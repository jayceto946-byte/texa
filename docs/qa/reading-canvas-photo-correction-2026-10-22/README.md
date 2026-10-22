# 图片问答 Reading Canvas 修正 · 2026-10-22

修正上一轮将图片布局参考扩展成问题气泡的问题。图片问题现在与普通文字问题使用相同的 Reading Canvas 标题排版，没有底色、气泡圆角或独立内边距。图片置于问题下方，沿正文左边缘对齐；保持自然宽高比，最大宽 480px / 高 280px，不再放进右侧 104px 方框。点击看原图和 Escape 关闭保留。

## 实际验证

从经过审阅的真实暂存区导出隔离源码，复用已有依赖：ESLint、TypeScript/Vite 构建通过；既有 MathLive 大 chunk 提示保留。真实 macOS Electron 生产渲染器三档尺寸 **89 项通过**，无页面异常或失败夹具响应。[结果](results.json)、[验证范围](validation.json)。

新增检查直接比较文字问题和图片问题的字体、字重、行高、内边距及表面样式，验证图片位于问题下方并沿正文轴对齐。采用 1600×180 横向题目及 480×960 竖向解答 SVG 夹具，检查自然比例、尺寸上限、按需加载原图、选择复制和原图关闭。复习页面复验上传、刷新恢复、批改展示及用户确认。

| 窗口 | 横向题目 | 竖向解答 | 点击原图 |
|---|---|---|---|
| 1280×820 | [截图](1280-chat.png) | [截图](1280-chat-portrait.png) | [截图](1280-original.png) |
| 1024×768 | [截图](1024-chat.png) | [截图](1024-chat-portrait.png) | [截图](1024-original.png) |
| 760×820 | [截图](760-chat.png) | [截图](760-chat-portrait.png) | [截图](760-original.png) |

[窄窗口图片重做](760-redo.png)。图片内容为排版夹具，不代表真实识图或模型批改。第一次测量竖图时，图片先于惰性正文完成加载，测量脚本读取空节点而中止；补齐正文等待后完整重跑通过，应用代码未因此增加逻辑。

复现：先运行 `npm --prefix frontend run build`，再以可用 Playwright 的 NODE_PATH 执行 `TEXA_QA_OUT=/private/tmp/texa-reading-canvas-qa node scripts/qa-desktop-photo-review-electron.mjs`。脚本使用隔离 API 和临时 userData，不调用模型、不访问正式学习数据。未测试原生 Windows、在线模型或安装包。
