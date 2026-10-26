# 设置、侧栏动效与历史读取修复（2026-10-26）

本轮在 Texa_MacOS 当前检出修改。未暂存、提交或推送，未触碰搁置功能的实现与运行开关。

## 修改与原因

- 数据与教材：移除 MinerU API URL、CLI 与“保存解析配置”入口及其前端状态/请求。此页不再为已移除的解析配置读取整份模型设置。提示导入已有 Markdown/图片的 ZIP；教材导入默认选中“MinerU 输出包（推荐）”。现有 PDF 兼容路径及后台解析接口保留。
- 设置动效：保留挂载的 Dialog 在关闭时移除进入动画类，重开时重新播放；设置分类通过 Web Animations 播放轻微淡入/位移，不重挂载表单。遵循减少动态效果偏好，保留焦点回归、Escape、焦点锁与未保存模型草稿的确认。
- 侧栏：移除关闭时的 display:none/contents 切换，让实际宽度从导航宽度过渡到 0；内部导航平移淡出，关闭时 inert。浮动历史独立可用。两种折叠按钮共用标题栏中心线；桌面 48px 标题栏与窄屏 56px 标题栏分别计算，窄屏保留 44px 点击区域。
- 历史列表：数字和首次读取改用骨架屏，去掉“加载中/正在读取会话”文字闪现。按完整教材范围与分类保存最多 12 份、30 秒有效的内存摘要页缓存；分类返回复用列表、数量与分页游标，过期时先显示快照再更新。会话变更、回答完成、重试或连接身份变化使缓存失效；连接变化同时清除显示快照。错误保留可用记录，迟到请求不覆盖另一分类。
- 后端：合并最新范围、统计与首问摘要的读取，教材/学科过滤先于聚合，批量读取管理元数据；一次性导入标记先批量读取，已导入 JSON 不逐文件查询。列表与详情连接确定关闭。没有数据库 schema、索引、依赖或存储格式迁移，保持原置顶排序、游标世代、管理 CAS、回收站与消息事件规则。

## 已完成验证

- Python 3.10：会话管理、事件存储、追问与并发 60 项通过。新增覆盖多教材旧范围隔离、最新范围首问/统计、无范围会话、后出现的旧 JSON 一次导入、坏兼容文件不污染权威数据，以及批量读取不随会话数增加 SELECT 次数。
- 前端 54 文件 / 254 项通过；ESLint、TypeScript 和生产构建通过。保留既有 MathLive 包体积提示。缓存测试覆盖范围隔离、TTL、过期可见快照、容量、游标和失效。
- 真实 macOS Electron：1280×820、1024×768、760×820，51 项通过，零 renderer error。服务仅使用隔离 HTTP 夹具，并人为延迟列表 400ms；包含实际中间宽度、标题栏中心线、设置首次/重开/分类动效、减少动效、首次骨架屏、缓存无重复请求、分页返回、读取失败及重试、迟到分类响应、选取旧会话与浮动历史。
- 既有会话历史竞态脚本另跑 12 项通过：向前/向后分页迟到、同 ID 内容替换、去重、三尺寸公式与溢出。
- 已实际查看设置三尺寸、历史实内容/骨架屏、折叠后的教材页面和浮动历史截图，并对照已有学习/教材视觉参考。修改前截图在 before/；最终截图为根目录按尺寸命名的 PNG，races/ 保存公式与会话竞态截图。failure.png 和 *run*.json 是保留的前轮记录，不代表最终结果。

## 速度证据与限制

最终交替配对基准使用同一个临时 SQLite：500 个会话、20,000 条合成消息、九组有效前后交替采样，对比提交 d69a4b3 的原函数与本轮函数；逐次检查完整第一页及游标相同。结果见 backend-paired.json：中位 25.00ms → 21.80ms，减少约 12.8%。backend-before.json / backend-after.json 为早期探索轮，最终结论以配对结果为准。

Electron 模拟 400ms 列表延迟时，返回已有分类的操作到行可见为 25/39/43ms，且没有再次发出列表请求。这是隔离渲染与缓存行为测试，不代表真实用户库或手机网络端到端速度。没有连接生产学习数据、调用模型、升级依赖或发布安装包；Windows、真实 iPad 远程链路未实测。

## 验收夹具修正记录

前轮依次暴露了窄窗口需要展开“功能与设置”、其标题栏实际为 56px、初始 Electron 导航尚未完成、来源选择控件语义为 radio，以及短动画在机器负载下已完成导致的采样误报。最后的 renderer 异常由夹具用无 detail 的普通 Event 模拟 conversations:changed 造成；按生产 CustomEvent 的 id/management 合同修正后零异常，没有放松生产监听器或错误断言。初始轮和修改记录保留在 electron-first-run.json 至 electron-eighth-run.json，最终证据为 electron-results.json。

## 复现

```sh
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
venv310/bin/python -m pytest -q tests/test_conversation_management.py tests/test_conversation_event_store.py tests/test_conversation_followup.py tests/test_conversation_memory_concurrency.py
PYTHONPATH=. venv310/bin/python docs/qa/settings-history-motion-2026-10-26/benchmark.py
NODE_PATH=/absolute/path/to/node_modules node scripts/qa-settings-history-motion-electron.mjs
NODE_PATH=/absolute/path/to/node_modules node docs/qa/settings-history-motion-2026-10-26/history-races.mjs after frontend/dist
```

Electron 脚本需要已有 Electron 和 Playwright、回环监听权限；每轮建立独立临时 userData，不读取正式学习库。夹具来源位于 scripts/visual-preview-server.mjs。
