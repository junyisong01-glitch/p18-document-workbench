# 文档格式与低成本部署

此批新增 TXT、Markdown（.md）、CSV、旧版 XLS、JPG/JPEG、PNG。复用既有上传、权限、异常复核、发布、版本、切分、索引和原件下载流程。未购买服务器、未启用外部识别 API、未增加独立服务。

## 格式能力

| 格式 | 读取和预览 | 边界 |
| --- | --- | --- |
| TXT | UTF-8（含 BOM）、带 BOM 的 UTF-16、GB18030；段落与原始行号 | 不猜测其他编码，异常需重新导出 |
| Markdown | 保留标题、代码围栏和原始文字，表格按行列预览 | 原始 HTML 和代码作为文字，不执行；不抓取链接或外部图片 |
| CSV | 分隔符识别，保留引号内逗号、换行和前导零；复用表格预览 | 表头通过保守规则识别，不确定时复核；公式样式字符串不执行 |
| XLS | 读取工作表、保存的单元格值和格式；复用表格预览 | 不还原公式表达式、图表或嵌入对象，保留提示并需复核 |
| JPG/JPEG、PNG | 根据 EXIF 纠正方向、生成预览并执行本机 OCR；原文件不改写 | 仅识别文字，不承诺理解工程图、手写或复杂图片表格 |

识别无文字、失败或乱码不会虚构可检索内容。低置信度结果走解析异常。表格内容的可信度、发布权限及跨部门范围继续由现有后端判断。

## 费用与资源控制

- 解析无按文件/页/字符计费接口，使用本机开源库或系统识别能力。仍需承担服务器、磁盘、备份、索引/问答模型等既有资源成本。
- 现有解析进程池最多并行 2 个；单文件 20 MB，单批最多 20 个、100 MB；解析作业 180 秒超时。
- PDF 200 页；文本 200 万字符；表格最多 50 工作表、20000 行、256 列、10 万单元格。
- 独立图片最多 2000 万像素、单边 12000 像素；OCR 渲染最长边 2400 像素；单页 30 秒、单文件 OCR 预算 100 秒。首个编译或等待锁也占用作业总时限。
- 相同内容上传沿用已有去重流程，不重复解析。macOS Vision 辅助程序按源码哈希缓存在 `P18_DATA_DIR/ocr-tools`，缺省位于项目 `runtime/ocr-tools`；并发编译加锁，成功后原子替换。缓存只含程序，图片在临时目录处理。
- Tesseract 每个识别进程 `OMP_THREAD_LIMIT=1`；缺少引擎/语言包时报异常，不自动改用付费服务。

## 本机测量（2026-11-22）

Mac 上以独立虚构样本测试；不包含向量化、模型回答、数据库和 Web 服务常驻内存，不能用来直接承诺云端容量或月费用。

| 样本 | 解析时间 | Python 解析进程峰值 RSS |
| --- | ---: | ---: |
| 小型 TXT / Markdown / CSV / XLS | 0.05～0.09 秒 | 76～77 MiB |
| 5000 条设备记录 CSV（约 149 KB） | 3.61 秒 | 93.3 MiB |
| 1600×650 图片，OCR 程序已缓存 | 0.24 秒左右 | 97 MiB 左右 |

图片测试中，缓存前每个文档需重新编译，约 25～27 秒。缓存方案首次初始化实测 40.79 秒，编译/OCR 子进程峰值 RSS 约 1106 MiB；随后复用时 OCR 子进程峰值约 78 MiB。父、子进程峰值不是同一时刻的总内存，不能简单作为整机预算。首轮结果受其他并发验收影响。Linux 上无需 Swift 编译，但 Tesseract 的速度和中文识别效果必须另测。

复测命令：

```sh
.venv/bin/python scripts/benchmark_formats.py /绝对路径/样本.txt /绝对路径/样本.png
```

每份文件在独立进程中运行，输出耗时、父/子进程各自峰值、识别字数及异常数。仅测解析，不上传或发布文件。

## Linux 上线准备

`deploy/cloud/Dockerfile` 已添加 Tesseract 和简体中文、英文语言包；compose 明确使用 `P18_OCR_BACKEND=tesseract`。保留原有 CPU 模型部署，不增加 GPU 服务。单独安装可参考：

```sh
apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

支持 `P18_OCR_BACKEND=auto|vision|tesseract`，auto 在 macOS 选择 Vision，在其他环境选择 Tesseract。当前开发机没有 Docker/Tesseract，Linux 配置和调用契约有代码测试，尚未完成 Linux 容器构建、实际 OCR 准确率及整机负载测试。上线前必须在目标环境用真实规模的脱敏样本复测，尤其是并发上传与本地问答同时运行的内存。此批不直接部署公网，也不据样本结果推荐购买配置。

参考：[Python CSV](https://docs.python.org/3/library/csv.html)、[xlrd 能力边界](https://xlrd.readthedocs.io/en/latest/)、[Tesseract 安装和语言包](https://tesseract-ocr.github.io/tessdoc/Installation.html)。
