# 给部署同学：从 GitHub 部署均易工作台

本说明对应当前 `main` 的蓝白/深色暖灰双风格、部门身份卡片和启辰单库工作台。部署目标是**保留现有虚构演示资料的独立公网演示环境**。14 个演示身份可以体验包括管理层在内的权限，不用于存放真实企业资料。

## 你需要收到的东西

1. 本仓库的访问权限，克隆 `main`。
2. 项目持有人单独提供的 `p18-demo-data-20261123.tar.gz` 以及同名 `.sha256` 校验文件。资料包不在 Git 中；不要用旧 6+30 固定数量的 `export_bundle.py` 导出替代当前包。
3. 自己可管理的 Linux x86_64 服务器、域名和 DNS 权限。运行期主推理在该服务器的 Ollama，检索用固定版本 Qwen Embedding；不需要从项目持有人处拿 API Key。

不要复制开发者的 `.env`、虚拟环境、`node_modules`、会话或本机登录说明。源码、依赖清单、Docker/HTTPS 配置和导入工具均已在仓库中。

## 资料包包含什么

- 业务库全部文档记录，包括已删除/已下架/历史状态，存在的原件、解析结果、切分、元数据、审核/发布操作记录和已保留演示账号的借阅授权。
- 14 个演示身份及其部门、岗位；旧密码摘要已替换为随机新摘要，只能通过新环境的演示身份入口产生临时登录口令。
- 保留旧演示库资料用于历史维护；当前界面仍只显示启辰业务库。
- 清除旧会话、邀请、登录尝试、非演示账号、外部调用审计/设置/授权和反馈内容；不含个人 API Key、日志、模型权重。
- 不携带本机 Qdrant 和旧索引成功记录。服务器按原模型重建索引，完成之前不能称为可检索。

资料包仍包含文档正文和操作记录，请通过双方认可的私密渠道传递。它是部署数据，不要提交到 GitHub，也不要放到公开 Release。

## 第一次部署

推荐独占 Ubuntu 24.04 LTS x86_64，安装 Git、Python 3.12、Docker Engine 与 Compose v2。此 Compose 使用 Linux host 网络，不适用于 Docker Desktop。模型运行需要足够内存和磁盘；原演示方案以 4 核 16GB、80–100GB 磁盘为低并发试运行起点，是否足够须服务器实测。构建时需要能下载 npm/PyPI/基础镜像，初始化模型时需要访问 Hugging Face 与 Ollama 模型仓库。

服务器只开放 HTTP/HTTPS 80/443，SSH 限维护者；8896、11434 和数据服务不要暴露公网。域名 A 记录指向服务器；使用 AAAA 时也须保证 IPv6 正确可达。

下面命令在全新目录执行。`/secure-transfer/` 是示例路径，替换为实际收到资料包的目录。

```bash
git clone https://github.com/junyisong01-glitch/p18-document-workbench.git
cd p18-document-workbench
git switch main
python3 deploy/cloud/preflight.py --source-only

# 对照发送者提供的 SHA256；不是仅相信同一陌生来源的校验文件。
cd /secure-transfer
sha256sum -c p18-demo-data-20261123.tar.gz.sha256
cd -
DATA_SHA=$(awk '{print $1}' /secure-transfer/p18-demo-data-20261123.tar.gz.sha256)
python3 deploy/cloud/runtime_bundle.py import \
  --archive /secure-transfer/p18-demo-data-20261123.tar.gz \
  --sha256 "$DATA_SHA" --runtime ./runtime

cp deploy/cloud/.env.example deploy/cloud/.env
# 编辑 P18_DOMAIN 为实际域名，不带 https://、端口或路径。
# P18_IMAGE_TAG 建议填写下面命令输出的提交短号，便于保留旧镜像。
git rev-parse --short HEAD
nano deploy/cloud/.env
python3 deploy/cloud/preflight.py
sudo chown -R 10001:10001 runtime

# 后续命令统一从仓库根目录执行。
dc() { docker compose --env-file deploy/cloud/.env -f deploy/cloud/compose.yaml "$@"; }
dc config --quiet
dc build app
# 镜像会在 Node 构建阶段 npm ci + build，无需上传电脑上的编译环境。
dc up -d ollama
dc exec ollama ollama pull qwen3.5:4b
dc run --rm --no-deps prepare-model
dc up -d app https
dc ps
dc logs --tail=100 app https
```

不要提前创建空 `runtime` 后再导入：导入器拒绝覆盖已有目录。若导入时发现目录已存在，先核对是否已有业务数据，不能直接删除。

首次访问 `https://实际域名/login`，选择身份再点登录。首次进入业务库会初始化本地索引服务并重建索引，CPU 机器可能需要较长时间。模型未准备好时，应看日志修复，不要手改数据库将资料标记为“可检索”。

## 上线验收

