# 复杂交互整改与验收 · 2026-10-12

用户选定的本批范围：笔记冲突恢复、习题候选导入、聊天图片附件与回答来源浮层。复用 QA Inventory、现有截图、qa-live-server.py / qa-live-e2e.mjs / qa-check.py，不新增依赖或审计平台。既有 Mobile S2 改动保留，未提交/推送。

## 发现与整改

|对象|整改|实际验收|
|---|---|---|
|笔记草稿|存储失败、草稿 revision 冲突、正式笔记版本变化分别呈现；一个主恢复动作，错误详情可折叠|503 后保留正文、阻止离开；重试保存；草稿CAS409复制本地修改后载入权威草稿，冲突提示清除|
|正式笔记冲突|旧保存禁用；复制成功后读取最新正式版本，建立基于最新 revision 的编辑草稿；旧草稿保留；恢复期间冻结字段；已归档则只打开阅读|复制失败及最新读取503均保留原编辑器和正文；revision2未被覆盖；人工整合后发布revision3；已归档恢复保留草稿并进入阅读|
|习题候选|来源准备与校对阶段分开；来源/原文可返回查看；校对区域取得主要空间；正常布局页底唯一确认导入按钮；保留警告和解析置信度；八类编辑字段有持久可见标签|真实Word提取2题与独立答案配对2/2；未经确认题库无写入；合并/拆分、编辑、选中、来源对照切换保留编辑与选择；正式批量入库2题及用户确认回滚；文本PDF提取2题；点击难度标签聚焦输入|
|聊天图片|裁剪使用现有Dialog；固定标题、可滚动正文与普通布局footer；提示移出图片；Escape/取消不提交调整；旧附件在实际应用前保留；同文件可再次选择|旋转/增强/压缩后附件预览；键盘增强、Tab回环、背景inert；取消替换保留旧附件；移除后空发送禁用；Escape取消与焦点返回上传按钮|
|回答来源|宽屏保持并排非模态Inspector；窄屏为阅读模态并隔离背景交互|真实持久来源元信息展示；窄屏ShiftTab不逃离、背景inert；Escape关闭、焦点返回来源按钮，输入草稿保留；跨页关闭|

不新增自动合并，不把解析置信度或选中视作人工校对完成。候选问题与答案仍需用户校对并明确导入。旧草稿复制为可恢复文本，不自动注入最新正式笔记。

## 证据与检查

- [浏览器最终结果](evidence/complex/final/results.json)：13类检查×4宽度，52项通过；1280×820、1024×768、760×820，390×820为补充。每项包含多个流程断言，不等于所有异常组合穷举。
- [Electron结果](evidence/complex/electron/results.json)：13类通过，macOS Electron开发壳、隔离userData、真实本地API；不代表正式安装包生命周期通过。
- 最后增加恢复期间字段冻结，并在[1280代表流程](evidence/complex/recovery-final/results.json)复验13项通过，读取失败期间编辑控件禁用、失败后保留正文。该补验不重复计入52项。
- qa-check：相关后端125项、前端195项、桌面15项通过；类型、lint、生产构建通过。桌面loopback测试沙箱EPERM后经授权环境复验通过。构建保留既有大chunk提示。
- 首轮 [before](evidence/complex/before/results.json) 留存真实正式笔记恢复缺口与图片Escape故障；早期页面定位/等待时机错误不作为产品缺陷。中间after结果包含已经纠正的截图定位错误与同文件重选问题，最终以final/electron为准。
- 代表截图：[正式版本冲突](evidence/complex/final/1280-note-publish-conflict.png)、[已归档冲突](evidence/complex/final/1280-note-archived-conflict.png)、[恢复后正文](evidence/complex/final/1280-note-recovered-published.png)、[760候选校对](evidence/complex/final/760-candidates-corrected.png)、[760图片裁剪](evidence/complex/final/760-image-crop.png)、[760来源](evidence/complex/final/760-answer-source-inspector.png)、[1280并排来源](evidence/complex/final/1280-answer-source-inspector.png)。

## 视觉审查

[Visual Review Board](VISUAL-REVIEW-BOARD.md) 的 VRB-02 登记选图、共同原则和Astra审查。首次6图直接审查后统一实施；抽查6图（包括2张Sol初筛合格页面）发现持续可见标签缺失，以及正文加载未完成的证据时机缺口。已补标签与标签聚焦断言，截图等待正式正文渲染。最小复查2图通过，本批关闭；合计3次调用14张原图（6+6+2）。源代码核对与实际截图分别登记，未将首屏以下字段冒充截图可见。

## 数据与范围

本批全部写操作使用 `/tmp/texa-complex-qa`，模型/parser替代仅在测试模式，Word/textPDF提取走真实代码；服务启动前隔离.env及所有数据路径并拦截外部连接，未写正式学习资产、事件库或教材索引。测试库和截图保留供复查。无付费模型、OCR、真实索引发布或依赖安装。

本批仅关闭上述复杂交互域；P1其他动态浮层及异常组合继续保留Inventory条目。真实教材/OCR/模型质量、真实Tailscale设备、正式安装包生命周期不在本批，不登记PASS。
