# P18 Demo V1 — 源码审查分支

这是当前8896体验版的代码归集，不是生产发布。基于GitHub main ee84209；运行中的Mac工作台没有被覆盖。

包含FastAPI后端、React/TypeScript文件库、原生JavaScript检索/问答页面、Excel解析、E2结构切分、Qwen Embedding接口、Qdrant/SQLite、RAG人工证据确认、四岗位和只读双数据源适配。未默认启用任何Reranker或失败的新提示词。

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

## 解析后端：Docling（默认）与原实现

安装 `requirements-docling.txt` 后，`.docx`/`.doc` 默认走 Docling；未安装时自动退回 python-docx，实际使用的后端记录在 `parser_version` 里。

```sh
.venv/bin/python -m pip install -r requirements-docling.txt
P18_PARSER=legacy .venv/bin/python scripts/experience.py --local   # 强制旧解析
P18_PARSER=docling .venv/bin/python scripts/experience.py --local  # 连 PDF 也用 Docling
```

| 格式 | 默认 | 说明 |
|---|---|---|
| `.docx`/`.doc` | Docling | 输出仍是同一套 blocks/tables/issues，切分、复核、来源定位、文件库预览不变 |
| `.pdf` | PyMuPDF | Docling 的 PDF 管线需要约 500 MB 本地权重、CPU 约 2 秒/页，与单文档 180 秒上限冲突；`P18_PARSER=docling` 时才启用，已实测可用 |
| `.xlsx` | openpyxl | 不替换：Docling 的表格输出没有工作表名、行号和单元格坐标，而这三样是 Excel 预览与行级溯源的产品数据 |

- 合并单元格仍会触发人工复核；Docling 不额外解释合并语义。
- 显式 `P18_PARSER=docling` 但未安装时，解析明确失败并提示，不会静默降级。
- 依赖树较大（含 torchvision、opencv 等）；不安装也不影响原流程。

## 测试与审查

```sh
.venv/bin/python -m pytest -q tests
node --test tests/*.cjs
cd frontend
npm run typecheck
npm run build
```

tests/通过代码构造虚构文档、工作簿和模拟客户端；不会调用真实DeepSeek。scripts/中的历史实验/预览入口保留供参考，不是本版主启动路径。不要运行旧默认8765入口进行本次审查。

重点按app/parser.py → excel_parser.py/word_structure.py → chunking.py → semantic.py/retrieval.py → library_policy.py/library_api.py → datasets.py/read_only_index.py → rag.py → scripts/experience_server.py审阅。frontend/src为React源码，web/library/assets为当前构建快照；web/qa和web/search.js是另一组真实使用的页面，不能只交React目录。
