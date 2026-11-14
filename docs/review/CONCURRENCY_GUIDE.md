# 并发能力说明与实施手册

面向两件事：**现在能承诺什么**，以及**以后想提高并发该怎么做**。
所有数字都来自本机实测（123 份文档、`scripts/load_probe.py`），不是估算。

---

## 1. 一句话结论

**当前是单机演示原型：列表 55 QPS、检索 6.6 QPS，建议同时在线不超过 5 人。**
它能稳定演示，但不能当"部门级并发系统"承诺。

---

## 2. 现状：能力边界

### 2.1 实测

| 场景 | 并发 | QPS | p50 | p95 |
|---|---|---|---|---|
| 文档列表 | 5 | 55.1 | 88 ms | 118 ms |
| 文档列表 | 20 | 54.3 | 356 ms | 388 ms |
| 检索 | 5 | 3.0–6.5 | 720 ms | 4 488 ms（冷启动） |
| 检索 | 20 | 6.6 | 2 960 ms | 3 099 ms |

### 2.2 架构事实

| 事实 | 位置 | 影响 |
|---|---|---|
| 单进程单 worker | `scripts/experience_server.py` | 只能用满一个核 |
| 全局可重入锁 `LOCK` | `app/main.py` | 读路径也串行 |
| SQLite 单写 | `app/main.py:connect()` | 写并发要排队（已开 WAL） |
| Qdrant 本地目录模式 | `app/semantic.py` | 不能被多个进程共享 |
| Embedding 串行 | `app/embedding.py`（`LocalQwen` 内部锁） | 一次只编码一条 |
| 索引单线程池 | `app/semantic.py`（`max_workers=1`） | 索引不并行 |
| RAG 状态在进程内存 | `app/rag.py:112` | 多 worker 会丢票据 |

### 2.3 能给客户的承诺

- ✅ 单机演示、答辩、1–2 人操作：延迟 1 秒内，体感良好
- ✅ 5 人以内小范围试用：列表即时，检索 1–3 秒
- ❌ 10 人以上同时使用、对外服务、生产系统

---

## 3. 瓶颈归因（实测，不是猜）

列表接口原本每份文档查一次索引状态，76 份 151 ms。**已修**（见第 4 节）。

检索停在 ~6.6 QPS，逐项测量（128 份文档、约 300 个 chunk）：

| 环节 | 耗时 |
|---|---|
| `all_docs()` 全表反序列化 | 2 ms |
| 逐份读 `chunk_runs` + `chunks` | 2 ms |
| BM25 over 300 chunks | 4 ms |
| **一次检索的纯 Python CPU 合计** | **约 150 ms** |

**结论：不是数据库慢，是单核 Python 的 GIL。** 再多缓存也只能省掉其中一小段，
要提升只能多进程。

---

## 4. 已完成（第一期）

| 改动 | 效果 |
|---|---|
| 索引状态批量读取（`IndexService.status_many`） | 列表不再逐份查库 |
| 列表先切片再构造记录 | 一页 10 条不为全库付代价 |
| 候选集缓存（2 秒 TTL，`_candidate_map`） | 检索少一次全量重建 |
| 查询向量缓存（300 秒，256 条） | 同问题不重复编码 |

**列表：6.0 → 55 QPS（并发 5）；5.9 → 54 QPS（并发 20），p50 3 368 → 356 ms。**

### 已铺好的地基

- `P18_QDRANT_URL`：有值走 Qdrant 服务端，无值走本地目录（`app/semantic.py:31`）
- SQLite 已开 WAL + `busy_timeout=5000`（`app/main.py:connect()`）
- `P18_WORKERS` 开关存在，但 **>1 会直接报错** 并指向本文件

---

## 5. 剩下的三期：依赖顺序不能乱

```
状态外置 ──► 应用工厂化 ──► 多 worker ──► 压测验收
    │
    └──► （与 Qdrant 服务化同时满足，否则多 worker 无效）
```

**为什么不能先开多 worker**：
`RagService` 的 `sessions/drafts/tickets/receipts` 都在进程内存（`app/rag.py:112`）。
两个 worker 时，用户在 A 拿的票据落到 B 就是 `ticket_expired`——功能直接坏，不是变慢。

---

## 6. 实施手册

> 原则：每一步都在独立分支做，做完跑完整回归（`pytest` 422 + `smoke_e2e` 18 +
> `ui_smoke` 9 + `load_probe`），通过再进入下一步；任何一步失败就回滚，不叠着改。

### 6.1 状态外置（约半天）

**目标**：把四个内存 dict 换成 SQLite 表，带 TTL，值可写通。

**表结构**

```sql
CREATE TABLE IF NOT EXISTS rag_state (
  kind TEXT NOT NULL,              -- session / ticket / draft / receipt
  key  TEXT NOT NULL,
  body TEXT NOT NULL,              -- JSON
  expires REAL NOT NULL,
  PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS rag_state_expiry ON rag_state(expires);
```

**实现要点**

1. 新建 `app/rag_state.py`，提供 `StateView(store, kind)`，行为对齐 dict：
   `__getitem__ / get / pop / setdefault / __contains__ / __len__ / items / retain`
2. 取出的值用 **写通代理**（`MutableMapping` 子类）：`session['at']=...`、
   `session['rounds']=...` 这类赋值要立即落库，否则跨 worker 看不到
