# 可配置LLM Provider

RAG的检索、ACL、发布/索引过滤、证据选择、快照、人工确认与引用校验保持原流程。推理经 `BaseLLMProvider.generate(prompt: str) -> str`；`app/llm.py`管理Provider、固定地址、路由、健康检查。原urllib适配器移至 `app/llm_legacy.py`，仅在未配置LLM_PROVIDER时维持旧部署/BYOK兼容；显式deepseek路由使用OpenAI SDK，不会调用OpenAI服务。

## 配置及依赖

复制 `.env.example` 为项目根目录 `.env`，真实文件已被Git忽略。环境变量优先；只解析四个受控变量的字面量，不执行shell。启动读取配置，不通过修改浏览器参数选择Provider。

```dotenv
LLM_PROVIDER=ollama
DEEPSEEK_API_KEY=
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_NUM_CTX=16384
```

DeepSeek固定 https://api.deepseek.com 和 deepseek-flash，使用环境Key；已有登录用户也可沿用会话内个人Key。清除个人配置会在该会话禁用Key，不回传、不持久化。旧部署未显式路由时继续保持个人Key不继承全局Key。

可选依赖文件 `requirements-llm.txt` 已锁定OpenAI SDK 2.54.0。它是Apache-2.0许可，来源为官方PyPI openai包；本次仅装入受控工作副本 `.optional/llm`，连同依赖约21MB，没有修改8896虚拟环境。部署时在目标隔离虚拟环境安装依赖，或通过PYTHONPATH引用该可选目录。未安装/启动Ollama及其模型，不自动下载权重。

Ollama固定 localhost:11434，通过GET /api/tags检测服务和所选模型；POST /api/chat显式带options.num_ctx（最低16384）、stream=false、format=json、truncate=false。除配置窗口外还做UTF-8字节上限的保守检查，为输出与模板留容量；超限拒绝，不静默截断。该检查可能拒绝实际可容纳的部分长文本，不能替代精确tokenizer评估。

## 安全与确认

- 来源库由服务端业务实例决定，浏览器不能宣称自己是demo。qichen/qichen30/business到DeepSeek显式拒绝；本地推理仍只能使用身份可读、当前已发布且索引有效的证据。
- 演示库DeepSeek保留逐份外发许可、消息预览、本次人工确认和一次性ticket。默认不自动发送。
- 本地故障不自动发往外部。仅演示库显示“确认切换到DeepSeek”；POST /api/rag/fallback要求已认证用户和严格布尔确认。成功后清空旧草稿、票据、历史及回执，再重新检索、核对完整消息并第二次确认实际发送。
- 启辰库没有降级按钮，服务端也拒绝降级。模型与地址变化使旧票据失效；权限/索引变更仍在发送前后复核。
- 两Provider共用严格system：无证据固定拒答“知识库中未找到相关内容”。模型JSON及引用编号由后端校验；有效回答末尾补上已校验来源片段编号。Prompt约束不能保证模型不出现幻觉，重要内容仍需人工核对。
- 固定目标，无代理继承、无重定向、无自动重试；不记录Key、原始异常体或请求正文。

## 同题对比脚本

```sh
python scripts/compare_llm.py --env .env --health-only
python scripts/compare_llm.py --env .env
```

将.env的LLM_PROVIDER分别设为ollama和deepseek，各运行一次。脚本始终只用内置公开虚构资料和同一个问题，不读取企业文档或数据库。DeepSeek需要核对打印的完整消息后输入SEND；无人值守使用--confirm-external只授权该内置虚构示例。Ollama不可用时，交互输入DEEPSEEK仅确认路由，仍需再次确认发送；非交互不自动降级。脚本不属于真实知识库检索质量评测。

## 抽象层首次交付记录（真实模型测试前）

受控工作副本实现并验证，未覆盖8896运行代码或切换其Provider。当前本机Ollama端口未运行，未做真实模型回答对比；SDK真实序列化使用内存HTTP传输验证，未调用付费API或外发企业数据。启用前需自行准备Ollama服务及模型，或配置已授权DeepSeek Key，并在受控环境完成真实推理验收后再发布。

