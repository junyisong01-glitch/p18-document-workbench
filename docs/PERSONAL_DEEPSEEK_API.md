# 网页个人DeepSeek Key与RAG接口

## 使用

正常登录8896→演示资料库→知识问答→右上角“配置模型API”→输入自己的API Key→“保存配置”。配置弹窗显示后端实际模型与地址，详情见[界面说明](MODEL_CONFIG_UI.md)。输入框立即清空，后端只返回是否配置，不返回完整Key或尾号。保存只做格式检查，不访问DeepSeek验证；余额、有效性仍待用户实际调用时确认。调用费用由该Key对应账户承担。

Key仅按登录会话保存在后端进程内存，不进入环境变量、SQLite、配置、日志、浏览器storage或Git。刷新页面可继续用当前会话；清除、退出登录、服务重启后需重新填写，过期会话不能使用。Python字符串无法承诺物理内存擦零，过期对象在后续会话清理/进程退出时释放。正在进行的请求不能更换Key，已发出的请求也不能撤回。

不继承管理员/启动器的全局Key。填写Key不增加文档权限、不授予外发许可，启辰30份库仍本地只读、禁止外发。当前演示库仅已获逐份许可的虚构公开文档可发送；其余资料先走管理员的原生审核许可流程，不批量授权。

配置后：原生检索drafts→人工选择selection→核对完整消息、来源、接收地址与可能费用→同意后answer。更换或清除Key会销毁已有发送票据，须重新预览确认。没有Key仍可上传/检索/看来源。

## 接口

所有接口都要求正常登录会话（HttpOnly Cookie或登录会话Bearer），修改请求需X-P18-Client: workbench。个人密钥配置只接受HTTPS；本机127.0.0.1/localhost回环允许HTTP。API Key不能放在URL、查询参数、shell历史或前端持久存储中。登录凭据与DeepSeek Key是两种不同凭据。

| 方法/地址 | 作用 |
|---|---|
| GET /api/rag/credentials | 当前登录是否已配置，scope=login_session、persistent=false；绝不回传Key |
| PUT /api/rag/credentials | JSON只有api_key字段，最长256字符；返回verified=false（未发起付费验证）。拒绝自定义接收URL与多余字段。 |
| DELETE /api/rag/credentials | 清除当前登录的Key和旧发送票据；其他会话不受影响 |
| POST /api/rag/drafts | question与可选session_id；得到当前权限/许可下的原生候选及默认选择 |
| POST /api/rag/selection | draft_id、selection_version、candidate_ids；得到完整messages、来源、预算和一次性ticket |
| POST /api/rag/answer | ticket和consent:true；消耗一次票据，通过发送前复核后调用模型；不自动重试 |

这些接口是P18受控RAG接口，不是允许任意提示词/原文直接转发的通用代理。模型、系统提示与容量延续原值；个人Key只允许发往https://api.deepseek.com/chat/completions，不接受重定向或用户指定目标。官方协议参考：https://api-docs.deepseek.com/api/create-chat-completion/。

## 当前接入与未来部署边界

本机启动无需再经终端输入Key，启动器以web-ready模式运行，由每个登录用户自行配置。本机仍只监听127.0.0.1:8896，本轮不开放公网、不修改旧8765/8876/8892。

未来上线至少单独完成：HTTPS和安全Cookie/可信代理、域名与TrustedHost配置、用户账号开通、日志正文及Authorization脱敏、频率/并发控制、备份，以及多进程会话/Key隔离方案。当前为单进程临时内存方案，不能直接开多worker，也没有实现跨重启加密保存Key。只用浏览器“记住密码”不能替代服务端密钥管理。

现有原生外发许可门保留；账号/ACL变更的跨进程一致性等既有限制仍在，不声明真实机密数据生产外发安全已经通过。个人Key不会修复这些限制。

## 验证

使用合成Key与内存模拟HTTP，验证会话隔离、不继承全局Key、退出/清除、票据失效、请求进行中禁止换Key、HTTPS/回环限制、无效输入不回显和恶意接收地址阻断。真实DeepSeek HTTP请求数为0。

标准全套、前端构建、真实浏览器配置/清除及四岗位回归、两库数据完整性详见本机验收报告。真实Key有效性、真实模型结果及费用本轮未验证，不沿用历史D1/D2成绩冒充本功能验收。
