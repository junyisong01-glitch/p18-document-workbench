# 最新源码基线（2026-11-19）

用户本轮授权将所有最新源码合并到 GitHub 主分支，并暂停部署上线。此前文档中“未推送”“未接入”等表述属于对应阶段的历史；实际发布状态以 GitHub main 提交为准。

## 当前代码入口

| 范围 | 文件 | 行为 |
|---|---|---|
| 登录与激活 | `frontend/src/pages/Login.tsx`、`LoginFlow.css`、`components/DemoIdentityCards.tsx` | 激活和登录互斥展示；14卡按五组展示姓名/原账号，点击填入后明确登录 |
| 业务文档 | `frontend/src/pages/BusinessPage.tsx`、`components/DocumentLayout*`、`EnterpriseActions.tsx` | 真实提交进度、部门分类、审核发布、历史/回收站与邀请入口 |
| 角色及账号 | `app/business_roles.py`、`enterprise_accounts.py` | 唯一老板、主管/员工/访客；老板与人事主管邀请建号；任免使旧会话失效 |
| 状态与版本 | `app/business.py`、`enterprise_documents.py` | 老板/主管自审留审计；普通本部门发布件主管可读；普通件明确借阅；本人轻量勘误保留旧内容、索引后切换；核心修改走新版审批 |
| 检索 | `frontend/src/pages/SearchPage.tsx`、`components/SearchEvidence*`、`SourceContent.tsx` | 原生命中表格直接显示，保留来源/合并信息；历史单独查阅，不作为RAG证据 |
| 问答 | `frontend/src/pages/QaPage.tsx`、`components/EvidenceStack*`、`QaConfirmation*`、`QaModelRoute*` | 可选问题、证据分组收拢、真实完整消息驱动确认区、来源引用和两种模型入口 |
| 模型与路由 | `app/llm.py`、`llm_legacy.py`、`rag.py`、`scripts/local_llm.py` | 只替换最后生成回答环节；当前登录演示库可明确选择本地或DeepSeek，选择后旧票据失效 |
| 两库入口 | `app/datasets.py`、`config/business.example.json` | 启辰可写业务库与演示资料库；旧只读入口兼容保留，不增设第三个可见知识库 |
| 构建结果 | `frontend/src/` → `web/app/` | React/TypeScript源码与本次生产构建一致；历史独立静态预览不是正式页面 |
| 部署准备 | `deploy/cloud/` | 独立演示打包、网关、Docker Compose及Caddy；没有完成Linux容器、云端性能和外网验收 |

## 保留的安全边界

- 主搜索/RAG只接受当前身份可读、已发布且索引有效的资料；待审、历史、回收站不混入RAG。
- 启辰库所有身份禁止外部模型API；老板不豁免。演示库DeepSeek需配置当前会话Key、逐份许可及逐轮完整消息确认。
- 员工无审核、发布、删除权限；部门以外仅可读公司公开与明确借阅的资料。机密不因同部门或主管身份自动开放。
- 物理删除仅老板可执行，先软删除，输入完整ID，按所选版本处理并保留审计墓碑。
- 16384上下文显式保留；本地故障不悄悄外发。切换Provider不改变Embedding、切分或检索排序。

## 检出源码不等于复制本机数据

GitHub包含完整实现、测试、空白环境模板和配置示例，不包含现有账号密码、邀请、会话、API Key、SQLite、上传原件、预览副本、Qdrant数据、模型权重或本机依赖。

首次检出为空数据环境，14张卡的显示和账号权限依赖可信维护者在本机准备的账号配置、显式演示开关及独立业务种子，不能从源码推断账号已存在。`config/business.json`与`runtime/**/business-seed.json`仍为本地配置，不提交；不要将未经核验的目录配置成现有知识库。两库现有文档和检索成果仍留在原本机运行环境。

本地模型配置见根目录`.env.example`及[模型文档](LLM_PROVIDERS.md)。Ollama、公开模型权重、固定revision的Embedding和LibreOffice须在本地另行准备；不会因检出Git而自动下载。真实DeepSeek模型质量对比尚未完成，不以合成测试通过代替模型效果验收。

## 给后续前端协作者

从本文件和README进入，再读 `frontend/src/pages/`、`components/`、`lib/api.ts`、`lib/types.ts` 及对应后端端点。以真实接口和状态为准；Kimi压缩包仅是视觉参考，模拟权限、模拟审批、模拟答案不作为正式实现。

## 本轮核验与十三项交接

| 项 | 内容 | 交接结果 |
|---|---|---|
|1|远端基线|更新前main为588dbedaee7468554ace6485f2197f84db726cfb，与本地旧HEAD源码树一致；未覆盖远端独有代码|
|2|范围|后端、前端、测试、配置模板、部署准备脚本统一纳入|
|3|身份|四职责、五分组、14张卡显示及真实权限实现|
|4|账号|邀请激活及人员职责保留|
|5|流程|自审、审核发布、本人进度、退回重提|
|6|版本|新版本审批和有审计的轻量勘误双轨|
|7|文档页|采用已确认的紧凑布局及老板部门分类|
|8|检索页|采用结构化命中证据表格，原算法保持|
|9|问答页|采用分组证据、确认区及示例问题|
|10|模型|Ollama本地回答及DeepSeek入口，启辰外发禁令保持|
|11|数据边界|不提交原件、数据库、权重、密码及个人Key|
|12|部署状态|用户暂停，临时后端关闭，云部署代码尚未完成云端验收|
|13|发布核验|测试/构建与实际合并结果记入本轮进度；不以文档宣称代替远端确认|
