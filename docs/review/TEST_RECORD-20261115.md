# 测试记录（2026-11-15）

对象：`codex/p18-integration`（本机 8896 演示实例）。这是**流程验证记录**，不是规模验收。
结论先说：链路通、门禁在，未配置模型时行为符合设计；规模与真实语料未验证。

## 1. 环境

| 项 | 值 |
|---|---|
| 机器 | macOS 26.6.2 / arm64 |
| 运行 | `.venv/bin/python scripts/experience.py --local`，`127.0.0.1:8896`，单 worker |
| 解析 | DOCX = Docling 2.150.1，PDF = PyMuPDF，XLSX = openpyxl |
| 检索 | 本地 Qwen3-Embedding-0.6B（revision `97b0c614…`），`hybrid_dedup`，Top-5 |
| 生成 | DeepSeek，**未配置密钥** |
| 语料 | 演示库 2 份虚构文档（1 内部 / 1 机密），均经人工复核 |
| 账号 | `admin`（研发部员工，管理员）/ `dev`（启辰研发岗位）/ `prod`（启辰生产岗位） |

## 2. 自动化测试

```sh
.venv/bin/python -m pytest -q tests
# 412 passed, 1 skipped, 9 warnings in 35.8s
```

跳过项：真实模型生命周期测试（需要完整权重与外部服务）。

覆盖范围（按模块）：解析与切分（`test_chunking` / `test_docling_parser` / `test_word_structure` / `test_excel_parser`）、
检索（`test_retrieval` / `test_semantic`）、权限（`test_library_api` / `test_library_sessions`）、
RAG（`test_rag` / `test_rag_api` / `test_rag_boundaries` / `test_rag_selection`）、
外发（`test_external_permission` / `test_rag_permission_audit`）、迁移脚本（`test_ragflow_export` / `test_anythingllm_export`）、
网关（`test_gateway`）、评测脚本（`test_eval_retrieval`）。

## 3. 接口冒烟

| # | 用例 | 预期 | 实测 |
|---|---|---|---|
| A | 未登录 `GET /api/documents` | 401 | ✅ 401 |
| B | 未登录 `POST /api/gateway/ask` | 401 | ✅ 401 |
| C | 三个身份可见文档 | 2 / 2 / 0 | ✅ 2 / 2 / 0 |
| D | `prod` 直接取 `admin` 文档 ID | 404（不泄露存在性） | ✅ 404 |
| E | `dev` 取同一文档 | 200 | ✅ 200 |
| F | `dev` 检索「晨间校准几分钟」 | 命中表格块 | ✅ 2 条，Top1 0.449 |
| G | `dev` 检索库里没有的「夜间模式…」 | 可返回但不含答案 | ✅ 2 条，不含“夜间” |
| H | `prod` 检索（无可见文档） | `no_index` | ✅ 空结果 |
| I | `prod` 调网关 | 拒绝 | ✅ 409 |
| J | 未启用网关时调 `/api/gateway/ask` | 路由不存在 | ✅ 404 |

## 3b. RAG 边界用例（补充）

| 用例 | 预期 | 实测 |
|---|---|---|
| 空问题 | 拒绝 | ✅ 422 `string_too_short` |
| 2001 字问题 | 拒绝 | ✅ 422 `string_too_long` |
| 不存在的草稿 | 拒绝 | ✅ 409 `draft_expired` |
| 复用已消费票据 | 拒绝 | ✅ 409 `ticket_expired` |
| 选不可外发候选 | 拒绝 | ✅ 409 `selection_forbidden` |
| 选择版本不匹配 | 拒绝 | ✅ 409 `selection_changed` |
| 未勾选同意即发送 | 拒绝 | ✅ 409 `consent_required` |
| 无密钥发送 | 拒绝 | ✅ 409 `api_not_configured` |

## 4. RAG 门禁链路（未配置密钥）

| 步骤 | 预期 | 实测 |
|---|---|---|
| `POST /api/rag/drafts` | 200，出候选 | ✅ 2 候选，表格块第一 |
| 候选是否可选（资料=内部） | 不可选，且原因是**部署策略** | ✅ `policy_public_only` / `deployment_policy` |
| 改成公开并授予 fictional 许可后 | 可选 | ✅ `selectable: true`，预算 2 组 / 1624 字符 |
| `POST /api/rag/selection` | 200，发票据 | ✅ 票据有效 180 秒 |
| `POST /api/rag/answer`（含同意） | 拒绝：未配置 | ✅ 409 `api_not_configured` |
| `POST /api/rag/answer`（无同意） | 拒绝：需同意 | ✅ 409 `consent_required` |

