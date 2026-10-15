# Texa Anti-AI-Slop Audit

集成更新：本报告的整改已与 Mobile S3、Goals/Tasks/Focus 及其后续 UI 调整合入 `Texa_MacOS`。设置颜色小字删除等改动与新功能同时保留；新增四尺寸专注流程和 214 项渲染复核见 [分支整合审计](TEXA-MACOS-INTEGRATION-AUDIT.md)。以下为最初审计时的范围和记录。

2026-10-15。依据现有 Texa UI 规范及批准的学习/教材截图实施；未更换设计体系、依赖或全局 Token。

## 覆盖

审计 **19 个入口：18 个业务页面/子页面 + 设置弹窗**。源码清单、引用和 UI 元素位置见 [source-inventory.json](docs/qa/anti-ai-slop/source-inventory.json)，逐页路径与状态见 [coverage.json](docs/qa/anti-ai-slop/coverage.json)。

| 页面组 | 实际覆盖 |
| --- | --- |
| 学习 | 主聊天、空会话、范围选择、来源详情、历史会话菜单、教材图空态、错题选择、图片裁剪、公式/矩阵、任务补输入/恢复/确认 |
| 目标 | 列表、详情、新建；空/加载/错误 |
| 笔记 | 列表、筛选、草稿、阅读、编辑预览、整理弹窗；空/加载/错误/重试 |
| 错题 | 列表、诊断、录入、草稿校对、详情；空/加载/错误 |
| 练习与复习 | 练习设置、导入、手动录入；复习队列、开始页、作答页；周报及无记录/加载/错误 |
| 教材 | 列表、分类、状态详情、操作菜单、图片审核、导入及长文件名、章节重点 |
| 设置与桌面 | 五个设置分区、窄屏返回/未保存字段、首次配置三页、启动/启动失败恢复页 |

浏览器尺寸：1280×820、1024×768、760×820、390×844；另检查五个已有主题。真实 macOS Electron 使用独立临时 userData 和合成数据。没有请求真实模型、OCR、学习数据库或执行提议写入。

边界：手机为浏览器视口，未验收 iOS/Android 实机、软键盘、触屏与屏幕阅读器；未运行 Windows/Linux 原生壳、真实更新/备份恢复、远程令牌连接或付费模型。复杂题库候选校对、真实 OCR 警告、教材图片选区、笔记冲突与历史来源异常只检查源码合同，未穷举所有渲染组合。旧 KnowledgeGraphPage、LibraryManager、ModelSettingsForm 的独立视图无当前路由入口；`/kg` 重定向复习，保留兼容代码。

## 整改

**23 组问题：DELETE 9、SIMPLIFY 10、REDESIGN 4。** 计数按可复核的问题组，不按删除字符串/组件数量。每组包含源码位置、认知成本、操作、置信度和证据，见 [findings.json](docs/qa/anti-ai-slop/findings.json)。

- DELETE：设置同义副标题、主题配色解说、空会话操作复述、诊断重复标题、归档/筛选空态复述、参考答案用途说明、错题列表用途说明、启动随机鼓励/饮食问候。
- SIMPLIFY：配置作用域、模型方案标题、错题录入层级、笔记草稿/正式保存说明、习题导入说明、PDF 按钮、未执行提示、完成条件列表、首次欢迎页、学科归类建议。
- REDESIGN：周报撤销嵌套卡片和装饰图标；章节重点撤销目录/文章外框与逐段横线；写入确认使用中文字段并保留完整载荷；公式面板约束在视口内并允许滚动。

