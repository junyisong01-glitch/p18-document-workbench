# P18 Demo V1 — 统一工作台

**当前工作台基线（2026-11-21）**已整合启辰单库模式、中文身份展示、对话式知识问答、引用分组和右侧原文预览。问答默认使用本地 Ollama（`qwen3.5:4b`），检索使用原 Qwen Embedding。系统级 DeepSeek 默认关闭。公网部署暂停。详见 [最新版本说明](docs/LATEST_BASELINE.md)。

工作台使用 FastAPI、React/TypeScript、SQLite 和 Qdrant，面向本地虚构知识库演示。知识问答整合检索和本地回答，文档管理提供历史查阅。`main` 为维护基线，本机启动后访问 `http://127.0.0.1:8896/`。

首次检出提供源码、前端构建和空白配置模板。资料、账号权限配置、数据库、模型权重和凭据由维护者在本机准备。

## 本地准备

建议Python3.12、Node20及以上。以下只操作新检出目录，不连接既有8765/8876/8896数据：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt -r requirements-semantic.txt -r requirements-llm.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/prepare_review.py
.venv/bin/python scripts/experience.py --local
```

启动默认127.0.0.1:8896；先确认没有占用，禁止在实际运行目录执行上述初始化。已有服务时启动器只打开现有页。依赖安装由审查者在自己环境明确执行，本轮没有安装。

实际检索需要单独准备固定的Qwen/Qwen3-Embedding-0.6B权重，revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，1024维。缓存位置见config/demo-v1.json；本地推理不外发文档。未提供模型时不得宣称索引或检索已通过。DOC/Word预览还需要LibreOffice；通过SOFFICE_PATH指定本机转换器，未捆绑Mac软件。

日常使用可双击「启动P18体验工作台.command」。启辰模式使用本机 Ollama；需要试用 DeepSeek 时，在知识问答配置中按本次登录配置 Key，并按系统开关、公开级资料和逐轮确认规则执行。

## 启辰知识库模式

按[业务库说明](docs/BUSINESS_WORKFLOW.md)在本机准备核验过的数据和角色配置。在本地 `config/business.json` 中设置 `demo_offline` 为 `true`，工作台即以启辰单库模式运行。旧演示库的文件和索引备份保存在原运行环境。仅将示例配置纳入 Git。

既有演示环境的检索结果依赖其文档、权限和索引。源码测试在独立数据上运行。

## 测试与审查

```sh
.venv/bin/python -m pytest -q tests
node --test tests/*.cjs
node --test frontend/tests/*.test.cjs
cd frontend
npm run build
```

tests/通过代码构造虚构文档、工作簿和模拟客户端；不会调用真实DeepSeek。scripts/中的历史实验/预览入口保留供参考，不是本版主启动路径。不要运行旧默认8765入口进行本次审查。

重点按app/parser.py → excel_parser.py/word_structure.py → chunking.py → semantic.py/retrieval.py → library_policy.py/library_api.py → datasets.py/read_only_index.py → rag.py → scripts/experience_server.py审阅。frontend/src为React源码，web/app为当前构建快照。历史web/library、web/qa、web/search.js保留供既有测试和回退参考，不是当前使用的另一套工作台；/library/是同一新界面的兼容地址。

整合取舍、验收和回退见[统一版记录](docs/UNIFIED_RELEASE.md)。私有知识库配置、运行数据、模型缓存不在Git中；源码合并不会合并两套知识库。

重复问题向量缓存、问答阻断解释与容量提示的最新整合及禁用方法见[2211fcc择取记录](docs/DELIVERY_2211_INTEGRATION.md)。不采用交付包的密级切库、默认解析切换或造数初始化。

剩余交付功能的逐项实测与取舍见[补测记录](docs/REMAINING_2211_VERIFICATION.md)。新增只读“检查P18运行环境.command”；Docling仅为显式可选DOCX后端，当前8896仍legacy，WAL选项也默认关闭。

个人DeepSeek Key现在可在问答页按本次登录配置，API与部署边界见[个人Key说明](docs/PERSONAL_DEEPSEEK_API.md)。填写Key不授予文档外发权限。