3. 替换 `app/rag.py:112` 的四个初始化；把第 147–150 行、303 行的
   `self.x = {k:v for ...}` 改成 `self.x.retain(lambda k,v: ...)`
4. `prune()` 改为按 `expires` 删行，不再遍历内存
5. 保留 `self.lock`（进程内互斥仍然需要）

**验收**

- 单 worker 下 422 测试 + 18 业务流全过
- 两个 worker（见 6.2）下：登录 → 草稿 → 选择 → 票据 → 发送，跨请求不出现 `ticket_expired`
- 重启服务后，未过期会话仍可用（说明真的落库了）

**回滚**：`rag_state.py` 不被 `rag.py` 引用即可退回内存实现。

### 6.2 应用工厂化（约 2 小时）

**目标**：让 uvicorn 能用导入字符串启动多 worker。

**做法**

1. 把 `scripts/experience_server.py` 的模块级逻辑（传输拦截、`external_allowed`
   补丁、`DatasetsApp` 安装）收进 `build_app()`，返回 ASGI 应用
2. 启动改为：
   `uvicorn.run("scripts.experience_server:build_app", factory=True, workers=N)`
3. `P18_WORKERS` 去掉"只能为 1"的守卫，改为读取真实值

**验收**

- `P18_WORKERS=2` 起得来，日志有两行 `Started server process`
- 任意请求打到任意 worker 都能正常返回（用 `load_probe` 并发验证）

### 6.3 Qdrant 服务化（约半天，容器已就绪）

**已具备**：容器 `p18-qdrant` 跑在 `127.0.0.1:6333`，代码已支持 `P18_QDRANT_URL`。

**切换步骤**

1. 停服务 → 设 `P18_QDRANT_URL=http://127.0.0.1:6333` → 启动
2. **重建全部索引**（本地目录的向量不能复用，collection 名含配置哈希）
3. `curl :6333/collections` 确认 collection 存在、点数对得上
4. 跑一遍 18 项业务流 + 检索基线

**回滚**：去掉 `P18_QDRANT_URL` 即回到本地目录（原向量仍在）。

### 6.4 多 worker 压测（约半天）

**目标数字**（4 核，参照第一期基线）：

| 场景 | 现在 | 目标 |
|---|---|---|
| 检索 20 并发 | 6.6 QPS / p50 2 960 ms | **≥ 20 QPS / p50 < 1 s** |
| 列表 20 并发 | 54 QPS | 不退化 |

不达标说明状态外置或 Qdrant 切换有问题，不要靠"再加 worker"掩盖。

### 6.5 PostgreSQL（2–3 天，按需）

**不要直接改 SQL**。当前代码里 `sqlite3` 用法散落在 `main.py / library_store.py /
egress.py / semantic.py`，特征是：`?` 占位符、`PRAGMA`、`json` 列、`INSERT OR REPLACE`。

建议：

1. 先抽 `app/db.py` 适配层：`connect()`、`execute()`、`executemany()`、事务上下文
2. 逐模块替换调用，保持 SQL 方言由适配层翻译
3. 迁移脚本：导出 SQLite → 建 Postgres 表 → 导入 → 校验行数与抽样内容
4. 双跑一周（读 Postgres、写两处）再切

**验收**：50 并发写入不超时；与 SQLite 结果逐条比对一致。

### 6.6 HTTPS、反代与备份（约 1 天）

- 监听地址改可配置（现在写死 `127.0.0.1`），默认仍是本机
- 反向代理终止 TLS；应用侧保留 `X-Forwarded-*` 校验
- 备份三件套要**同一时刻**：`workbench.sqlite3`、`qdrant/`、`files/`；先停写再打包
- 恢复演练：在干净目录还原后跑 18 项业务流

---

## 7. 每阶段必须复测的命令

```sh
.venv/bin/python -m pytest -q tests                    # 422 passed 基线
.venv/bin/python scripts/smoke_e2e.py                  # 18 项业务流
NODE_PATH=frontend/node_modules node tests/ui_smoke.cjs # 9 项真实浏览器
.venv/bin/python scripts/load_probe.py                 # 并发数字
.venv/bin/python scripts/eval_scale.py                 # 检索质量不退化
```

---

## 8. 风险与不要做的事

| 不要做 | 原因 |
|---|---|
| 直接在演示机上改 | 改到一半会留下"有时正常、有时 ticket_expired"的状态，最难排查 |
| 只做 Qdrant 不做状态外置 | 多 worker 会丢票据，比不加 worker 更糟 |
| 只做状态外置不做 Qdrant | 本地 Qdrant 有目录锁，第二个 worker 起不来 |
| 用 `uvicorn --workers` 硬开 | 应用是运行时组装的对象，必须走工厂 |
| 为了跑分调小 `top_k` 或关检索 | 那是拿质量换数字 |

---

## 9. 关键代码位置

| 关注点 | 文件:行 |
|---|---|
| RAG 内存状态 | `app/rag.py:112` |
| 过期与容量上限 | `app/rag.py:145-151` |
| 票据消费 | `app/rag.py:511` |
| Qdrant 客户端 | `app/semantic.py:29-34` |
| 索引线程池 | `app/semantic.py`（`ThreadPoolExecutor(max_workers=1)`） |
| 候选集重建 | `app/semantic.py`（`_candidate_map`） |
| SQLite 连接 | `app/main.py`（`connect()` / `initialize()`） |
| 启动与 worker | `scripts/experience_server.py`（文件末尾） |
