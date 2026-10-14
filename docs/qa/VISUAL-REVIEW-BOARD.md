# Texa Visual Review Board

2026-10-11 · 后续审查素材索引。本轮已完成共同问题决策、整改抽查及最小复查；调用3次、原图15张。执行规则见 [P0/P1 策略](QA-REMEDIATION-STRATEGY.md)。

## 参考与证据来源

成熟视觉参考为 [学习画布](../../artifacts/study-desk/learning-final-type.png) 与 [教材工作区](../../artifacts/study-desk/textbooks-final-type.png)。它们提供已批准的视觉语言；其他页面仍需按任务判断层级与交互。

[accepted-pages.json](evidence/accepted-pages.json) 为现有有效截图映射；[frontend-inventory.md](frontend-inventory.md) 为页面、子状态和全局浮层清单。下表是候选素材池，不代表把一个域的全部图片一次发送，也不代表截图仍与后续代码一致。送审前核对捕获状态、视口、代码身份及映射；代码已变或交互缺图时用现有脚本补拍。

## 按功能域组织的候选批次

|功能域/共同问题|成熟参考与待审查素材|必要细节与补拍重点|
|---|---|---|
|问答、学习、章节阅读：正文/来源/行动层级|学习参考；[chat](evidence/pages-supplement/1280-chat.png)、[learning](evidence/pages-repeat/1280-learning.png)；章节 highlights 图从有效映射选择|长公式、引用/Inspector、输入工具、侧栏折叠；窄窗口代表图与实际展开状态|
|笔记：资产列表到阅读/编辑连续性|学习参考；[notes](evidence/pages-repeat/1280-notes.png)、[edit](evidence/pages-repeat/interaction-note-edit.png)；详情/历史/草稿图从有效映射选择|[filters](evidence/pages-repeat/interaction-notes-filters.png)、[error](evidence/pages-repeat/error-notes.png)；保存/冲突/取消与历史只读补拍|
|练习、错题、复习：作答与管理状态|学习参考；[exercises](evidence/pages-repeat/1280-exercises.png)、[review start](evidence/pages-repeat/1280-review-start.png)；intake/错题详情/复习完成图从有效映射选择|候选校对、题干/参考答案、自评/下一步、手工录入弹窗；错误→重试与跨页恢复|
|教材：管理、导入与章节材料|教材参考；books/import/highlights 图从有效映射选择|来源选择、目录/PDF页选择、导入进度、取消/失败恢复、长名称与层级|
|目标、学习报告：状态与行动优先级|学习参考；[weekly](evidence/pages-supplement/1280-weekly.png)；goals/detail 图从有效映射选择|启动确认、所需输入、暂停/继续、执行记录与空数据；避免指标压过学习行动|
|设置与全局浮层：导航、表单与反馈一致性|教材参考；[模型连接](evidence/pages-repeat/interaction-settings-模型连接.png)、[高级与诊断](evidence/pages-repeat/interaction-settings-高级与诊断.png)|五 Tab、设置未保存关闭确认、菜单/抽屉/Inspector、焦点和 Escape；当前网络诊断改动需补最新图|

某共同问题跨域时，从相关域精选代表图组成一批，例如统一“阅读页标题/正文/元信息层级”；不将全部域拼成大批。全部页面仍需在现有 Inventory 中逐项登记，不能用代表样本替代覆盖。

## 每批记录格式

在本文追加批次记录即可，无需新平台或新图库副本：

- 批次 ID、功能域、一个共同设计问题、覆盖的 route/浮层与暂缺状态。
- 4–6 张左右的精选图链接与角色（成熟参考/待审子页面/细节），各自状态、视口、主题、构建身份；更多图的必要性。提供原图供 Astra 直接读取，文字补充操作前后和截图不可表达的行为。
- Sol 初筛结论与待决策取舍；Astra 调用次数/图片数、共同问题、原则、组件模式、整改要求、验收条件。
- 决策对应的共享组件/视觉角色与页面清单；整改前后截图、实际交互断言及剩余风险。
- Astra 抽查图与结论：关键整改样本 + 少量 Sol 判定合格样本；漏检/标准偏差、扩展检查与最终状态。

