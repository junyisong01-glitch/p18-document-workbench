# 迁移方案 B（轻量版）：用 AnythingLLM 替换 P18 自研主体

状态：2026-11-14 选定并已在本机安装验证。P18 代码保留在
`codex/p18-demo-v1-review-20261114`、`codex/p18-docling-parser`，不删除。

选它而不是 RAGFlow 的原因：RAGFlow 需要 5 个容器 + 16G 内存，本机实测卡在
MySQL 远程授权和 kvrocks 崩溃；AnythingLLM 是单应用（Electron + 内置服务），
无 Docker、无外部数据库，和"单机演示机"的定位一致。

## 1. 本机实测记录

| 步骤 | 结果 |
|---|---|
| 下载 `AnythingLLMDesktop-Silicon.dmg` v1.19.0（584 MB） | ✅ 经本机代理 8.5 MB/s，约 70 秒 |
| 安装到 `/Applications/AnythingLLM.app`（1.9 GB） | ✅ |
| 启动 | ✅ 进程起来，内置服务监听 `127.0.0.1:3001`，另有 `:8888` |
| `GET /api/ping` | ✅ 200 |
| 本地库初始化 | ✅ `~/Library/Application Support/anythingllm-desktop/storage/anythingllm.db`（workspaces / workspace_documents / api_keys 等表） |
| `GET /api/v1/workspaces`（无 Key） | 403 `No valid api key found`（预期） |
| 生成 API Key（直接写 `api_keys` 表，绕过 UI） | ✅ 可用，`GET /api/v1/workspaces` → 200 |
| 建 workspace「公开」 | ✅ slug `4790eaa5-221b-4210-8cc6-4c7aa772c27a` |
| 上传 `zx8.md` + `update-embeddings` | ✅ `[NativeEmbedder] Initialized Xenova/all-MiniLM-L6-v2`，LanceDB 生成 2 条向量 |
| `POST /api/v1/workspace/{slug}/vector-search` | ❌ 500，日志报 `No OpenAI API key was set` |
| `POST /api/v1/workspace/{slug}/chat` | ❌ 同上：检索与问答都会先构造 LLM provider |

**结论**：解析—切分—向量化链路已通（本机内置 native embedder，不联网）；检索与
问答被"必须存在一个 LLM provider"卡住。直接改 `system_settings`（`LLMProvider=ollama`
等）在本 build 里不生效，官方路径是桌面向导里选模型。

## 2. 能力对照

| 能力 | P18 现状 | 迁移后 |
|---|---|---|
| 解析 PDF/DOCX/PPTX 等 | 自研 + Docling | AnythingLLM 内置（含 OCR 可选） |
| 切分 / 向量 / 检索 | 自研 E1/E2 + BM25 + RRF | 内置（LanceDB + 向量检索） |
| 问答界面 | 三套自研前端 | 自带 Chat UI |
| 隔离粒度 | 行级 ACL（密级/部门/查看人） | **workspace 级**（一个密级一个 workspace） |
| 逐份外发授权 | 有（票据 + 人工确认） | **无**：问答直接调模型 |
| 只读第二知识库 | 有 | **无**，需重建索引 |
| Excel 行级溯源 | 有（`sheet!r2c1`） | **无**，只有表格文本 |
| 部署 | Python + SQLite + Qdrant | 单个 .app，无容器 |

> 裁剪的四项写死在这里。对外不能再宣称"机密不外发""可以逐份授权"。

## 3. 数据迁移

```sh
# 1) dry run：看会生成几个 workspace、跳过哪些
.venv/bin/python scripts/export_to_anythingllm.py --data-dir runtime/demo-v1-experience

# 2) 在 App 里完成向导并生成 API Key（Settings → Tools → Developer API）
# 3) 批量导入
.venv/bin/python scripts/export_to_anythingllm.py --data-dir runtime/demo-v1-experience --push \
    --api-base http://127.0.0.1:3001 --api-key <生成的 Key>
```

映射规则与 RAGFlow 版一致：`library_metadata.classification` → workspace 名；
原件原样上传；`deleted/superseded/characters=0` 跳过；块与向量不迁移，由
AnythingLLM 重新解析嵌入。

## 4. 验收清单

1. App 能打开并进入主界面（本机已验证进程与端口）
2. 生成 API Key 后，`GET /api/v1/workspaces` 返回 200
3. 导入后 workspace 内文档数 == dry run 的数量
4. 在某个 workspace 里问"晨间校准几分钟"，命中并引用到正确文档
5. 跨 workspace 不可见（用两个 workspace 验证隔离）
6. 断网 + 本地模型（Ollama）时仍可问答

## 5. 最后一公里（必须人工）

桌面版是 Electron 应用，首次向导（选择模型、生成 API Key）无法脚本化。
两条路：

- **手动 2 分钟**：打开 App → 跳过云模型 → Settings → Tools → Developer API → 生成 Key → 把 Key 给我，我跑导入与验收。
- **直接改库**（不推荐）：向 `api_keys` 表插一条记录再重启 App。可行但绕过产品逻辑，除非明确要求否则不做。

## 6. 回滚

- `rm -rf /Applications/AnythingLLM.app` + 删除 `~/Library/Application Support/anythingllm-desktop`
- P18 未改动，8896 未重启，随时可回。

## 7. 风险

| 风险 | 应对 |
|---|---|
| 失去权限/外发边界 | 交付文档与申报口径同步改；不得沿用旧说法 |
| 桌面版单机、无并发 | 明确定位为演示机 |
| 模型仍需选择（云端或 Ollama） | 演示用 Ollama 本地模型，问答不出网 |
| 30 份库成绩不可复现 | 旧成绩标记为"迁移前历史记录" |
