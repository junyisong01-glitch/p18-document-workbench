# P18 Demo V1 — 统一工作台

本版将文件管理、检索、问答和身份页面统一到一套 React 界面。FastAPI、E2 检索、权限及人工选证据机制继续使用现有实现。唯一维护基线是本仓库 main，体验入口为 http://127.0.0.1:8896/ 。这是本地虚构资料演示版，不是企业生产系统。

包含FastAPI后端、React/TypeScript统一界面、Excel解析、E2结构切分、Qwen Embedding接口、Qdrant/SQLite、RAG人工证据确认、四岗位和只读双数据源适配。未默认启用任何Reranker或失败的新提示词。

**不包含账号密码、API Key、数据库、模型、30份原件、真实ACL、历史试题或测试答案。首次检出是空库，不会自动出现本机的6份或30份资料。**

## 本地准备

建议Python3.12、Node20及以上。以下只操作新检出目录，不连接既有8765/8876/8896数据：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt -r requirements-semantic.txt
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python scripts/prepare_review.py
.venv/bin/python scripts/experience.py --local
```

启动默认127.0.0.1:8896；先确认没有占用，禁止在实际运行目录执行上述初始化。已有服务时启动器只打开现有页。依赖安装由审查者在自己环境明确执行，本轮没有安装。

实际检索需要单独准备固定的Qwen/Qwen3-Embedding-0.6B权重，revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`，1024维。缓存位置见config/demo-v1.json；本地推理不外发文档。未提供模型时不得宣称索引或检索已通过。DOC/Word预览还需要LibreOffice；通过SOFFICE_PATH指定本机转换器，未捆绑Mac软件。

日常使用：双击“启动P18体验工作台.command”。需要真实AI时使用“启用P18真实AI.command”隐藏输入一次密钥；不会自动提问，但确认发送可能计费。未配置时管理和检索仍可用。禁止把真实企业机密用于外部问答；发送前撤权竞态尚未根治。

## 第二知识库

默认config/qichen-libraries.json禁用。只有独立获得资料访问权后，才在本机填写已有数据目录和逐文档ACL；**不要把真实配置提交Git**。结构见docs/review/DATASETS.md。使用已有向量的只读加载器，不重新向量化，不复制建立第二套索引；两库共享本地Embedding提供者。权限不能从文件夹或客户端岗位字段获得。

既有本机演示成绩与本轮源码测试结果分开记录，见docs/review/STATUS.md。已有运行数据不是Git源码的一部分，没有授权数据时无法在其他电脑复现30份库的检索成绩。

## 测试与审查

```sh
.venv/bin/python -m pytest -q tests
node --test tests/*.cjs
cd frontend
npm run build
```

tests/通过代码构造虚构文档、工作簿和模拟客户端；不会调用真实DeepSeek。scripts/中的历史实验/预览入口保留供参考，不是本版主启动路径。不要运行旧默认8765入口进行本次审查。

重点按app/parser.py → excel_parser.py/word_structure.py → chunking.py → semantic.py/retrieval.py → library_policy.py/library_api.py → datasets.py/read_only_index.py → rag.py → scripts/experience_server.py审阅。frontend/src为React源码，web/app为当前构建快照。历史web/library、web/qa、web/search.js保留供既有测试和回退参考，不是当前使用的另一套工作台；/library/是同一新界面的兼容地址。

整合取舍、验收和回退见[统一版记录](docs/UNIFIED_RELEASE.md)。私有知识库配置、运行数据、模型缓存不在Git中；源码合并不会合并两套知识库。

重复问题向量缓存、问答阻断解释与容量提示的最新整合及禁用方法见[2211fcc择取记录](docs/DELIVERY_2211_INTEGRATION.md)。不采用交付包的密级切库、默认解析切换或造数初始化。

剩余交付功能的逐项实测与取舍见[补测记录](docs/REMAINING_2211_VERIFICATION.md)。新增只读“检查P18运行环境.command”；Docling仅为显式可选DOCX后端，当前8896仍legacy，WAL选项也默认关闭。

个人DeepSeek Key现在可在问答页按本次登录配置，API与部署边界见[个人Key说明](docs/PERSONAL_DEEPSEEK_API.md)。填写Key不授予文档外发权限。
