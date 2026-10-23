# Logo 与教材目录交互验收 — 2026-10-23

真实 macOS Electron + 生产 renderer，使用临时 userData 与进程内目录/教材/对话夹具。没有访问真实学习数据或调用模型；保存目录只写入 QA 服务进程内存。辅助 POST `/api/mistakes/chat-sources/query` 为只读查询，由视觉夹具响应。

## 最终结果

- `after/results.json`：67/67，通过。`after/requests.json` 为请求记录。
- 1280×820、1024×768、760×820：移除分类标题与分类省略号；右键未选学科、键盘打开科目菜单、重命名、跨父学科删除科目、删除空学科、有教材目录禁用删除、添加两类目录均通过；菜单未被滚动容器裁剪，Escape 返回触发条目。
- Logo 从对话返回起始页、清空草稿、移除旧会话 URL；1280 档额外从缓存教材页点击 Logo 返回，验证保留挂载的学习页可重置。
- mineral、graphite、clay、notebook、codex：添加控件透明、1px浅边框、整组居中、间距12px；桌面按钮32px高/13px字/16px图标，与学科行一致；760档36px高，与当地学科行一致。
- 长中文目录名称截断且不导致页面横向溢出；显式保存后重新加载可读到内存夹具的更名结果。菜单方向键与外部点击关闭通过；无renderer异常。
- 前端53文件/251项通过，相关ESLint、TypeScript/Vite构建通过；保留原有大chunk构建提示。
- 提交前另用HEAD与暂存UI补丁导出独立候选，复用既有依赖：52文件/249项、TypeScript/Vite通过。首次仅导出frontend导致UI合同测试缺少`desktop/loading.html`；补齐HEAD中的桌面文件后通过。独立候选未包含工作区其他未提交差异。
- 上一轮对话顶部/历史记录/计时器 Electron 回归56/56通过，结果保留在相邻 `chat-header-history-2026-10-23/after/`。

## 可复现入口

`scripts/qa-library-context-electron.mjs before|after` 使用前端当前 `dist` 与本地 Electron，依赖 Playwright。前后截图在 `before/`、`after/`；`1280-books.png` 为默认主题最终按钮布局，各主题的 `*-theme.png` 包含菜单。

窄窗口初测发现滚动将条目带入视野后，已排队的 scroll 事件误关刚打开的菜单。最终实现比较触发条目祖先的实际滚动位置，仅在后续位移时关闭；复测通过。请求审计曾误把只读 POST 识别为写入，现按端点区分；原始失败不代表真实数据写入。按钮有色填充与缩小方案已按用户反馈撤回。

没有原生 Windows、安装包、真实模型或真实教材数据验收，不据夹具声明这些平台或模型已通过。