协议参考：https://api-docs.deepseek.com/ ，https://docs.ollama.com/api/chat ，https://docs.ollama.com/api/tags 。


## 2026-11-18 Qwen真实模型下载与验证

用户直接授权下载并真实测试。复用Ollama0.40.2，隔离目录下载官方qwen2.5:7b Q4_K_M约4.7GB（Apache2），16GB Mac串行运行，日志确认上下文16384；未改原Gemma模型或8896。真实测试后补强统一SYSTEM的JSON正文与多来源引用格式，保持严格验证。最终合成5/7：冲突判断错误、注入资料过度拒答；启辰三条业务题仅E4291完整，BUG题漏编号、版本题遗漏/误归因，另无证据拒答通过。普通链路约7-8秒，首条14.5秒；Chrome真实E4291闭环通过。接口成功不等于质量通过，暂不建议设为默认。

回归488通过5跳过。没有可用环境DeepSeek Key，未提取个人Key，未发真实DeepSeek请求；无启辰外发。临时8907关闭，模型已卸载，11434仅回环待用，权重保留且不进Git；8896代码及入口保持原状。控制副本含既有验收样本，本次选入证据均为原启辰文档，不冒充纯30份检索基准。多轮结果、真实问答及来源、截图、digest和隔离核验见本机.development/llm-real-model-20261118/结果.md。


## 2026-11-18 本地回答模型正式接入8896

用户授权只替换最终回答模型。正式8896默认使用Ollama/qwen3.5:4b，显式16384上下文、无需API Key；保留原检索模型、排序、配置、文档与索引。移除测试中的默认2组限制，按原最多8组及实际容量选择。原逐轮确认与权限保留；启辰外发/降级403，无效票据409；演示库本地实测校准18/24分钟正确。原启动命令已接入本地模型服务启动/复用，缺失服务不自动外发或下载。

Python495通过4跳过，前端8通过，构建通过；正式14账号两库可见范围及关键检索结果逐项一致，142份受保护文件和28张业务表校验一致。实际4道启辰题中编号、错误码、拒答3题正常，复杂版本题仍混淆早期未执行和后续模拟发布，不能算全对；已保留来源供核对。真实DeepSeek对比未完成。本地源代码及SDK/模型已部署，未推送GitHub。正式PID80896，本地模型PID80953，8907已关闭；检查点、发布清单、截图与质量限制见本机.development/local-llm-live-20261118/结果.md。启动器首次根路径缺失已修复并实测，旧日志保留。

使用：打开原8896知识问答页面并刷新，看到“Ollama · qwen3.5:4b · 本机推理”后，按原流程检索、核对证据、预览完整消息、确认发送。原“启动P18体验工作台.command”会复用或启动已安装的本机模型；没有Key也可本地生成。模型文件位于正式工作台.optional/ollama/models，配置在其.env，仅含Provider/模型/上下文三项。旧阶段的“尚未下载/未部署”描述属于历史记录。


## 演示库的会话内模型选择（2026-11-18）

正式知识问答提供本地Ollama/DeepSeek选择。启动.env继续决定默认路由；页面选择仅当前登录有效，不改变其他用户，也不将启辰资料送到外部。

- POST `/api/rag/provider`，正文`{"provider":"deepseek","confirm_external":true}`：先明确选择外部模型，再重新选择获准证据和逐轮确认。
- POST `/api/rag/provider`，正文`{"provider":"ollama"}`：返回本地模型。
- 需有效登录、同源自定义客户端头及HTTPS/本机回环；不接收任意URL/模型名称。切换过程中不发送问题或文档。
- 回答进行中409；成功切换清除旧草稿、票据、历史和回执；Key仍仅当前会话内存，可主动清除，退出/重启失效。
- 启辰库Provider选择POST由业务权限层403拒绝；生成层仍检查source_library，不能凭老板身份或演示库个人Key越过。
- `/api/rag/fallback`原故障条件与明确确认保持。页面健康时主动选择DeepSeek使用新的会话选择接口，不伪装成服务故障。

8910保持隔离样式参照。正式确认区域以实际pending.messages、实际接收地址和原票据为准，没有复制示例问题、来源或预览回答。