- 在另一网络或手机上打开域名，HTTPS 无证书警告。
- 蓝白默认与深色暖灰切换正常；登录页按五部门展示身份，管理层和访客单列。
- 管理层、主管、员工、访客分别登录；访客看不到工作台/管理入口，跨部门未授权资料不能读取。
- 查看资料总量和原文、审核与发布记录，抽查部门和借阅权限。导入包记录数量包含删除记录，不应直接等同页面“可查阅资料”数量。
- 等索引完成后提问并打开引用原文，核对真实答案来源；再用虚构新文件检查上传、审核、自动发布与检索链路。
- 重启 `app` 后资料、账号与授权仍存在。确认已有资料不会因更新镜像被覆盖。
- `http://127.0.0.1:8896/__health` 仅说明入口进程存活，不证明索引或问答模型就绪，必须完成前述业务验收。

## 更新、备份和回滚

`runtime` 是宿主机持久化目录；模型与证书使用 Docker 命名卷。升级通常只更新 Git 代码和镜像，**不重新导入首次交接包**。

更新前记录 `git rev-parse HEAD`、当前 `P18_IMAGE_TAG`，并备份。为了让 SQLite 和原件一致，选择无文件处理中时暂停服务：

```bash
umask 077
BACKUP_TIME=$(date +%Y%m%d-%H%M%S)
dc stop -t 120 app https
sudo tar -czf "../p18-runtime-$BACKUP_TIME.tar.gz" runtime
sudo chmod 600 "../p18-runtime-$BACKUP_TIME.tar.gz"
# .env 单独私密备份；不要提交 Git。完成备份后可以先恢复旧服务。
dc up -d app https
```

备份应另存到服务器以外的安全位置；实际验证解压到新目录后能恢复原件和数据库。模型可重新下载，证书卷由 Caddy 管理；`docker compose down -v` 会删除命名卷，不用于日常更新。

升级：确认工作区无源码改动后 `git pull --ff-only origin main`，更改 `.env` 的 `P18_IMAGE_TAG` 为新提交短号，`dc build app`，然后 `dc up -d app https`。随后重新验收。若未来提交含数据库迁移，先按该版本迁移说明操作；本次仅提供现有应用启动时的建表/兼容升级，没有新增独立迁移框架。

回滚：回到此前**已在服务器验收**的代码版本和镜像标签。若已经改变数据库结构，必须连同更新前 `runtime` 备份恢复，不能让旧程序直接读取未知的新结构。先停止服务，把现有 `runtime` 改名保留，再解压备份、修正属主，最后启动；不要覆盖正在运行的数据目录。

## 常见问题

| 现象 | 检查方式 |
|---|---|
| 构建缺文件 | 必须完整克隆仓库。新 Dockerfile 不再依赖仓库外的 `CLOUD-DEMO.json`。 |
| 导入拒绝 | 核对 SHA256、目标 runtime 是否已存在；不要绕过校验或覆盖已有库。 |
| 文件权限错误 | 容器运行用户 UID/GID 为 10001，检查 runtime 属主和父目录权限。 |
| `bind source path does not exist` | 先导入资料，再启动 Compose；不会自动创建空库冒充已有数据。 |
| 模型下载失败 | 检查服务器出网与磁盘空间，重跑 `prepare-model` / `ollama pull`，不要换模型后伪造索引状态。 |
| 资料可看但问答不可用 | 等待重建索引，查看 `dc logs app`、`dc logs ollama`，分别检查检索与回答模型。 |
| 证书签发失败 | 检查 DNS、80/443、安全组、其他服务占用以及 AAAA 是否错误。 |
| 登录出现来源错误 | `.env` 中域名须与浏览器地址一致，通过 Caddy HTTPS 访问，不直接开放后端端口。 |

## 当前验证边界

资料包导出/校验/导入、源数据不变、脱敏、禁止覆盖及路径穿越检查可在本机验证；仓库提供 deploy/cloud/deployment-checks.workflow.example.yml 模板，可检查前端构建、Compose 和部署工具测试，手动触发还可构建 Linux 镜像。当前 GitHub OAuth 授权缺少 workflow scope，模板尚未启用，不声称远端CI已通过。仓库维护者使用有相应权限的账号，把模板复制为 .github/workflows/deployment-checks.yml 并提交后即可启用；手动部署无需等待此步骤。

交付时必须区分这些检查与真正云端验收：未完成的 Linux 镜像构建、模型下载、TLS、索引重建与公网问答性能，不视为已上线。旧 `README.md` 的固定 6+30 演示打包方式留作历史说明，本文件为当前 GitHub 交接入口。

部署实现参考：[Docker多阶段构建](https://docs.docker.com/build/building/multi-stage/)、[Compose启动依赖顺序](https://docs.docker.com/compose/how-tos/startup-order/)。
