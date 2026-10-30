# Texa Icon Audit

2026-10-30 · 当前工作区静态普查，包含已存在的未提交文件；不代表这些差异获准提交。审计完成前未改业务组件。

这份库存是迁移前快照。最终 A 的生产接入范围与验证见 TEXA-ICON-SPEC.md 和 TEXA-ICON-EVALUATION.md；下列频次不作为迁移后的实时统计。

## 范围与计数

扫描 frontend/src 全部非测试 TS/TSX/CSS（216 文件），并逐项核对 public SVG、品牌资产、原生窗口控制及数学输入。排除测试、候选设计目录；ui-refactor-preview 单列为预览。唯一第三方 UI 图标来源是 lucide-react。79 个导入名称，216 组图标/文件，287 个静态引用（含 JSX 和映射，不是用户点击频率）。重复 JSX、条件分支会分别计数；未运行遥测，不推断热度。

## 主要发现

- AppRail 实际导航为学习、目标与任务、复习、笔记、错题、练习、教材；错题使用 GraduationCap，泛指毕业而非错误复盘。优先重设计产品语义。
- BookOpen 同时承担教材导航、来源段落、教材范围和复习关联。保留书籍基形，检索需要明确的段落定位结构，不能全用同一本打开的书。
- AlertCircle / CircleAlert、HelpCircle / CircleHelp、RefreshCw / RotateCw、Loader2 / LoaderCircle 存在近义或别名；统一语义入口，保留警告/信息差异。
- Copy 同时用于内容复制和 DesktopTitleBar 窗口还原；后者必须保持平台惯例并有独立语义名。
- JSX 多见 14、16、18、20px，另有空态大图。ApprovedWorkspace.css:110 与 StudyDesk.css:160 将导航强制为 16px / 1.6，覆盖 AppRail 的 18px；study-book-icon 为 20×25 / 1.3。仅改 SVG 默认线宽不足以统一。
- BrainCircuit 用于完善知识关联；无需脑形电路模板。数学验证在 ExecutionTrace 里是状态 Check/AlertCircle，不存在单独的验证 logo；Agent 和动态命题没有独立导航图标，不应编造现有页面。候选仅用于探索。
- 没有发现业务内联 SVG、自定义 SVG 组件、SVG use 或 CSS mask 图标。index.css:1883 的 select 通过两个 5px CSS linear-gradient 拼成下拉箭头，应与 ChevronDown 合并语义；这类功能性渐变无需因为“去 AI 感”而删除。DesktopRefinement.css:55 使用文字 ›；其余伪元素为选中条或布局。
- ChatPage 用 📎 标记图片/教材图消息，ChatMessage 有对应前缀解析。以后替换需要保留历史兼容，不能只删除字符。数学面板的 ∑、→、−、矩阵标签是输入内容，保留文字。
- 不为“整理笔记”“确认入库”等已有清晰文字动作增加装饰图标；空态无需为了品牌感再加 AI 星芒。

## 图标库存

每行是一个来源符号在一个文件内的全部引用；Name 是当前图形名，后接操作语义；多义项需结合位置与标签区分，原始上下文保存在 JSON。尺寸列是源码声明（动态项需结合调用方/CSS）；实际统一规则见上。P1 产品/专属；P2 合并；P3 成熟操作保留并校正。全部位置相对仓库根。