| Before | After | 对照证据 |
| --- | --- | --- |
| “偏好”后重复“调整当前设备的阅读外观”，每个主题另有小字介绍 | 标题、名称、色样、选中勾；仅保留设备作用域；行高同步收紧 | [前](docs/qa/anti-ai-slop/before-panels/1280-panel-settings-偏好.png) / [后](docs/qa/anti-ai-slop/after/1280-panel-settings-偏好.png) |
| 周报每条结论一张卡，提问再套卡片 | 三段结论与提问列表，保留统计展开和复习入口 | [前](docs/qa/anti-ai-slop/before/1280-weekly.png) / [后](docs/qa/anti-ai-slop/after/1280-weekly.png) |
| “错题录入”下面再次“补录错题”并解释两种按钮 | 单一页标题、草稿与校对关系、两种入口、继续草稿 | [前](docs/qa/anti-ai-slop/before/390-intake.png) / [后](docs/qa/anti-ai-slop/after/390-intake.png) |
| 归类建议用图标/箭头/强调背景，并显示“判断置信度 88%” | 普通边界；显示目标学科、教材、理由与三种选择 | [前](docs/qa/anti-ai-slop/before-panels/390-panel-task-routing.png) / [后](docs/qa/anti-ai-slop/after/390-panel-task-routing.png) |
| 待确认学习写入直接展示英文 JSON | 中文字段；原始载荷可展开；未知合同仍完整展示 | [前](docs/qa/anti-ai-slop/before-panels/390-panel-task-confirmation.png) / [后](docs/qa/anti-ai-slop/after/390-panel-task-confirmation.png) |
| 首次欢迎页同时出现用途段、三条特性、准备说明和口号 | 一段具体用途与配置要求；保留三步与完成反馈 | [前](docs/qa/anti-ai-slop/before-panels/1280-panel-onboarding-welcome.png) / [后](docs/qa/anti-ai-slop/after/1280-panel-onboarding-welcome.png) |

## KEEP 与 Astra 判断

保留八类有实际价值的信息：①批准的学习画布/教材列表构图；②缺输入/暂停恢复/未核验状态；③删除、覆盖、归档与备份恢复边界；④凭证、外连、模型能力和参数；⑤OCR/候选校对与来源；⑥证据/索引版本与历史分页；⑦目标状态、完成条件与首次配置三步；⑧统计分母、同题组比较限制与可采取的错误恢复动作。

Astra 已结合源码和截图裁决：目标列表/详情状态承担不同定位职责，保留；空圆圈不能暗示不存在的逐项完成状态，改普通列表；欢迎页压缩宣传而保留三步；归类建议删除未经校准的百分比并补教材；确认内容按五类真实 payload 合同展示。无待决的页面级重新设计。本次没有实施工作区中已有的 Goals/Tasks/Focus 另案设计。

确认载荷的未知字段不会丢失；空答案、清空备注、0 分、`false` 仍可见。不改写入逻辑。另发现既有概念复习执行器会把 0 分按默认值 4 处理，已记为独立业务缺陷，本次不将其包装为视觉修复或已修复。

## 验证与第二轮

- TypeScript 与 Vite 构建通过；保留已有大 chunk 提醒。
- 前端 **46 文件 / 207 测试通过**；新增四项确认字段测试覆盖长文本、0/false、空答案/清空备注、未知/缺字段回退。
- 本次修改的 TS/TSX ESLint 通过；全量 ESLint 有一处既有 `ChatPage.tsx:242` 的 `react-hooks/refs` 错误，该文件与 HEAD 一致，未为本次审计修改业务逻辑。
- 桌面测试 **15 / 15 通过**。首次端口测试受沙箱限制，允许本机监听后重跑通过。
- 最终批次 **214 项自动检查通过**：浏览器页面/状态/主题 119 项、共享面板 76 项、真实 macOS Electron 路由 19 项。无页面异常、未处理 fixture 接口或文档级横向溢出；错误场景预期的 503 控制台信息另计。
- 实际阅览最终全部联系表及重点全尺寸截图：周报、设置、录入、归类、确认字段、公式面板的层级与间距符合本次调整；未以 DOM 宽度代替视觉判断。范围加载、手动录入取消、笔记筛选/编辑、设置返回/未保存值保留、首次配置保存、笔记及复习错误→重试→成功均有实际操作记录。
- 视觉保留项：`electron-review-start.png` 截到加载态，因此 Electron 该入口只验收加载状态；其完成状态已在浏览器四种尺寸中检查。`panel-mistake-picker` 捕获候选摘要加载态，不据此声称题干预览已完成。未改动这些业务加载逻辑。

第二轮沿“进入学习→选范围/公式→查看来源→整理笔记”和“进入错题→校对→复习→报告→设置”复核。发现主题文案删除后仍保留双行高度、错题列表用途复述，以及录入入口与继续草稿过近，已同步收紧主题行并恢复分区间距。没有添加填充空白的元素。

证据目录：[修改前页面](docs/qa/anti-ai-slop/before/results.json)、[修改前面板](docs/qa/anti-ai-slop/before-panels/results.json)、[最终结果](docs/qa/anti-ai-slop/after/results.json)。测试夹具定位/启动标记及字段名错误已在最终批次修正，早期失败批次不计验收通过。修改前面板批次的重点列表和错题状态两个接口未提供 fixture，其空/加载画面仅作结构参考；最终批次已补齐，未将它们误报成产品故障。
