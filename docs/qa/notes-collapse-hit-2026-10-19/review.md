# 笔记侧栏鼠标命中修复

用户当前检查窗口，macOS ARM64 / Electron 37，当前 Texa_MacOS 工作树。继续使用 texa-ui-system。

复现：笔记库点击收起正常；收起后直接以鼠标坐标点击可见图标，无状态变化；AX 激活同一按钮可以展开。DevTools 只读诊断显示按钮 rect=(16,41,30,30)，DOM elementFromPoint 命中图标，按钮 no-drag，而笔记 header 的实际计算值为 drag。说明 DOM 命中检查不足以验收 Electron 原生拖拽区域。

产品仅增加 notes.css 的 macOS 笔记 header no-drag 规则。需覆盖共享 macOS header 规则的 specificity；原生顶部 32px drag 区保持原实现。无布局、业务、依赖或令牌变更。

已在同一检查窗口实际坐标点击验证：笔记库、笔记阅读、笔记编辑均可收起并重新展开；Tab 可以聚焦展开按钮，回车可展开。编辑样本未修改正文或发布正式版本。检查窗口已刷新并留在阅读页，未关闭。

- [修复前原生窗口](before-native.png)
- [修复后阅读页收起](after-reading-closed.png) / [展开](after-reading-open.png)
- [编辑页收起](after-editor-closed.png) / [键盘焦点](after-keyboard-focus.png)
- [原生操作记录](native-checks.json)
- [构建输出](build.log) / [笔记测试输出](note-tests.log)

保留此前三档尺寸证据，本轮未重跑三档全流程或 Windows。此前仅 AX 激活的侧栏通过判断已明确更正；截图本身不能证明点击有效。构建既有 MathLive 大 chunk 提示仍在。
