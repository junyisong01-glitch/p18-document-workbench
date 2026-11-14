# 只读第二数据源配置

分享版默认禁用，不提供真实文档ID、ACL、文件名、原件、数据库或向量。运行版的真实ACL只在原Mac本地，不应上传。

经资料所有者授权后，可在本机config/qichen-libraries.json填写下列结构（真实配置不要提交）：

```json
{"enabled": true, "data_dir": "runtime/authorized-readonly-data", "acl": {
 "synthetic-uuid": {"code": "SYNTHETIC-01", "file_sha256": "original-file-sha256", "roles": ["研发", "测试"], "pending_confirmation": false}
}}
```

真实data_dir要指向已有、有效且兼容本代码的workbench.sqlite3及files/qdrant；使用完整四岗位映射与原件哈希，不用本例自动放行任何真实文档。推荐在自己检出目录内部放置经授权数据，路径按当前工作目录解析。原十五份roles为null时沿用数据库中的部门/密级规则；EXT按明确的roles控制。EXT-13对运维持续拒绝，业务确认之前不能仅修改表格绕过代码中的拒绝。

两库使用同一正常登录库；新账号通过scripts/create_library_account.py交互创建，身份可选启辰研发/测试/运维/生产岗位。不提供预置密码。不创建隐藏全权限身份。

生产运行需额外的用户管理、权限变更流程及部署评估；本分支仅本地虚构数据演示。只读加载器依赖当前qdrant-client==1.19.1本地存储接口，后续升级须重新测试，不能自动重建原索引。