批次状态使用 待准备→待 Astra 决策→统一整改→Sol 视觉/交互验证→Astra 抽查→关闭；需要补图或交互证据时保留待验证。下列批次记录实际调用与有限关闭范围。

## 已执行批次 VRB-01：表单、管理对象与行动层级

**已关闭本批共同问题；全部 P1 保留独立覆盖条目。**

### 首次决策 · Astra 1 次 / 6 原图

成熟参考：[学习画布](../../artifacts/study-desk/learning-final-type.png)、[教材工作区](../../artifacts/study-desk/textbooks-final-type.png)。待审：[笔记编辑](evidence/pages-repeat/interaction-note-edit.png)、[无图错题录入](evidence/pages-final/1280-intake-draft.png)、[教材导入](evidence/pages-final/1280-book-import.png)、[目标](evidence/pages-final/1280-goals.png)。成熟参考提供视觉语言；其余为整改前历史构建快照，未混入不相关域。

Astra 决策：正常布局底部动作区，单一保存入口，状态/次要动作/主动作分工；无原图时改为辅助行，有原图保留比对区域；共享同排返回控件；对象标题24px、分组18px，参数子标题16px；Goal enabled 与 Runtime running 分别表达。Sol 用 WorkspaceActionBar 与共享 CSS 统一整改，不改领域状态机。

### 抽查 · Astra 1 次 / 6 原图

整改样本：[录入1280](evidence/p0-p1/pages-final/1280-intake-draft.png)、[导入760](evidence/p0-p1/pages-final/760-book-import.png)、[目标1280](evidence/p0-p1/pages-final/1280-goals.png)、[笔记编辑1280](evidence/p0-p1/pages-final/interaction-note-edit.png)。Sol 初筛合格样本：[教材列表1280](evidence/p0-p1/pages/1280-books.png)、[设置390](evidence/p0-p1/pages-final/390-settings.png)。前四图来自 /tmp/texa-full-qa-dist-final；教材列表来自首轮本批 /tmp/texa-full-qa-dist。

Astra 通过4图当前构图；发现导入父步骤标题弱于参数标题和窄屏设置固定侧栏压窄正文。后者是 Sol 标准偏差：无水平溢出不等于信息可读。要求所有窄屏设置共享单栏导航/详情，不继续按子页增加特例；返回保留选项、字段和焦点。导入PDF/zip分支统一18/16px父子层级。

### 最小复查 · Astra 1 次 / 3 原图

[设置390详情](evidence/p0-p1/pages-accepted/390-settings-content.png)、[设置390导航](evidence/p0-p1/pages-accepted/390-settings-navigation.png)、[导入760长文件名与滚动末端](evidence/p0-p1/pages-accepted/760-import-long-scroll-end.png)，来自 /tmp/texa-full-qa-dist-accepted。

Astra 确认窄屏导航占宽及导入末端可达性关闭；导入18/16px源码只读核对单独登记，末端图不冒充首屏标题截图。主题说明完整换行，关闭按钮与返回入口清楚。Sol 实际断言字段跨返回保留、进入/返回焦点、隐藏导航Tab、关闭和滚动末端；导入取消走独立真实 Job E2E，截图只验证位置与层级。

跨页可复用原则：层级由标题角色和间距表达；同一对象的启用/运行/提交状态分别展示；操作区正常布局并给出前置条件；窄屏管理导航先让出正文宽度；审美验收检查可读性和任务完成路径，不只检查溢出。

### 覆盖与暂缺

[visual-coverage.json](evidence/p0-p1/visual-coverage.json)逐项映射19URLs及最新快照；Sol 全页面联系表位于 [boards](evidence/p0-p1/boards)，关键原图直接读取。Astra 样本判定限于上述问题域；本批没有声称全部复杂交互、图片识别质量、动态导入进度及笔记冲突均完成审美验收。下一批沿原 Inventory 的未审子状态补图，不重建审计设施。

## VRB-02 · 冲突恢复与复杂编辑/阅读呈现（2026-10-12）

