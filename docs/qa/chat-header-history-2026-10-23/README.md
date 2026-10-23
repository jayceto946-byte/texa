# 对话顶部栏与历史列表整理

按用户标注截图调整显示与交互位置，不修改历史存储、会话排序、置顶/归档/回收站合同或专注计时权威。

- 删除常驻侧栏内重复的“学习 / 新对话 / 收起”工具条；保留全局侧栏收起按钮。历史浮层仍保留标题与关闭入口。
- 删除“置顶 / 最近对话”分组行；置顶仍在前，别针与该对话标题并列，读屏保留“已置顶”说明。普通记录与置顶记录使用相同间距。
- 有对话或教材图片工作区时，右上方显示“新对话”。它与学科选择字号一致、高度同为32px，触控场景保留44px。新建复用 ChatContext，移除来源定位 URL，清除当前输入/附件/图片选择并聚焦输入框；起始页不重复展示此按钮。生成/上传等忙碌期间按钮不可用。
- 新对话、专注计时、学科选择按顺序并列。计时器进入专门的 header slot，其他页面仍跟随既有 header。计时器出现时180ms轻微渐入/上移，状态刷新保留节点，不随倒计时重播；减少动态效果时关闭动画。
- 会话身份变化会取消侧栏未完成的历史读取，避免从顶部新建后迟到的历史响应重新切回旧会话。没有在 React state updater 内引入副作用。

## 验证

| 检查 | 结果 |
| --- | --- |
| 前端 `npm test` | 53文件 / 251项通过 |
| 修改 TSX 的 ESLint | 通过 |
| `npm run build` | TypeScript / Vite通过；保留既有 MathLive 大chunk提示 |
| `git diff --check` | 通过 |
| `scripts/qa-chat-header-history-electron.mjs before` | 修改前真实Electron三档基线截图 |
| `scripts/qa-chat-header-history-electron.mjs after` | 56项通过，无renderer exception；[原始结果](after/results.json) |

Electron 使用独立临时userData、只读API夹具和生产构建。1280×820、1024×768、760×820均检查：重复工具条/分组行消失，内联别针，统一记录间距，控件字号/高度相同，timer出现前后不重叠，弹层位于窗口内，键盘Enter新建、保留专注状态，以及置顶对话读取/菜单。另覆盖目标页timer并列、减少动态效果、收起后的历史浮层关闭、刷新不重新挂载timer、标题栏no-drag属性，无模型请求或学习写操作。

人工查看修改前1280基线、修改后1280计时、1024历史、760抽屉和目标页截图；阅读区正文轴、公式与输入框布局未调整。截图见 [before](before/1280-history.png)、[after](after/1280-timer.png)、[窄窗口](after/760-timer.png)、[目标页](after/goals-timer.png)。

QA脚本修正记录：首次导航需等Electron初次装载完成；渐入期间不能用临时transform测最终对齐；正文断言应定位markdown而非包含“学习问题”的整个article；窄窗口功能导航需要展开，选中对话后抽屉会自动收起，检查更多菜单前需重新打开。相关失败是夹具时序/定位问题，不通过放宽产品条件处理；部分早期记录保留于 `after/fixture-navigation-failure.json`，最终56项结果独立保存。

未运行原生Windows、正式安装包或真实模型/用户数据验收。
