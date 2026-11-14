# P18 文件管理前端

源自 junyisong01-glitch/P18new 的 43a8afb，React + TypeScript + Tailwind。已替换 Supabase 数据访问与模拟处理逻辑，所有请求发往同源 P18 API。

在本目录执行 `npm ci`、`npm run typecheck`、`npm run build`。构建产物位于 ../web/library，由 FastAPI 的 /library/ 提供；不需要另起前端开发服务器。登录入口 /login，需要独立数据目录启用权限模式并创建可信账号。

禁止把 .env、node_modules、实际文档和测试账号加入版本库。分类权限由后端决定，前端身份标签不能切换权限。知识检索/问答链接接入已有工作台；这两个页面的视觉升级仍待后续迭代。
