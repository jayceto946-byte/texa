# 笔记顶部栏与教材侧栏修复验收

环境：macOS / Electron 37，当前 Texa_MacOS 工作树。生产 frontend/dist，临时 userData，只读接口夹具；没有访问正式教材/笔记存储或调用模型。复现脚本：`scripts/qa-notes-books-chrome-electron.mjs`。

## 改动与测量

- 修复前，笔记列表、阅读、编辑的 header top 均为 32px，教材及目标页为 0；笔记额外使用单独的原生标题条和侧栏位移。移除这组专属布局，使其与其他主页面共享顶部行。
- 笔记各状态标题改用公共 app-page-title。修复前后本夹具计算出的字体均为 HarmonyOS Sans SC、16px、600；本次统一公共样式入口，未宣称测得字体家族变化。
- 1280×820 和 1024×768 下笔记三种页面与教材均为 top=0、height=48px；760×820 下均为 top=0、height=56px。标题字号和字重一致，无页面水平溢出。
- 教材的侧栏展开按钮原先在路由正文之前渲染，与后续 header 的 Electron drag 区重叠；现在在正文及 Inspector 之后渲染，保持 no-drag 和同一侧栏状态。DOM 点击无法单独证明原生拖拽命中正确，因此另做原生鼠标验收。

## 实际验证

- 自动化共 51 项检查通过，无 renderer 异常：三档尺寸、笔记列表/阅读/草稿编辑、教材导航每档 3 次收起/展开、教材分类重新展开、Enter/Space 键盘操作、真实 macOS 全屏进入/退出、缓存笔记后 SPA 返回教材。
- CUA 原生鼠标坐标输入（Retina 截图坐标）：在独立 TexaChromeQA 测试窗口，点击教材展开按钮 (246,48) 后 AX 出现“收起侧栏”和“教材分类”；点击收起按钮 (404,52) 后出现“展开侧栏”；再次点击 (246,48) 成功展开。SPA 进入笔记后，同坐标收起并重新展开也成功。最初一次 (203,124) 点击位于按钮之外，无状态变化，不计为功能失败或通过证据。
- 前端 lint、生产构建通过；52 个测试文件、243 项测试通过。既有 MathLive 大 chunk 提示保留。
- 未测试 Windows 原生鼠标与窗口拖拽。760px 下目标页既有高度为 57px，本次不调整目标页；笔记与教材的 56px 一致性有单独断言。

完整测量见 [修复前](before/results.json) 和 [修复后](after/results.json)。截图位于同名目录；例如 [760px 笔记编辑](after/760-draft.png)、[1280px 笔记阅读](after/1280-detail.png)、[教材收起](after/native-books-closed.png)。
