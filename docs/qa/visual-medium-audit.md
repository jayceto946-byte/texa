# 1024 / 760 中等窗口视觉审阅

审阅日期：2026-10-11。应用：[texa-ui-system](../../.agents/skills/texa-ui-system/SKILL.md)，实际阅读了其 learning canvas / states 参考。只审阅本地合成fixture截图，未修改产品。依据的完成批次为 `pages/results.json`，started=`2026-10-11T08:00:42.217Z`；排除07:59旧批次、390状态截图及主题截图。

## 实際阅图证据

已通过 `view_image` 读取批准参考 `artifacts/study-desk/learning-final-type.png` 和 `textbooks-final-type.png`；以下38张截图全部在联系表中实际阅图，而非仅检查文件存在或scrollWidth。联系表为 `evidence/pages/medium-1024-0.jpg` 至 `medium-1024-3.jpg`，以及 `medium-760-0.jpg` 至 `medium-760-3.jpg`，每张图有独立文件名标签。

| 路由 | 已审阅1024×768文件 | 已审阅760×820文件 | 静态观察 |
| --- | --- | --- | --- |
| 主聊天 | 1024-chat.png | 760-chat.png | 空会话起始页，标题/范围/输入框对齐；没有已生成长答案。 |
| 目标 | 1024-goals.png | 760-goals.png | 列表与目标详情分栏，执行/暂停动作可见；760左栏仍保持独立选择区。 |
| 笔记列表 | 1024-notes.png | 760-notes.png | 状态tabs、检索与内容行层级清晰，标题与摘要有区分。 |
| 笔记阅读 | 1024-note.png | 760-note.png | 标题/摘要/正文轴一致，公式正确呈现，不显示多余来源块；编辑与归档可见。 |
| 笔记草稿 | 1024-draft.png | 760-draft.png | 字段、块级编辑与保存动作明确；长表单向下延续不等于裁切。 |
| 错题列表 | 1024-mistakes.png | 760-mistakes.png | 题干公式渲染，760日期改到下行，箭头保留；没有注册表横向溢出。 |
| 错题诊断 | 1024-diagnosis.png | 760-diagnosis.png | 显示route error fallback；本批诊断fixture不满足组件合同，见M2。 |
| 错题录入 | 1024-intake.png | 760-intake.png | 选择方式/继续草稿分区；草稿标题原始LaTeX，见M1。 |
| 错题草稿校对 | 1024-intake-draft.png | 760-intake-draft.png | 1024原图与校对双栏；760上下堆叠；textarea原始LaTeX符合编辑场景，且保留预览入口。 |
| 错题详情 | 1024-mistake.png | 760-mistake.png | 题目/当时作答/修正方式分节，关键动作位于题干下，不与正文争夺层级。 |
| 练习 | 1024-exercises.png | 760-exercises.png | 题数与复习/开始操作成组，主次按钮可辨；列表fixture内容不足，未验长题库。 |
| 复习计划 | 1024-learning.png | 760-learning.png | 今日概览/队列层级清晰，760打开/标记复习下移保持可用；队列题干是原始LaTeX，见M1。辅助未完成复习fixture不可用已明确披露。 |
| 开始错题复习 | 1024-review-start.png | 760-review-start.png | 标题、数量、退出可恢复说明与开始操作清晰。 |
| 复习作答 | 1024-review.png | 760-review.png | 题目、独立作答区、保存/提交动作没有重叠；公式渲染正确。 |
| 周报 | 1024-weekly.png | 760-weekly.png | 本周/薄弱/下一步三段平行，主动作可见；最近提问raw摘要见M1备注。 |
| 教材列表 | 1024-books.png | 760-books.png | 1024折成两行记录；760分类置顶、单本多行，状态和角色/操作仍可见，无横向溢出。 |
| 导入教材 | 1024-book-import.png | 760-book-import.png | 1024文件/参数双栏，760上下排；MinerU不可用的disabled标识与本地文本选中态可辨。 |
| 章节重点 | 1024-highlights.png | 760-highlights.png | 1024目录/正文分栏，760目录在正文上；标题、正文、公式及打印动作可读。 |
| 设置 | 1024-settings.png | 760-settings.png | 左侧设置分区与主题选项密度适中，选中主题同时有背景/勾，关闭按钮在窗口内。 |

另外实际读取全尺寸：`760-diagnosis.png`、`1024-diagnosis.png`、`760-learning.png`、`760-books.png`、`1024-books.png`、`760-intake.png`、`760-intake-draft.png`、`760-note.png`，用于验证联系表中的异常、长题干与行内公式。非这些文件的细小文字主要依据联系表，不声明逐像素通过。

## 与批准参考比较

教材参考在宽窗口采用名称/状态/分类/用途/操作横向表格；本批1024及760以多行重排保留同样的信息顺序和主次。1024截图每屏约4本、760约2本半，密度较参考低，原因是可用内容宽度下降；没有根据密度差异提出通用重设计。760分类面板有内部高度边界，截图只显示部分树，未实际滚动该面板，不能证明剩余分类可达。