**本批已关闭；不扩大为全部P1通过。** 批次范围：笔记草稿/正式版本冲突、习题候选校对、图片裁剪、回答来源。共同问题是编辑内容与权威版本分离后如何保留修改、表达屏障，并提供唯一明确的下一步。真实模型质量独立于本批。

### 决策 · 1次 / 6原图

成熟参考：[学习](../../artifacts/study-desk/learning-final-type.png)、[已审笔记编辑](evidence/p0-p1/pages-final/interaction-note-edit.png)。待审：[1280正式笔记冲突](evidence/complex/before/1280-note-publish-conflict.png)、[760候选校对](evidence/complex/before/760-candidates-corrected.png)、[760裁剪](evidence/complex/before/760-image-crop.png)、[760来源](evidence/complex/before/760-answer-source-inspector.png)。待审图来自 `/tmp/texa-complex-dist-before`，不能作为最终图。

Astra要求：先保留当前内容，再说明屏障及影响；恢复区一个主动作、至多一个常用次动作。草稿存储失败/草稿CAS/正式CAS分别处理；正式冲突复制后基于最新revision新建编辑草稿，不自动合并，已归档只复制+阅读。候选生成准备与校对分阶段，原文可返回，底部唯一确认导入；解析置信度和选中不等于校对。编辑模态共用固定标题、可滚动正文、普通布局footer；窄屏来源隔离背景键盘，桌面来源保持非模态并排。图片中央提示移出画布。

Sol在DraftWorkspace/DraftAutosaver、ExercisesPage、Dialog、ProblemImageEditor、ContextInspector及共享CSS统一实施。原业务服务和状态权威保持。图片选择在应用成功前保留原附件，取消不丢失；同文件重选清空input值。

### 抽查 · 1次 / 6原图

关键整改：[正式笔记冲突](evidence/complex/final/1280-note-publish-conflict.png)、[760候选校对](evidence/complex/final/760-candidates-corrected.png)、[760裁剪](evidence/complex/final/760-image-crop.png)、[760来源](evidence/complex/final/760-answer-source-inspector.png)。Sol初筛合格：[1280并排来源](evidence/complex/final/1280-answer-source-inspector.png)、[恢复后阅读](evidence/complex/final/1280-note-recovered-published.png)。来自 `/tmp/texa-complex-dist-after`；final同名图后经下述修复覆盖，原抽查阅读图当时尚有“正在加载内容…”，不能作为正文通过证据。

Astra通过共同布局与恢复层级；发现候选字段填入值后失去用途标签，以及正式阅读截图捕获过早。前者是Sol表单审查偏差：placeholder在填写后消失，无溢出不代表字段身份清楚。后者是证据时机缺口，不判定为产品加载故障。

### 最小复查 · 1次 / 2原图

[760候选标签](evidence/complex/final/760-candidates-corrected.png)、[1280恢复后正式正文](evidence/complex/final/1280-note-recovered-published.png)。已增加题干、题型、难度1–5、知识点、标准答案、解析、来源、章节可见嵌套label，13px既有字段角色；点击难度标签实际聚焦。解析/来源/章节处于首屏以下，Astra单独源码核对，未以截图冒充可见。正文捕获等待“基于最新版本人工整合”实际渲染，并显示版本3。Astra通过并明确无需额外末端图。

本批Astra **3次、14张原图（6+6+2）**。从6图抽查仅补2张遗留项，未重复送全部域。后续表单审查统一增加“填写后标签仍可见且可聚焦”，加载页捕获须断言实际目标正文。

### 行为及有限关闭证据

[完整报告](COMPLEX-INTERACTIONS-2026-10-12.md)、[浏览器52项](evidence/complex/final/results.json)、[Electron13项](evidence/complex/electron/results.json)。浏览器1280×820、1024×768、760×820、补充390×820；真实API/SQLite、Word与文本PDF提取；覆盖失败保留、权威CAS、人工整合、归档只读、候选切换/入库/回滚、附件替换取消、焦点/inert/Escape及跨页关闭。Astra视觉结论只支持对应图与共同问题；正式阅读证明离线手工恢复后的呈现，未证明模型正确性。真实Tailscale与正式安装包仍不处理。