> 测试期间把演示文档临时改为「公开」以验证可选性，验证后已改回「内部」；
> 当前 `admin 2 / dev 2 / prod 0` 已恢复。该文档上保留了一份 fictional 外发许可。

## 5. 检索质量

见 `docs/review/RETRIEVAL_BASELINE.md`：当前 2 份语料 6 条可答题 Core@1 = 6/6（送分题）；
历史 38 题冻结集 Core@1 53% / Complete@1 44%（旧解析器，不可直接对比）。
**本轮未做规模检索评测。**

## 6. 本轮发现并修复的缺陷

| 编号 | 现象 | 根因 | 状态 |
|---|---|---|---|
| D1 | 网关答案带 `<think>…</think>` | 模型思考内容原样透传 | 已修（随 AnythingLLM 移除，代码保留在历史提交） |
| D2 | 被拒绝的请求不进审计 | 409 在审计之前抛出 | 已修，记录 `status=refused` |
| D3 | 「内部」资料不可选时只提示“未获外发许可” | 体验版策略与授权缺失共用一个原因码 | 已修，新增 `policy_public_only` 与独立文案 |

对应提交：`df581bb`（D1/D2）、`24f0e27`（D3）、`26a5190`（D4）、本次（D5）。

| D4 | 答案含 `arr[0]`、原文里的链接或页码时被整条丢弃 | 引用解析吞掉一切方括号；位置检查不分“引用原文”与“编造” | 已修（`26a5190`）：只认 `[S数字]`；位置必须出现在证据原文里 |
| D5 | 发送与撤权之间存在竞态窗口 | 许可检查在锁内、网络发送在锁外 | 已根修：新增读写门（`app/egress_gate.py`），发送是读者、授予/撤销是写者；撤销会等待在途发送结束后才返回 |
| D6 | 历史来源失效后整个会话作废，重试也没用 | 只报错不清理 | 已修：报错同时丢弃失效轮次，同会话重试可继续（`history=[]`） |
| D7 | `继续`/`那么` 这类普通衔接词触发追问改写 | 代词正则过宽 | 已修：抽出 `refers_back()`，只认 `他/她/它/该项目/上述/前述/那位/这位/此人` |
| D8 | 证据因容量被丢弃时，用户无从得知 | 跳过是静默的 | 已修：响应新增 `budget_skipped` |

## 7. 未覆盖（不得声称通过）

- 真实 DeepSeek 问答质量、拒答率、引用正确性
- 30 份真实语料的检索精度与召回
- 并发、长时间运行、崩溃恢复
- AnythingLLM 路径（已整体移除）
- OCR（扫描件 PDF）

## 8. 复现

```sh
.venv/bin/python scripts/provision_demo.py               # 建空库与三个账号
.venv/bin/python scripts/experience.py --local           # 8896
.venv/bin/python -m pytest -q tests                      # 412 passed
.venv/bin/python scripts/eval_retrieval.py --username dev --password p18-review-2026 \
    --cases tests/fixtures/retrieval_baseline.json       # 检索流程基线
```

## 9. 关于“历史来源失效”的处理

会话里任何一轮的来源被撤权或索引失效后，带该会话的新提问会报 `history_invalid`，
**同时把失效轮次从会话里丢弃**。因此：

- 用户第一次会看到明确的错误，知道历史不可信；
- 紧接着重试（哪怕不换会话）就能继续，不会永久卡死；
- 前端 `web/qa/flow.js` 仍会重置会话，两条路都通。

不改成"静默丢历史继续答"的理由：那样用户会以为模型还记着上文，实际上下文已经变了。

## 9b. 明确不做的两项

| 项 | 为什么不做 |
|---|---|
| 相似度阈值 | 实测可答题 0.449–0.683、不可答题 0.320–0.506 **区间重叠**，任何单一阈值都会误杀或漏放；拒答交给 RAG 层的 `insufficient_evidence` |
| Reranker | BGE Base 实验：Core@1 17→24，但 Complete@3 30→29 退步，结论是不采用 |

## 10. 撤权竞态现在的保证

新增 `app/egress_gate.py`（读者=发送，写者=授予/撤销）：

- 撤销请求会**等待在途发送结束**再返回；
- 撤销进行中，新的发送会排队，不会带着旧许可出发；
- 发送在门内做**最终许可校验**，校外不再有“检查完才发”的窗口。

仍然存在的物理事实：已经开始的这一次发送无法召回字节；但它发生在撤销返回之前，
所以“撤销返回后不会再按旧许可发送”这句话现在是真的。撤销路径实测无死锁（12 ms 返回）。