批准Learning参考为有问答正文的阅读画布，主问题、解答、公式、引用和底部composer对齐。当前`chat`截图仍为新会话起始页，`learning`路由是复习计划管理页，不是批准图的回答页面。因此**不能宣称已完成有正文Learning画布的构图/长公式/引用/composer遮挡验收**。笔记与错题阅读页有公式，可确认这些单页片段渲染，但不能替代主聊天验收。

## 发现和修复候选

### M1 — P2：复习/继续草稿的阅读摘要直接显示原始LaTeX

实际全尺寸证据：`760-learning.png`的到期错题行显示`$\\lim_{x\\to0}\\frac...$`，`760-intake.png`的继续草稿标题同样显示`$\\lim...$`，1024联系表有相同行为。公式命令占用标题空间，降低快速识别题目的能力，与已渲染的错题详情/笔记正文不一致。周报最近提问也显示原始LaTeX，尚未追踪该模块代码。

已核实源位置：`frontend/src/pages/LearningPage.tsx:524`直接把`mistake.question_text`插入span，展开后另用ChatMessage；`frontend/src/pages/MistakeIntakePage.tsx:44`将question_text直接slice成标题。候选修复只针对**只读摘要**：复用现有数学渲染或明确可读的摘要转换，并保留折行/截断和Chevron操作位置；不要改变textarea编辑内容或另建渲染系统。当前没有执行这些行的展开操作，故不把源码上的可展开认定为实际交互通过。

### M2 — 未归因产品故障：诊断fixture合同错误，页面可用性尚未验收

两张全尺寸diagnosis截图均为“页面文件未能加载，桌面更新后请刷新以读取当前版本”。`scripts/qa-pages.mjs`返回`{groups:[],total:1}`；`MistakeDiagnosisPage`需要`record_count/reasons/comparison/actions/scope`，随即读取`diagnosis.reasons`和comparison。此故障与旧onboarding批次不同，但不能当作真实后端正常响应时的产品缺陷。建议先补正确fixture重新捕获两个宽度；目前诊断页的静态布局/交互未通过，页面级bodyWidth正常也不能算功能通过。

## 实际交互与静态检查分开

本次本人未控制浏览器执行交互。所审阅结果批次仅记录`notes filter expand`完成；此项为harness已执行证据，且使用1280窗口，**不能宣称1024/760已执行**。随后harness寻找“编辑正文”超时，`notes tab→draft→edit`与设置分区交互未完成。只看到draft编辑页静态截图不代表编辑/保存路径通过。

results的38项normal viewport检查均bodyWidth等于viewport，证明页面级无横向overflow；这不证明内部滚动容器、keyboard focus、popover、长标题、全部按钮点击/低屏高可达性。未通过浏览器测试键盘、焦点、展开、关闭、长答案滚动或Windows/Electron壳。未将截图的选中态外观当作持久化主题测试。

所审阅批次unhandled包括`/api/system/settings/subjects`、`/api/exercises/answer/jobs/latest`、`/api/review/sessions`、`/api/books/import-capabilities`；其中复习页在主体队列仍可读时显示明确辅助错误，符合故障隔离外观，但不代表这些接口上线可用。

## 授权局部修复

本报告前文记录修复前观察。随后主审计授权仅修改`LearningPage.tsx/css`、`MistakeIntakePage.tsx/css`和`MistakesPage.css`，未修改共享ApprovedWorkspace.css、Workspace、SystemHealth。

已实现：

- M1只读复习队列标题、最近学习问题、概念详情的近期问题/相关错题及继续草稿标题复用现有SimpleMarkdown；去除草稿标题原始文本slice，改为渲染后CSS两行限制，避免切断math delimiter。编辑textarea保持原内容。
- 摘要内markdown继承font-size/weight/line-height并移除p额外margin；display equation在容器内可横向滚动。原review题干`span`普遍line-clamp规则改为外层summary专用规则；原日期`span`规则收窄到直接日期元素，避免影响KaTeX内部span。
- 补充390窄屏的局部header修复：标题与目标入口flex:none/nowrap；范围selector wrapper允许flex-shrink并保持min-width:0，scope文字使用既有truncate。保留单行header及全部动作；没有隐藏标题/操作，也没有覆盖共享文件中的既有紧凑布局约定。

修复前截图副本：`evidence/ui-before/760-learning.png`、`1024-learning.png`、`760-intake.png`、`1024-intake.png`、`390-learning.png`、`390-mistakes.png`。390截图由主审计识别标题破字，本子审计的最初视觉矩阵仍限定1024/760；不把390副本保存算成实际阅图。

精确diff：`evidence/medium-fixes.diff`。TypeScript `tsc -b`通过（`medium-typecheck.log`空日志，exit 0）；两份修改TSX的ESLint通过（`medium-lint.log`空日志，exit 0）；Vite构建通过（`medium-build.log`，输出`/private/tmp/texa-medium-fixed-dist`，保留已有大chunk警告）。mathText与mistake reviewSession两文件共4项测试通过；日志`medium-tests.log`。没有为低风险CSS调整增加实现镜像测试。

**修复后视觉状态：待主审计用新dist重新截图并实际阅图**。源码/type/build通过不代表390单行标题、760公式摘要或展开交互已经实际验收；新截图确认前，本节不标视觉FIXED/PASS。
