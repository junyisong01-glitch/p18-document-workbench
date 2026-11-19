# 长期企业演示部署（尚未上线）

目标是一台独立 Linux x86_64 云服务器运行真实 FastAPI、两套持久化资料/索引和本地 Ollama。企业方通过 HTTPS 和14张演示身份卡体验业务。此配置不用于接入真实企业生产资料：公开老板卡可管理这套演示资料，所有访问者共享演示库状态。

建议先选普通 CPU 4核16GB、100GB SSD 作为低并发演示起点（非性能保证），暂不买 GPU；优先实际试用再决定升配到8核32GB。1核2GB/2核4GB不适合同时运行现有检索和本地回答。CPU问答可能明显慢于你的Mac，首次索引和并发速度必须云端实测。

用户仅有个人主体，本次采用中国香港地域、Ubuntu24.04 LTS（需在云控制台确认当时可购规格和网络）；先核对月付与短期试运行费用，不购买GPU。香港节点无需中国内地ICP备案，但大陆访问可用性与速度必须实测；不保证所有企业网络均可访问。个人主体可否按科研/作品展示办理内地备案需由云商结合实际内容确认，本次不按个人博客名义虚假申报企业产品。费用包含主机、磁盘、公网带宽/流量和快照，不能只比较主机价格。具体价格以下单页为准，当前没有开通或收费资源。

## 启动条件

1. 用户自行开通云账号并支付服务器费用；准备仅供本次部署的SSH公钥访问，不要在聊天中发送云主账号密码、AccessKey或私钥。
2. 服务器绑定公网IP，域名A记录指向该IP；域名填入本目录`.env`的P18_DOMAIN。开放80/443，SSH仅限维护者；不开放8896、11434或数据库端口。
3. 按Docker官方说明安装Engine与Compose插件。本配置使用Linux host网络；不适用于Docker Desktop或共享宿主机。
4. 上传经export_bundle.py生成的完整包，解压到全新目录。包包含已授权虚构演示资料，不携带旧会话、邀请、密码或个人Key，也不携带Mac依赖与模型权重。

```sh
cp deploy/cloud/.env.example deploy/cloud/.env
# 编辑域名后，以下命令均在解压根目录执行：
sudo chown -R 10001:10001 runtime
docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml build
docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml up -d ollama
docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml exec ollama ollama pull qwen3.5:4b
docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml up -d
docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml ps
```

首次下载公开模型需要网络。运行期使用原检索模型固定revision及qwen3.5:4b，16384上下文；本地回答失败不自动外发。演示库DeepSeek仍需登录后配置Key、逐份许可和人工确认；启辰禁止外发。云端首次依赖版本若导致索引配置变化，只能原生重建，不能改hash冒充已有索引有效。

外部入口为`https://实际域名/`。Caddy自动申请证书，原后端只监听回环；独立gateway验证精确HTTPS来源、回环代理、自定义请求头，补充Secure Cookie和登录限流，再进入保持原规则的原生API。此opt-in入口不会用于你本机8896。卡片临时口令仍只用一次，不复制真实密码，需明确点击登录。

## 验收后才可发企业方

- 外网手机/另一网络打开，无证书警告；14卡片可填入并登录、角色/部门正确。
- 两库文档、原文预览、检索和引用正确；启辰外发403，演示库未勾选不能发送。
- 独立虚构文件完成上传→审核→索引→发布→检索；新版发布替换旧版，员工不能越权。
- 真实本地问答验证速度与拒答；重启容器后文件、账号、审计仍在。
- 只对外开放80/443，日备份runtime及模型卷配置，验证恢复。不要运行`down -v`清数据。

本机没有Docker，也没有已授权云主机。本轮只能完成入口单元测试、脱敏打包和本机原生链路测试；镜像构建、Linux兼容、TLS签发、云端性能及外网验收必须在服务器到位后执行，不能将该包称为已经上线。

本轮源码已包含正式工作台最新表格检索、8910确认区及会话内Ollama/DeepSeek选择。公网模型说明指云服务器内的私有Ollama，不宣称运行在访客电脑上。云端推理超时设为允许范围内120秒；实际CPU速度仍待服务器实测。香港免内地ICP备案的依据：https://help.aliyun.com/zh/icp-filing/basic-icp-service/support/server-check-faq 。


## 2026-11-18 云部署地域选择更新

用户因香港ECS报价约700多元/月而要求降低费用，已取消国内可访问的硬性要求，希望加快上线；支付方式仅支付宝或微信。暂停香港ECS购买，继续用已实名认证阿里云账号，优先核对轻量应用服务器国际型、新加坡、4核16GB/80GB的实际库存和月付总价。官方规格swas.s.c4m16s80i1.linux支持该配置；80GB可作为演示起点，共享CPU问答速度和公网质量须实测，不承诺切换地域就更快。已打开轻量控制台入口，未购买或创建资源。现有Compose、本地Ollama、DeepSeek入口和启辰外发禁令保持。原v3归档仍可部署，地域推荐更新见本条。依据：https://help.aliyun.com/zh/simple-application-server/product-overview/instance-families/ 。