| Icon / Semantic Name | Source | Location（引用行） | Size / declaration | Frequency | Priority | Recommendation |
|---|---|---|---|---:|---|---|
| AlertCircle / 错误或降级提示 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:109 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| AlertCircle / 错误或降级提示 | Lucide React | frontend/src/components/ui/AsyncState.tsx:30 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| AlertTriangle / 警告 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:188 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| AlertTriangle / 警告 | Lucide React | frontend/src/components/SystemHealth.tsx:26 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| AlertTriangle / 警告 | Lucide React | frontend/src/layouts/MainLayout.tsx:257 | className="h-4 w-4 flex-shrink-0"  | 1 | P2 | Consolidate |
| Archive / 压缩包导入或归档 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:130,219 | className="h-4 w-4" ; 动态映射 / 容器 CSS | 2 | P3 | Keep（几何校正） |
| Archive / 压缩包导入或归档 | Lucide React | frontend/src/pages/BooksPage.tsx:264 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ArrowDown / 下移或回到最新 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:35 | size={14} | 1 | P3 | Keep（几何校正） |
| ArrowDown / 下移或回到最新 | Lucide React | frontend/src/features/notes/NoteBlocks.tsx:39 | size={16} | 1 | P3 | Keep（几何校正） |
| ArrowDown / 下移或回到最新 | Lucide React | frontend/src/pages/ChatPage.tsx:1057 | size={17} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/components/FirstRunGuide.tsx:114 | size={16}  | 1 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/BooksPage.tsx:255 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/GoalsPage.tsx:224,238 | size={15}  | 2 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/MistakeIntakePage.tsx:47,163 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/MistakesPage.tsx:287,388 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/ReviewSessionPage.tsx:47,56 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| ArrowLeft / 返回上一步 | Lucide React | frontend/src/pages/UserGuidePage.tsx:55 | size={15}  | 1 | P3 | Keep（几何校正） |
| ArrowRight / 前进或下一题 | Lucide React | frontend/src/components/FirstRunGuide.tsx:110,114,115 | size={16}  | 3 | P3 | Keep（几何校正） |
| ArrowRight / 前进或下一题 | Lucide React | frontend/src/pages/MistakesPage.tsx:188 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ArrowRight / 前进或下一题 | Lucide React | frontend/src/pages/UserGuidePage.tsx:54,54,55,55,55 | size={14} ; size={15}  | 5 | P3 | Keep（几何校正） |
| ArrowUp / 上移 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:35 | size={14} | 1 | P3 | Keep（几何校正） |
| ArrowUp / 上移 | Lucide React | frontend/src/features/notes/NoteBlocks.tsx:38 | size={16} | 1 | P3 | Keep（几何校正） |
| ArrowUpRight / 展开专注面板 | Lucide React | frontend/src/features/focus/FocusController.tsx:129 | size={12} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| BarChart3 / 复习工作区 | Lucide React | frontend/src/components/AppRail.tsx:8 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| BookMarked / 错题来源/教材标记 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:391,521,577 | className="h-4 w-4 flex-shrink-0 text-accent" ; className="h-3.5 w-3.5"  | 3 | P2 | Consolidate |
| BookMarked / 错题来源/教材标记 | Lucide React | frontend/src/pages/ChatPage.tsx:1086,1132,1146 | className="h-5 w-5" ; className="h-4 w-4" ; className="h-3.5 w-3.5"  | 3 | P2 | Consolidate |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/AppRail.tsx:12 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/chat/ChapterHighlightCard.tsx:15 | className="h-4 w-4 text-accent"  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:40,47 | 动态映射 / 容器 CSS | 2 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/ChatMessage.tsx:378,388 | className="h-3.5 w-3.5" ; className="h-3 w-3"  | 2 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/ScopeSelector.tsx:371 | className="h-3.5 w-3.5 flex-shrink-0 text-accent"  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:162,205 | 动态映射 / 容器 CSS; className="study-book-icon" aria-hidden="true"  | 2 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/components/SystemHealth.tsx:430 | className="h-4 w-4"  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/features/visual-learning/FigureContextAttachment.tsx:31 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/features/visual-learning/FigureRegionViewer.tsx:82 | className="h-3.5 w-3.5"  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/pages/ExercisesPage.tsx:633 | size={22}  | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/pages/LearningPage.tsx:498 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| BookOpen / 教材/范围/来源 | Lucide React | frontend/src/pages/MistakesPage.tsx:340,391 | className="h-4 w-4"  | 2 | P1 | Redesign |
| BrainCircuit / 完善知识关联 | Lucide React | frontend/src/pages/LearningPage.tsx:382 | className="h-4 w-4"  | 1 | P1 | Redesign |
| CalendarClock / 定时任务 | Lucide React | frontend/src/pages/GoalsPage.tsx:246 | size={15}  | 1 | P3 | Keep（几何校正） |
| CalendarDays / 日历/学习摘要 | Lucide React | frontend/src/pages/ChatPage.tsx:1143,1144 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| CalendarDays / 日历/学习摘要 | Lucide React | frontend/src/pages/LearningPage.tsx:434 | className="h-4 w-4 text-accent"  | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:26,109 | className="text-[var(--success)]" ; 动态映射 / 容器 CSS | 2 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/chat/LearningTaskActions.tsx:74 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/FirstRunGuide.tsx:115 | size={15}  | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/ScopeSelector.tsx:412 | className="h-3.5 w-3.5 flex-shrink-0 text-accent"  | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/settings/AppearanceSettings.tsx:43 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/components/ui/ScrollableSelect.tsx:183 | className="h-4 w-4 flex-none text-accent" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/features/focus/FocusController.tsx:141,151,161 | size={14} aria-hidden="true" ; size={14}  | 3 | P3 | Keep（几何校正） |
| Check / 确认/选中/完成 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:42 | size={15} | 1 | P3 | Keep（几何校正） |
| CheckCircle2 / 成功状态 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:68 | className="h-4 w-4 text-[var(--success)]"  | 1 | P3 | Keep（几何校正） |
| CheckCircle2 / 成功状态 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:188,229 | 动态映射 / 容器 CSS; className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| CheckCircle2 / 成功状态 | Lucide React | frontend/src/components/SystemHealth.tsx:24,25 | 动态映射 / 容器 CSS | 2 | P3 | Keep（几何校正） |
| CheckCircle2 / 成功状态 | Lucide React | frontend/src/components/ui/AsyncState.tsx:31 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/components/ScopeSelector.tsx:302 | className={`h-4 w-4 flex-shrink-0 text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`}  | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:118 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/components/settings/ModelSettingsManager.tsx:221 | size={15} className={connectionExpanded ? 'rotate-180' : ''}  | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/components/ui/ScrollableSelect.tsx:147 | className={`h-4 w-4 flex-none text-text-secondary transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/pages/ExercisesPage.tsx:691 | className="h-4 w-4 text-accent"  | 1 | P3 | Keep（几何校正） |
| ChevronDown / 下拉或折叠 | Lucide React | frontend/src/pages/LearningPage.tsx:360,491,517 | className="h-4 w-4" ; className={open ? 'h-4 w-4 rotate-180' : 'h-4 w-4'} ; className={expanded ? 'h-4 w-4 rotate-180' : 'h-4 w-4'}  | 3 | P3 | Keep（几何校正） |
| ChevronLeft / 返回分类 | Lucide React | frontend/src/features/math-input/VisualMathInputPopover.tsx:151 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ChevronRight / 展开详情 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:40,47,118 | className="execution-disclosure" ; className={`execution-disclosure ${expanded ? 'is-open' : ''}`}  | 3 | P3 | Keep（几何校正） |
| ChevronRight / 展开详情 | Lucide React | frontend/src/components/ScopeSelector.tsx:340 | className="h-3.5 w-3.5 flex-shrink-0 text-text-secondary"  | 1 | P3 | Keep（几何校正） |
| ChevronRight / 展开详情 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:118 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ChevronRight / 展开详情 | Lucide React | frontend/src/pages/ExercisesPage.tsx:570,633,636,691 | size={16} ; className="h-4 w-4 text-text-secondary"  | 4 | P3 | Keep（几何校正） |
| ChevronRight / 展开详情 | Lucide React | frontend/src/pages/NoteDetailPage.tsx:38 | size={14} aria-hidden="true" | 1 | P3 | Keep（几何校正） |
| Circle / 等待/未完成 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:28 | className="text-text-tertiary"  | 1 | P3 | Keep（几何校正） |
| Circle / 等待/未完成 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:71 | className="h-4 w-4 text-text-secondary/55"  | 1 | P3 | Keep（几何校正） |
| CircleAlert / 信息提示 | Lucide React | frontend/src/components/ui/AsyncState.tsx:32 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| CircleHelp / 用户指南 | Lucide React | frontend/src/components/AppRail.tsx:60,71 | 动态映射 / 容器 CSS | 2 | P2 | Consolidate |
| CircleX / 失败状态 | Lucide React | frontend/src/components/SystemHealth.tsx:27 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| ClipboardList / 练习与题库 | Lucide React | frontend/src/components/AppRail.tsx:11 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| ClipboardList / 练习与题库 | Lucide React | frontend/src/pages/ExercisesPage.tsx:716 | className="mx-auto mb-2 h-6 w-6"  | 1 | P1 | Redesign |
| ClipboardList / 练习与题库 | Lucide React | frontend/src/pages/LearningPage.tsx:497,499 | 动态映射 / 容器 CSS | 2 | P1 | Redesign |
| ClipboardList / 练习与题库 | Lucide React | frontend/src/pages/MistakesPage.tsx:391 | className="h-4 w-4"  | 1 | P1 | Redesign |
| Copy / 还原窗口 | Lucide React | frontend/src/components/DesktopTitleBar.tsx:30 | className="desktop-restore-icon"  | 1 | P3 | Keep（几何校正） |
| Copy / 复制内容 | Lucide React | frontend/src/components/settings/MobileRemoteS0.tsx:32 | size={15} | 1 | P3 | Keep（几何校正） |
| Copy / 复制内容 | Lucide React | frontend/src/pages/UserGuidePage.tsx:14 | size={14}  | 1 | P3 | Keep（几何校正） |
| Database / 数据备份 | Lucide React | frontend/src/components/settings/DataSafety.tsx:92 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ExternalLink / 打开独立来源 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:505 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| ExternalLink / 打开独立来源 | Lucide React | frontend/src/pages/HighlightPage.tsx:154 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| ExternalLink / 打开独立来源 | Lucide React | frontend/src/pages/LearningPage.tsx:499,521 | className="inline h-3 w-3" ; className="h-3 w-3"  | 2 | P3 | Keep（几何校正） |
| FilePlus2 / 新建文件条目 | Lucide React | frontend/src/components/chat/LearningTaskGate.tsx:47 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| FileText / 文档/章节 | Lucide React | frontend/src/layouts/MainLayout.tsx:265 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| FileText / 文档/章节 | Lucide React | frontend/src/pages/BooksPage.tsx:264 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Focus / 图片对焦/裁剪 | Lucide React | frontend/src/features/visual-learning/FigureRegionViewer.tsx:79 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| FolderInput / 导入目录 | Lucide React | frontend/src/components/chat/SubjectRouteSuggestionCard.tsx:128 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| FolderOpen / 打开教材目录 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:504,526,573 | className="h-3.5 w-3.5"  | 3 | P3 | Keep（几何校正） |
| FolderOpen / 打开教材目录 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:119 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Globe2 / 联网工具来源（现有搁置差异） | Lucide React | frontend/src/components/ChatMessage.tsx:323,340 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| GraduationCap / 错题/学科范围 | Lucide React | frontend/src/components/AppRail.tsx:10 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| GraduationCap / 错题/学科范围 | Lucide React | frontend/src/components/ChatMessage.tsx:340 | className="h-3.5 w-3.5"  | 1 | P1 | Redesign |
| GraduationCap / 错题/学科范围 | Lucide React | frontend/src/components/ScopeSelector.tsx:300 | className="h-4 w-4 flex-shrink-0 text-accent"  | 1 | P1 | Redesign |
| Grid3X3 / 数学模板分类 | Lucide React | frontend/src/features/math-input/VisualMathInputPopover.tsx:173 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| HelpCircle / 帮助 | Lucide React | frontend/src/pages/BooksPage.tsx:70 | className="h-4 w-4"  | 1 | P2 | Consolidate |
| History / 历史记录 | Lucide React | frontend/src/components/LearningHistoryDock.tsx:66 | size={16} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Image as ImageIcon / 图片/教材图 | Lucide React | frontend/src/features/visual-learning/FigureCatalog.tsx:71 | className="h-4 w-4 shrink-0" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| ImagePlus / 上传题图 | Lucide React | frontend/src/components/chat/MistakeQuickCaptureCard.tsx:8 | className="h-4 w-4 text-accent"  | 1 | P3 | Keep（几何校正） |
| ImagePlus / 上传题图 | Lucide React | frontend/src/pages/ChatPage.tsx:1129,1130,1147 | className="h-4 w-4" ; className="h-3.5 w-3.5"  | 3 | P3 | Keep（几何校正） |
| ImagePlus / 上传题图 | Lucide React | frontend/src/pages/MistakeIntakePage.tsx:47,164 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| ImagePlus / 上传题图 | Lucide React | frontend/src/pages/MistakesPage.tsx:177 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| ImagePlus / 上传题图 | Lucide React | frontend/src/pages/ReviewSessionPage.tsx:74 | size={16}  | 1 | P3 | Keep（几何校正） |
| Images / 教材图浏览 | Lucide React | frontend/src/features/visual-learning/FigureContextAttachment.tsx:18 | className="h-4 w-4 shrink-0 text-text-secondary" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Images / 教材图浏览 | Lucide React | frontend/src/pages/ChatPage.tsx:1131 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Info / 说明 | Lucide React | frontend/src/components/ui/AsyncState.tsx:29 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| Link2 / 模型连接 | Lucide React | frontend/src/components/settings/ModelSettingsManager.tsx:207 | size={15}  | 1 | P3 | Keep（几何校正） |
| ListChecks / 任务清单 | Lucide React | frontend/src/components/chat/LearningTaskGate.tsx:56 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:25,109 | className="animate-spin text-accent" ; 动态映射 / 容器 CSS | 2 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/chat/ExerciseCard.tsx:77 | className="h-3.5 w-3.5 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/ConceptPopover.tsx:57 | className="h-4 w-4 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/FirstRunGuide.tsx:114 | size={16} className="animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:70,505,511,521,526,577 | className="h-4 w-4 animate-spin text-accent" ; className="h-3.5 w-3.5 animate-spin"  | 6 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/settings/DataSafety.tsx:92,124 | className="h-4 w-4 animate-spin"  | 2 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/settings/MobileRemoteS0.tsx:31 | size={16} className="animate-spin" | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/components/ui/AsyncState.tsx:28 | 动态映射 / 容器 CSS | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/features/mistakes/components/ProblemImageEditor.tsx:192 | className="h-4 w-4 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/layouts/MainLayout.tsx:257 | className="h-4 w-4 flex-shrink-0 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/BooksPage.tsx:378 | className="h-4 w-4 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/ExercisesPage.tsx:570,741 | size={16} className="animate-spin" ; className="h-4 w-4 animate-spin"  | 2 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/GoalsPage.tsx:230,235 | className="animate-spin" size={16}  | 2 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/HighlightPage.tsx:85,154 | className="h-3.5 w-3.5 animate-spin"  | 2 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/MistakeIntakePage.tsx:166 | className="h-4 w-4 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/MistakesPage.tsx:181 | className="inline h-4 w-4 animate-spin"  | 1 | P2 | Consolidate |
| Loader2 / 加载/执行中 | Lucide React | frontend/src/pages/ReviewSessionPage.tsx:47,76 | className="h-4 w-4 animate-spin" ; size={15} className="animate-spin"  | 2 | P2 | Consolidate |
| LoaderCircle / 连接加载中 | Lucide React | frontend/src/components/settings/ModelSettingsManager.tsx:207 | size={15} className="animate-spin"  | 1 | P2 | Consolidate |
| Maximize2 / 放大阅读 | Lucide React | frontend/src/pages/UserGuidePage.tsx:48 | size={14}  | 1 | P3 | Keep（几何校正） |
| MessageSquare / 学习会话 | Lucide React | frontend/src/components/AppRail.tsx:6 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| MessageSquarePlus / 新会话 | Lucide React | frontend/src/pages/ChatPage.tsx:986 | size={15} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Minus / 最小化窗口 | Lucide React | frontend/src/components/DesktopTitleBar.tsx:29 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| Minus / 最小化窗口 | Lucide React | frontend/src/features/math-input/MatrixBuilder.tsx:62,70 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| MoreHorizontal / 更多操作 | Lucide React | frontend/src/components/chat/ComposerOverflowMenu.tsx:73 | className="h-4 w-4" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| MoreHorizontal / 更多操作 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:228 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| MoreHorizontal / 更多操作 | Lucide React | frontend/src/components/ui/OverflowMenu.tsx:43 | size={16} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| NotebookPen / 学习笔记 | Lucide React | frontend/src/components/AppRail.tsx:9 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| PanelLeftClose / 收起侧栏 | Lucide React | frontend/src/components/AppRail.tsx:43 | size={18}  | 1 | P3 | Keep（几何校正） |
| PanelLeftClose / 收起侧栏 | Lucide React | frontend/src/components/LearningContextSidebar.tsx:262 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| PanelLeftOpen / 打开侧栏 | Lucide React | frontend/src/layouts/MainLayout.tsx:281 | className="h-[18px] w-[18px]"  | 1 | P3 | Keep（几何校正） |
| Paperclip / 附件 | Lucide React | frontend/src/components/ChatMessage.tsx:250 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Pause / 暂停 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:109 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| Pause / 暂停 | Lucide React | frontend/src/features/focus/FocusController.tsx:148,168 | size={16} ; size={11} aria-label="已暂停"  | 2 | P3 | Keep（几何校正） |
| Pencil / 编辑 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:138,230 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| Pencil / 编辑 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:35 | size={14} | 1 | P3 | Keep（几何校正） |
| Pencil / 编辑 | Lucide React | frontend/src/features/math-input/MathExpressionList.tsx:36 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Pin / 置顶 | Lucide React | frontend/src/components/LearningContextSidebar.tsx:309 | className="conversation-pin" size={12} aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Play / 启动/继续 | Lucide React | frontend/src/features/focus/FocusController.tsx:148,153,160 | size={16}  | 3 | P3 | Keep（几何校正） |
| Play / 启动/继续 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:36 | size={13} | 1 | P3 | Keep（几何校正） |
| Play / 启动/继续 | Lucide React | frontend/src/pages/GoalsPage.tsx:246,246 | size={15}  | 2 | P3 | Keep（几何校正） |
| Plus / 新增 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:106,107 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| Plus / 新增 | Lucide React | frontend/src/components/settings/ModelSettingsManager.tsx:248 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Plus / 新增 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:39 | size={15} | 1 | P3 | Keep（几何校正） |
| Plus / 新增 | Lucide React | frontend/src/features/math-input/MatrixBuilder.tsx:64,72 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| Plus / 新增 | Lucide React | frontend/src/pages/GoalsPage.tsx:211 | size={16}  | 1 | P3 | Keep（几何校正） |
| Printer / 打印 | Lucide React | frontend/src/components/chat/ChapterHighlightCard.tsx:19 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Printer / 打印 | Lucide React | frontend/src/pages/HighlightPage.tsx:153 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:69 | className="h-4 w-4 text-[var(--warning)]"  | 1 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/components/settings/DataSafety.tsx:95 | className="h-4 w-4"  | 1 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:156,212 | className="h-4 w-4" ; className={`h-4 w-4 ${reindexing ? 'animate-spin' : ''}`}  | 2 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/components/settings/MobileRemoteS0.tsx:31 | size={16} | 1 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/components/SystemHealth.tsx:487,500 | className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} ; className="h-3.5 w-3.5"  | 2 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/features/textbooks/FigureAuditPanel.tsx:65 | className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}  | 1 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/pages/LearningPage.tsx:348 | className="h-4 w-4"  | 1 | P2 | Consolidate |
| RefreshCw / 刷新/重试 | Lucide React | frontend/src/pages/WeeklyReportPage.tsx:70 | className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`}  | 1 | P2 | Consolidate |
| RotateCcw / 恢复/撤销 | Lucide React | frontend/src/components/chat/LearningTaskResume.tsx:22 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| RotateCcw / 恢复/撤销 | Lucide React | frontend/src/components/settings/DataSafety.tsx:124 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| RotateCw / 重试/旋转 | Lucide React | frontend/src/features/mistakes/components/ProblemImageEditor.tsx:184 | className="h-4 w-4"  | 1 | P2 | Consolidate |
| RotateCw / 重试/旋转 | Lucide React | frontend/src/layouts/MainLayout.tsx:262 | className="h-3.5 w-3.5"  | 1 | P2 | Consolidate |
| Save / 保存 | Lucide React | frontend/src/components/SystemHealth.tsx:429,555 | className="h-4 w-4"  | 2 | P3 | Keep（几何校正） |
| Scan / 裁剪识别 | Lucide React | frontend/src/features/visual-learning/FigureContextAttachment.tsx:27 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Scan / 裁剪识别 | Lucide React | frontend/src/features/visual-learning/FigureRegionViewer.tsx:100 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Search / 搜索 | Lucide React | frontend/src/features/visual-learning/FigureCatalog.tsx:59 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| Search / 搜索 | Lucide React | frontend/src/pages/ExercisesPage.tsx:668 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Search / 搜索 | Lucide React | frontend/src/pages/MistakesPage.tsx:179 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Send / 发送 | Lucide React | frontend/src/pages/ChatPage.tsx:1158 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Settings / 设置 | Lucide React | frontend/src/components/AppRail.tsx:62,73 | className="h-[18px] w-[18px]"  | 2 | P3 | Keep（几何校正） |
| ShieldAlert / 风险提示 | Lucide React | frontend/src/components/ChatMessage.tsx:293 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Shuffle / 随机练习/命题入口 | Lucide React | frontend/src/components/chat/ExerciseCard.tsx:55 | className="h-4 w-4 text-accent"  | 1 | P1 | Redesign |
| Shuffle / 随机练习/命题入口 | Lucide React | frontend/src/pages/ChatPage.tsx:1145 | className="h-3.5 w-3.5"  | 1 | P1 | Redesign |
| Sigma / 公式输入 | Lucide React | frontend/src/features/math-input/VisualMathInputPopover.tsx:137 | className="h-4 w-4" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| SlidersHorizontal / 筛选/参数 | Lucide React | frontend/src/features/mistakes/components/ProblemImageEditor.tsx:183 | className="h-4 w-4 text-accent"  | 1 | P3 | Keep（几何校正） |
| Smartphone / 手机连接 | Lucide React | frontend/src/components/settings/MobileRemoteS0.tsx:29,31 | size={24}; size={16} | 2 | P3 | Keep（几何校正） |
| Square / 停止或最大化 | Lucide React | frontend/src/components/DesktopTitleBar.tsx:30 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| Square / 停止或最大化 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:511 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Square / 停止或最大化 | Lucide React | frontend/src/features/focus/FocusController.tsx:149 | size={14}  | 1 | P3 | Keep（几何校正） |
| Square / 停止或最大化 | Lucide React | frontend/src/pages/ChatPage.tsx:1154 | className="h-4 w-4 fill-current"  | 1 | P3 | Keep（几何校正） |
| Target / 目标与任务 | Lucide React | frontend/src/components/AppRail.tsx:7 | 动态映射 / 容器 CSS | 1 | P1 | Redesign |
| Target / 目标与任务 | Lucide React | frontend/src/pages/ChatPage.tsx:1142 | className="h-3.5 w-3.5"  | 1 | P1 | Redesign |
| Timer / 专注计时 | Lucide React | frontend/src/features/focus/FocusController.tsx:141,168 | size={14} aria-hidden="true" ; size={15} aria-hidden="true"  | 2 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:517 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:140,231 | className="h-3.5 w-3.5"  | 2 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/components/settings/ModelSettingsManager.tsx:256 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/features/focus/FocusPanel.tsx:41 | size={14} | 1 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/features/math-input/MathExpressionList.tsx:37 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| Trash2 / 删除 | Lucide React | frontend/src/features/notes/NoteBlocks.tsx:40 | size={16} | 1 | P3 | Keep（几何校正） |
| Upload / 导入/上传 | Lucide React | frontend/src/pages/BooksPage.tsx:274,343,378 | className="mb-4 h-9 w-9 text-accent" ; className="h-4 w-4"  | 3 | P3 | Keep（几何校正） |
| Upload / 导入/上传 | Lucide React | frontend/src/pages/ExercisesPage.tsx:519,636 | size={24} ; size={22}  | 2 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/chat/ExecutionTrace.tsx:27,109 | className="text-[var(--danger)]" ; 动态映射 / 容器 CSS | 2 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/chat/LearningTaskActions.tsx:71 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/chat/QuestionImage.tsx:18 | size={20}  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/chat/SubjectRouteSuggestionCard.tsx:134 | className="h-3.5 w-3.5"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/DesktopTitleBar.tsx:31 | 动态映射 / 容器 CSS | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/HighlightRepositoryDialog.tsx:393 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/settings/LibraryWorkbench.tsx:103 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/settings/SettingsDialog.tsx:33 | className="h-[18px] w-[18px]"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/components/ui/ContextInspector.tsx:32 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/focus/FocusController.tsx:130 | size={16}  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/math-input/VisualMathInputPopover.tsx:160 | className="h-4 w-4" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/mistakes/components/ProblemImageEditor.tsx:171 | className="h-5 w-5"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/textbooks/BookDeleteDialog.tsx:10 | size={16}  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/textbooks/ConceptExtractionStatus.tsx:22 | size={16}  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/textbooks/FigureAuditPanel.tsx:65 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/textbooks/OutlineCalibrationPanel.tsx:21 | size={16}  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/visual-learning/FigureContextAttachment.tsx:34 | className="h-3.5 w-3.5" aria-hidden="true"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/features/visual-learning/FigureRegionViewer.tsx:83 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/pages/ChatPage.tsx:1100 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/pages/ExercisesPage.tsx:736 | className="h-4 w-4"  | 1 | P3 | Keep（几何校正） |
| X / 关闭/移除/失败 | Lucide React | frontend/src/pages/UserGuidePage.tsx:59 | size={18}  | 1 | P3 | Keep（几何校正） |

