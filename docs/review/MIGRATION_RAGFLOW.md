# 迁移方案 B：用 RAGFlow 替换 P18 自研主体

状态：决策已定（2026-11-14）。本文只描述"换成 RAGFlow 之后长什么样、怎么迁、怎么验收、怎么回滚"。
P18 代码保留在 `codex/p18-demo-v1-review-20261114` 与 `codex/p18-docling-parser`，不删除、不覆盖。

## 1. 这次替换换掉了什么

| 能力 | 迁移后 | 说明 |
|---|---|---|
| 文档解析（PDF/DOCX/XLSX/扫描件） | RAGFlow DeepDoc | 比自研强：版面、OCR、表格识别 |
| 切分 | RAGFlow 模板切分 | 不再有 E1/E2 自研规则 |
| 向量 + 关键词检索 | RAGFlow 混合检索 | 不再有自研 BM25/RRF |
| 问答界面 | RAGFlow 自带 Chat | P18 三套前端下线 |
| 账号 | RAGFlow 账号体系 | 不再是四岗位 + 密级 |
| **行级 ACL** | **取消** | 换成"一个密级一个 dataset"，只到 dataset 粒度 |
| **逐份外发授权** | **取消** | 问答直接调模型，无人工证据确认 |
| **只读第二知识库** | **取消** | 需要重新建索引 |
| **Excel 行级溯源/结构化预览** | **取消** | RAGFlow 给的是表格文本，没有 `sheet!r2c1` |

> 这四项不是"以后补"，是本次明确裁剪。申报表第 6 条本来就写着"不做企业账号权限体系"，所以裁剪与申报口径一致；但如果对外仍宣称有权限/外发控制，属于虚假陈述。

## 2. 目标架构

```
浏览器 ──► RAGFlow Web (80) ──► ragflow server (9380)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        Elasticsearch         MySQL 8.0            MinIO
        (文档块/向量)         (元数据/账号)        (原始文件)
              │
              └──► 模型服务（DeepSeek 云端 或 本地 Ollama/vLLM）
```

对比现状：从"一个 Python 进程 + SQLite + 本地 Qdrant"变成"5 个容器 + 外部模型服务"。

## 3. 部署（已在 macOS + colima 上验证）

```sh
colima start --cpu 6 --memory 12 --disk 60
colima ssh -- sudo sysctl -w vm.max_map_count=262144
cd docker && docker compose -f docker-compose.yml up -d
# 访问 http://127.0.0.1/ ，首次注册管理员
```

- 磁盘镜像走国内镜像源（`docker.m.daocloud.io`），Docker Hub 直连不通。
- 官方建议 4C/16G；实测 6C/12G 可启动，解析大文件会吃紧。

## 4. 数据迁移

```sh
.venv/bin/python scripts/export_to_ragflow.py --data-dir runtime/demo-v1-experience      # dry run
.venv/bin/python scripts/export_to_ragflow.py --data-dir runtime/demo-v1-experience --push \
    --api-base http://127.0.0.1 --api-key <RAGFlow API Key>
```

映射规则：

| P18 | RAGFlow |
|---|---|
| `library_metadata.classification` | dataset 名（公开 / 内部 / 机密 / 未分类） |
| 原件 `files/<id>/original.*` | 原样上传，不转换 |
| `state in {deleted, superseded}` 或 `characters=0` | 跳过，输出在 `skipped` |
| chunks / 向量 / 索引 | **不迁移**，由 RAGFlow 重新解析建索引 |

导出的只是目录与原件，不含账号、会话、聊天、许可记录。

## 5. 验收清单

1. 三个样例文档（PDF/DOCX/XLSX）上传后解析成功，块可读
2. 检索接口 `/api/v1/retrieval` 返回带文档名与块的命中
3. Chat 能基于命中回答，引用可点开
4. dataset 隔离有效：A 数据集账号看不到 B 的文档
5. 断网后本地模型仍可问答（若用 Ollama）
6. 明确记录：无行级 ACL、无外发确认、无 Excel 行号

## 6. 回滚

- P18 代码与数据目录不动；RAGFlow 全部在 `/tmp/ragflow` 与 Docker 卷内。
- `docker compose down` 即停，不影响 8896。
- 双跑期建议 2 周：旧系统只读，新系统接新资料。

## 7. 工期

| 阶段 | 内容 | 人日 |
|---|---|---|
| D1 | 起栈、跑通上传解析检索 | 1–2 |
| D2 | 迁移导出 + 批量解析 30 份 | 1–2 |
| D3 | 接模型（DeepSeek/Ollama）、调检索参数 | 2–3 |
| D4 | 验收脚本 + 文档 + 口径更新 | 1–2 |
| 合计 | | **5–9 人日** |

## 8. 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| 容器栈成为新的运维负担 | 单机演示变重 | 明确"演示机"定位，不做生产承诺 |
| 模型仍需外发 | 文档会发给 DeepSeek | 用本地 Ollama 即全本地，但要额外机器/显存 |
| 失去权限/外发边界 | 不能再说"机密不外发" | 交付文档与申报口径同步改，禁止沿用旧说法 |
| 重建索引 | 既有 30 份库成绩不可复现 | 把旧成绩标注为"迁移前历史记录" |
