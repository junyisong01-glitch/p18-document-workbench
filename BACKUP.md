# 单库切换备份与恢复

本机备份位于工作区 `.development/single-library-20261120/backup/`。演示库和启辰库各有 `documents.json` 清单、SQLite 快照、原文件与解析结果、向量目录和文件哈希。该目录含运行数据，应保存于本机。变更前的 8896 代码和静态资源另存于 `backup/program-before/`。

恢复步骤位于工作区 `.development/single-library-20261120/BACKUP.md`。常规回滚执行同目录的 `release.py restore`，恢复原程序和配置并重启；保留当前数据库、原件和索引。运行数据仅在受损时从对应快照恢复。