## 非库来源清单

| Icon / Semantic Name | Source / Location | Size | Frequency | Priority | Recommendation |
|---|---|---|---|---|---|
| Texa mark / 品牌 | frontend/public/brand/texa-mark.svg；AppRail、FirstRunGuide、RemoteConnectionGate | 容器决定 | 3 个组件 | P3 | Keep；品牌不在改造范围 |
| Favicon | frontend/public/favicon.svg；index.html | 浏览器 | 1 入口 | P3 | Keep |
| 社交/文档 symbol | frontend/public/icons.svg：bluesky、discord、documentation、github、social、x | 16–21 viewBox | src 中无 use / 文件引用 | P3 | Remove 候选；本次保留待资产使用方确认 |
| Logo 源文件 | icon/Texa_Logo_*.svg、PNG；desktop/assets | 原生品牌资产 | 不计业务 UI 频率 | P3 | Keep |
| 用户指南截图 | frontend/public/guide/*.png | 响应式截图 | 内容资产 | P3 | Keep；不是可替换 UI 图标 |
| 下拉箭头 / disclosure | index.css:1883 CSS 双三角；DesktopRefinement.css:55 › | 5px 三角 / 字体字号 | 全部原生 select / 1 条样式规则 | P2 | Consolidate；下拉与展开分别命名 |
| 原生 macOS 窗口按钮 | Electron 原生框架 | OS 控制 | 平台生成 | P3 | Keep |
| Windows 窗口按钮 | DesktopTitleBar：Minus / Square / Copy / X | CSS 容器 | 3 控件 | P3 | Keep；独立 window-* 语义 |

以下是非库图形符号的完整源码命中；包括正则解析与数学内容，防止误替换。

- frontend/src/components/ChatMessage.tsx:62 — `const match = content.match(/^📎\s*([^\r\n]+)\r?\n(?:\r?\n)+([\s\S]*)$/);`
- frontend/src/components/settings/NetworkDiagnostics.tsx:68 — `<ul className="settings-secondary">{data?.history.slice(-8).reverse().map((entry, index) => <li key={′${entry.sampled_at}-${index}′}>{time(entry.sampled_at)} · {entry.previous_path ? paths[entry.previous_path] : '初始'} → {paths[entry.path]} · {entry.source}{entry.derp_region ? ′ (${entry.derp_region})′ : ''}</li>)}</ul>`
- frontend/src/features/exercises/components/BatchCandidateReceipts.tsx:25 — `return <details className="exercise-import-receipts"><summary>批次 {batch.id} · 来源与导入时校对信息</summary>{batch.candidate_receipts?.length ? <><button className="app-secondary-button" onClick={() => void check()}>核对正文版本</button>{batch.candidate_receipts.map(receipt => <details key={receipt.exercise_id}><summary>{receipt.origin_id} → {receipt.exe`
- frontend/src/features/guide/content.ts:25 — `instructions: ['首次打开时按引导连接；以后在“设置 → 模型连接”修改。选择服务商和模型，填写 API Key（模型服务的访问密钥）。自定义服务还需填写服务地址和 Model ID。', '按当前方案使用“测试文字连接”或“测试识图能力”，检查反馈；再点“保存并继续”或“保存并应用”。', '回到“学习”发一条问题，确认能收到回答。'],`
- frontend/src/features/guide/content.ts:40 — `instructions: ['在学习会话的三点菜单选择“整理为笔记”。选择全部会话或部分轮次，再生成草稿。', '检查并编辑标题与正文，点“保存笔记”。', '到“笔记 → 已保存”重新打开；以后编辑正式笔记，要点“保存修改”。'],`
- frontend/src/features/guide/content.ts:81 — `instructions: ['打开“练习 → 导入”，从已导入教材抽取，或上传 .docx / 含文字的 .pdf；也可手动录入。先用少量完整题目试一次。', '进入“校对候选题”，用“原文对照”检查题干、条件、答案与解析。需要时编辑、拆分或合并；页面要求时点“确认本题结构”。', '选择完整的题目，点“确认入库”。检查新增、重复和待处理回执，再到“题库”重开一道题。'],`
- frontend/src/features/guide/content.ts:122 — `instructions: ['到“设置 → 数据与教材”创建备份。需要时选择同时备份向量检索和 MinerU 产物，完成后查看校验结果、详情及保存位置。', '恢复前核对日期、包含范围和当前数据的安全副本。恢复按备份所含数据目录替换，同目录中新记录可能被覆盖。', '恢复在重启时执行；重开后分别核对教材、会话、笔记、作答、错题和目标，不只看登记提示。'],`
- frontend/src/features/guide/content.ts:132 — `more: { title: '手机连接（可选）', text: '在桌面“设置 → 手机连接”按提示准备 Tailscale，用本人手机打开地址并配对。电脑和本地服务需保持运行；手机访问同一份资料，不是独立同步副本。不要分享配对码。候选发行包、真实手机与重启配对行为仍待实测。' },`
- frontend/src/features/guide/rentedMineru.ts:6 — `instructions: ['需要租卡时再看本节，已有输出包可直接导入。在 AutoDL 等平台租一张 4090 或 5090，选适配的 Ubuntu 镜像，在实例终端安装 MinerU。下面以 AutoDL 容器实例为例。', '上传一本 PDF，先试解析 3 页，核对公式、表格和附图，再处理整本书；按下方清单检查输出并打包。', '下载 ZIP 到自己的电脑并校验，确认实例关机，再用 Texa“教材 → 导入教材 → MinerU 输出包”导入。'],`
- frontend/src/features/guide/rentedMineru.ts:51 — `paragraphs: ['回到运行 Texa 的电脑，打开“教材 → 导入教材”，选择“MinerU 输出包”。先将本机 ZIP 改为易辨认的教材名（教材名称取自文件名），选择该 ZIP 和所属科目，再点“导入输出包”。此路径复用已解析产物，不需要本机安装 MinerU，也不需要把云实例长期保持开机。', '等待最终可用状态后回教材列表，“设为学习范围”。用原书一个明确概念提问，点“查看来源”检查教材、页码、公式与附图。导入完成只表示系统接受并建立了资料，不证明 OCR 或回答完全正确。', '若提示多文档歧义、文件损坏、超限或没有正文，先检查第 4 步的结构和材料，不反复上传同一包。确认原 PDF 随包保留且来源可核对；教材导入不会自动建立练习题库。'],`
- frontend/src/features/math-input/mathQuickKeys.ts:21 — `{ id: 'minus', label: '−', latex: '-', description: '输入减号' },`
- frontend/src/features/math-input/mathTemplates.ts:22 — `{ id: 'square-root', label: '√x', description: '平方根', category: 'common', value: '$\\sqrt{[[selection|表达式]]}$' },`
- frontend/src/features/math-input/mathTemplates.ts:23 — `{ id: 'nth-root', label: 'ⁿ√x', description: 'n 次根', category: 'common', value: '$\\sqrt[[cursor|n]]{[[selection|表达式]]}$' },`
- frontend/src/features/math-input/mathTemplates.ts:25 — `{ id: 'less-equal', label: '≤', description: '小于等于', category: 'common', value: '$\\le$' },`
- frontend/src/features/math-input/mathTemplates.ts:26 — `{ id: 'greater-equal', label: '≥', description: '大于等于', category: 'common', value: '$\\ge$' },`
- frontend/src/features/math-input/mathTemplates.ts:27 — `{ id: 'not-equal', label: '≠', description: '不等于', category: 'common', value: '$\\ne$' },`
- frontend/src/features/math-input/mathTemplates.ts:28 — `{ id: 'approximately', label: '≈', description: '约等于', category: 'common', value: '$\\approx$' },`
- frontend/src/features/math-input/mathTemplates.ts:29 — `{ id: 'infinity', label: '∞', description: '无穷', category: 'common', value: '$\\infty$' },`
- frontend/src/features/math-input/mathTemplates.ts:30 — `{ id: 'arrow', label: '→', description: '趋于或映射到', category: 'common', value: '$\\to$' },`
- frontend/src/features/math-input/mathTemplates.ts:39 — `{ id: 'partial-derivative', label: '∂f/∂x', description: '偏导数', category: 'calculus', value: '$\\frac{\\partial [[selection|f]]}{\\partial [[cursor|x]]}$' },`
- frontend/src/features/math-input/mathTemplates.ts:40 — `{ id: 'indefinite-integral', label: '∫', description: '不定积分', category: 'calculus', value: '$\\int [[selection|f(x)]]\\,d[[cursor|x]]$' },`
- frontend/src/features/math-input/mathTemplates.ts:41 — `{ id: 'definite-integral', label: '∫ₐᵇ', description: '定积分', category: 'calculus', value: '$\\int_{[[cursor|a]]}^{b} [[selection|f(x)]]\\,dx$' },`
- frontend/src/features/math-input/mathTemplates.ts:42 — `{ id: 'double-integral', label: '∬', description: '二重积分', category: 'calculus', value: '$\\iint_{[[cursor|D]]} [[selection|f(x,y)]]\\,dx\\,dy$' },`
- frontend/src/features/math-input/mathTemplates.ts:50 — `{ id: 'cross-product', label: 'a×b', description: '叉积', category: 'linear-algebra', value: '$[[selection|\\mathbf{a}]]\\times [[cursor|\\mathbf{b}]]$' },`
- frontend/src/features/math-input/mathTemplates.ts:55 — `{ id: 'matrix-2', label: '2×2', description: '二阶矩阵', category: 'linear-algebra', value: '$$\n\\begin{bmatrix}\n[[selection|a]] & b \\\\\n c & d\n\\end{bmatrix}\n$$' },`
- frontend/src/features/math-input/mathTemplates.ts:56 — `{ id: 'matrix-3', label: '3×3', description: '三阶矩阵', category: 'linear-algebra', value: '$$\n\\begin{bmatrix}\n[[selection|a]] & b & c \\\\\n d & e & f \\\\\n g & h & i\n\\end{bmatrix}\n$$' },`
- frontend/src/layouts/DesktopRefinement.css:55 — `.goal-assistance > summary::before { content:'›';margin-right:8px; }`
- frontend/src/pages/ChatPage.tsx:410 — `const label = ′📎 教材图 · ${activeFigure.page ? ′p.${activeFigure.page}′ : '未标页'}\n\n${question}′;`
- frontend/src/pages/ChatPage.tsx:484 — `? ′📎 ${attachmentFile.name}\n\n${question || '请完整讲解这道题'}′`
- frontend/src/pages/ExercisesPage.tsx:647 — `</article>)}<button className="app-ghost-button" onClick={() => setWorkspaceMode('bank')}>查看题库 →</button>`
- frontend/src/pages/LearningPage.tsx:473 — `? ′涉及 ${item.concepts.map((concept) => ′${concept.name}${concept.count > 1 ? ′ ×${concept.count}′ : ''}′).join('、')}′`

## 后续迁移边界

优先 AppRail、ScopeSelector、LibraryWorkbench、ChatPage 输入控件与 ExecutionTrace；然后 features/exercises、notes、focus、visual-learning 和设置/状态组件。生产迁移需单独批准；本次库存是静态全集，20 个候选样本并非全部生产资产。单独的设计板不导入业务组件、不连接 API。
