# 2026-08-27 - Canonical Figure Visual Learning V1

- 在主聊天和现有 Learning Canvas 内新增教材 Figure 选择与查看，不新建平行 Agent 页或状态机。Figure/Region 只作为当前会话的临时前端状态；旧教材尚无 Canonical Figure 时明确提示重新导入，不伪造图片列表。
- 后端新增有界 Figure 列表、详情和受控图片读取接口；Figure context 从 Canonical 顺序中收集同章节前后文本块并映射相关 chunk IDs，不强制 Figure 进入普通向量检索。
- 用户选区统一为基于图片自然尺寸的 `[x1, y1, x2, y2]` 归一化坐标；服务端校验范围、方向和最小尺寸，Pillow crop 只是确定性 runtime helper，不注册为模型工具，临时 crop 在请求结束时清理。
- 视觉请求沿用独立 vision model role，一次请求可携带完整 Figure、同一 Figure 的局部 crop 和只读教材上下文；缓存图与选区的角色会显式标注。SSE 显示 context/crop/vision 活动，最终回答必须绑定请求中的 Figure/Page E1 来源。
- 前端 Figure Viewer 支持单击、拖框、重新框选、清除选区、中心选区、教材页来源，以及方向键移动 / `Shift + 方向键` 调整大小的键盘备选操作。

## Validation

- Python 全量回归：596 passed，1 个既有 Starlette/httpx 弃用警告；Frontend Vitest：21 files / 112 tests，ESLint 和 TypeScript 通过。
- 真实 MinerU 样本 `CGQ_2_content_list.json` 以系统临时目录验收：原始 Figure 508、Canonical Figure 508、有图注 455、有效稳定资产 508；Figure 列表 total 508，首幅 context 关联 6 个邻近 block / 3 个 chunk，intake report 有效。无图注但带 `image_footnote` 的 6 幅图保留为独立 `source_text`，不误计为 caption。
- 运行态验证覆盖 900 / 1280 / 1600px，Figure 入口、Inspector 空状态和响应式布局无 body 横向溢出。现有本地教材尚未用 Figure ingestion 重新导入，因此未为 UI 实跑擅自改写用户教材数据；完整选区几何和 SSE 流程由定向回归覆盖。未调用付费多模态模型。

# 2026-08-27 - 教材库高密度管理工作台

- `/books` 移除居中 `max-w-6xl` 容器，改为 App Rail 后的全宽双栏工作台：240px 分类树与占满剩余宽度的教材主区；1024px 下分类树收窄至 224px，窄窗口转为上下区域并保持主列表内部滚动。
- 分类名称从常驻输入框改为按需 inline rename；有教材的分类继续禁止重命名和删除，阻塞原因收进控件 title，不再长期展示重复说明。
- 教材记录从纵向详情块改为稳定的“教材 / 索引与 IR / 归属与资料组 / 角色 / 操作”紧凑行。检索与 Canonical IR 保持直接可见，语义质量说明转入 title；主要/辅助/独立角色说明不再逐条重复展示。
- 当前教材改为低权重状态，其他教材提供明确“设为当前”动作；重索引与更多菜单保持固定操作列。归档教材从页面尾部独立 section 改为“活跃 / 已归档”列表筛选，恢复逻辑不变。
- 教材归属不再使用扁平分组选项，改为复用问答、错题页的 `ScopeSelector` 学科树与一级/二级联动；由教材管理页直接注入已加载分类，避免每条教材重复请求分类接口。
- 移除教材页单独放大的 24px 标题和重复“教材管理”toolbar，合并为共享页面 Header。成功/普通检查结果改为 3.6 秒自动消退的 transient status；错误继续保留，版本页只持续展示可更新、下载、安装或错误等行动状态，不再常驻开发模式提示。

## Validation

- 1366×768 与 1600×900 下分类树为 240px，主区无居中留白，教材行稳定为 108px；1024×768 下行高约 115px，700×650 下转为上下区域，页面无 body 横向溢出。
- 1366×768 运行态确认教材页只保留一个 18px 页面标题；教材归属弹层呈现一级/二级分类联动，版本页初始无持久 Banner 或开发模式更新提示。
- 前端 ESLint、TypeScript 与 Vite production build、Vitest 全量测试及 `git diff --check` 通过；构建仅保留既有 MathLive 大 chunk 与 MarkdownRenderer 混合导入警告。

# 2026-08-27 - Settings 浮窗与配置页面语法统一

- 左下角“设置”从独立 Workspace 路由改为覆盖当前工作区的应用级 Dialog；保留 `/settings` 兼容入口，并新增 ESC、Tab 焦点圈定、关闭后焦点恢复和未保存草稿保留。
- Dialog 使用固定 header、160px 分组侧栏和独立滚动 content；窄窗口改为横向紧凑导航，避免双滚动条与横向溢出。
- 六个设置页统一标题、说明、section、divider、表单与操作层级；移除健康、版本、备份、外观中的大面积 Card 包裹，只为真实状态或备份实体保留必要边界。
- 完成纯 UI density refinement：文字层级收敛为 24/16/14/13px，表单标签列统一为 144px，主要控件与 primary action 统一为 36px；侧栏条目、圆角、行距和辅助文字对比度同步收敛。健康状态与外观列表移除 row-level divider，模型配置删除重复说明并将“模型名称”改为“显示名称”。
- 外观继续即时应用；模型配置与教材解析继续显式保存。模型 Provider、custom model、credential 与连接测试数据流未改，MinerU 教材解析仍独立于 LLM Provider。

## Validation

- Frontend Vitest：20 files / 105 tests；ESLint、TypeScript 与 Vite production build 通过。
- 模型设置定向 Python 回归：9 passed；`git diff --check` 通过。
- 浏览器运行态覆盖 1366×768 与 700×650：六页标题和内容骨架正确，长模型页仅右侧滚动，无横向溢出；ESC、Tab 回绕、焦点恢复、草稿保留和 `/settings` 兼容入口均通过，控制台无错误。
- 六页 refinement 复核未发现低于 13px 的可见正文或遗留的大型表单控件；模型页高度由约 1004px 收敛至约 803px，紧凑 Select 选项行为和自定义模型字段顺序保持正确。
- 构建仍保留既有 MathLive 大 chunk 与 MarkdownRenderer 动态/静态混合导入警告。

# 2026-08-27 - 教材就绪状态、重新索引与 MinerU 导入引导

- 教材库从真实索引 manifest、Canonical IR 与 ingestion report 派生三项独立状态：检索索引、Canonical IR、语义质量；自动结构探针不再被表述为语义验证，只有包含人工案例的 release quality 才显示“已验证”。
- 教材行新增可见的“重新索引”操作，复用已有 staged candidate 发布流程；执行期间显示进行态，成功或失败后刷新教材状态并给出明确反馈。
- 新增有界的 MinerU API/CLI 可用性检查。首次进入导入页默认使用本地文本提取；仅在 MinerU 实际可达时自动选择 MinerU，不可用时明确提供本地文本模式与 MinerU 输出包两条路径。

## Validation

- Python 全量回归：588 passed，1 个既有 Starlette/httpx 弃用警告。
- Frontend 契约测试：17 passed；ESLint 与 TypeScript + Vite production build 通过，仅保留既有 MathLive chunk 提示。

# 2026-08-26 - Docker 干净部署嵌入运行时修复

- Docker 后端依赖改为直接安装已锁定、Torch-free 的 requirements-release.txt，避免 requirements.txt 引用未复制的开发依赖文件导致干净构建失败。
- 镜像显式携带版本化 BGE ONNX 模型、tokenizer 与 manifest，并固定 TEXA_EMBEDDING_BACKEND / TEXA_EMBEDDING_ASSET_DIR；容器首次启动不再依赖下载 embedding。
- docker build 在产出镜像前执行完整 SHA-256 资产校验，缺文件、大小不符、manifest 合同不兼容或哈希损坏都会直接阻断构建；Compose 与部署文档同步为本地只读资产语义。

## Validation

- Docker release contract 回归覆盖 release 依赖、ONNX 资产复制、显式运行时绑定和构建期 full-hash gate。
- 本机仍未安装 Docker；已完成仓库内真实 ONNX 资产 full-hash 校验与 Python 回归，容器 build/start 需在有 Docker 的干净环境继续执行。

# 2026-08-26 - MinerU Figure Canonical Artifact 保真

- MinerU JSON 导入改为按 payload 结构确定性识别 content-list v1、content-list v2 与 middle，不再依赖 `rglob()` 的首个遍历结果；Figure 保留图注、页码、page bbox、章节路径、来源和原始图片相对路径。
- Figure 继续沿用 `DocumentBlock + attributes`，`figure_id` 复用 `block_id`。导入时将图片原子复制到每本教材的 `figures/<block_id>.<ext>`，Canonical IR 仅保存受控相对路径、SHA-256、像素尺寸和明确的 page/xyxy 坐标语义；重复导入保持相同 identity、路径和内容哈希。
- 空图注 Figure 不再被 Canonical splitter 丢弃；兼容 `_middle_chunks.json` 中保留 provenance-only artifact，同时以 `retrieval_excluded` 避免强行进入普通文本索引。图片缺失或损坏会在 block review status、book warning 和 ingestion report 中明确降级，不阻断仍可用的正文。

## Validation

- 定向回归：45 passed，覆盖 v1/v2/middle、确定性格式选择、图片路径/图注/page/bbox/section_path、空图注、缺失资产、稳定复制、幂等性、Canonical 持久化和文本索引边界。
- Python 全量回归：581 passed，1 个既有 Starlette/httpx 弃用警告；现有文本 ingestion、Canonical splitter、角色分配、词法/向量索引相关测试无回归。
- 真实 MinerU 样本 `CGQ_2_content_list.json`：原始 Figure 508、Canonical Figure 508、有图注 455、有效稳定资产 508，Canonical intake report 有效。
- 仓库 12 个现存候选 JSON 均可明确分类：content-list v1 4 个、v2 4 个、middle 4 个，无未知 payload shape 或 JSON 读取错误。

# 2026-08-26 - 问答执行轨迹统一事件流

- 保留现有 SSE 与 `stage` 协议，新增版本化 `texa.execution/v1` 事件：用单调 `seq`、稳定 `operation_id` 和明确的 `type / phase / status` 描述真实进度、工具调用、工具结果、状态转换与终态；兼容层继续投影旧 `activity`。
- Planner、教材检索与模型流改由 worker queue 驱动。阻塞超过 10 秒时只发送中性、低频的等待进度；首个可展示 token 到达后停止等待提示，不向前端暴露模型 thinking 或 hidden reasoning。
- 工具编排在每次 registry 调用前后实时发送 `tool_call / tool_result`，运行中发现的数学校验工具按实际插入顺序呈现。LearningTask 仅有界保存关键状态转换、工具结果和终态，不保存 heartbeat、工具开始或 token delta。
- 前端按 `seq + operation_id` 投影到现有 Learning Canvas / ExecutionTrace，忽略乱序和无序号的陈旧更新；移除固定阶段正文占位，正文区域只承载真实回答。
- 根据真实长请求复核，补充发送后立即可见的本地 transport 状态；首个后端事件到达后明确切换为“执行流已连接”。运行中改为开放式事件日志并显示当前操作实际等待时长，终态默认折叠为低权重披露，不再把执行过程呈现为占据回答首屏的固定步骤卡。
- 收紧终态“查看执行过程”披露控件：字号降为 caption 级，图标、箭头、行高和垂直点击留白同步减小，使其与“回答 / 教材依据 / 来源”元信息处于同一视觉层级。
- SSE 响应显式设置 `no-cache, no-transform` 与 `X-Accel-Buffering: no`，避免桌面代理或中间层聚合小事件。真实记录显示最近一次长问答的 124.8 秒中，约 114 秒消耗在模型首个可展示 token 之前，而不是冷启动或检索阶段。

## Validation

- Python 全量回归：577 passed，1 个既有 Starlette/httpx 弃用警告；新增覆盖事件持久化边界、动态工具顺序、阻塞阶段 progress 与无 CoT 契约。
- Frontend Vitest：19 files / 95 tests；ESLint 与 TypeScript + Vite production build 通过，仅保留既有 MathLive chunk 提示。
- 运行态验证：SSE 建连后立即显示“读取会话上下文”，完成后按真实事件更新 ExecutionTrace；1024px 与 1440px 桌面宽度下无横向溢出，控制台无 warning/error。

# 2026-08-23 - Canonical block 原生切分与索引 schema v5

- `ChapterSplitter` 新增 `split_blocks()` / `split_canonical_book()`：公式块保持原子性；结构化表格过大时只按行拆分并为每个子块重复表题、表头；例题/习题的题干、条件与答案通过稳定 `parent_id` 关联；普通段落在相同章节和来源内累积后切分。
- 统一 chunk 继承章节路径、页范围、bbox、公式、复核状态、来源类型/文件、OCR 置信度与源 block 位置，并在全书范围生成确定性的 `chunk_id`、`parent_id` 和闭合的前后邻接关系。
- 新教材导入在任何向量/词法索引写入前，必须先通过 CanonicalBook 确定性体检并落盘 `canonical_document.jsonl` 与 `ingestion_report.json`；已有 canonical 的重建索引优先走 block 路径，没有 canonical 的历史教材继续保留章节字符串兼容路径。
- Chroma 与 BM25 索引 schema 提升到 v5，新增页范围、来源、OCR、源 block 与结构化表格元数据；保留 `_middle_chunks.json` 作为当前兼容/回滚派生产物，不再作为新导入的上游输入。
- Word 适配器增加保守的显式“例题/习题”标签识别，并把紧随的条件、解答、答案归入同一逻辑组；未命中明确标签的正文仍按普通段落处理。

## Validation

- 四类契约 fixture 覆盖文本 PDF、公式/表格密集 MinerU、扫描 OCR、含标题/表格/例题的 Word；断言章节路径、公式原子性、表头保留、例题父子关系、来源回溯和邻接闭合。
- Python 全量回归：515 passed，1 个既有 Starlette/httpx 弃用警告。

# 2026-08-21 - README 深色主题 Logo 对比度

- README 顶部品牌图改用白底 `Texa_Logo.png`，避免透明深色字标在 GitHub 深色主题下失去对比度。

# 2026-08-21 - 项目首页与仓库展示整理

- 按当前 Electron 产品形态重写根 README，聚焦产品目的、核心功能、学习流程、架构、目录、安装与发展方向；移除阶段性实现状态和代码审计入口。
- 使用当前桌面端实机界面更新学习工作区、复习计划、错题录入与教材库截图，并同步静态站点的截图和产品叙事。
- 删除阶段性 `PROJECT_AUDIT.md`、旧截图归档、重复 UI 重建截图与编码审计输出；保留仍承担技术回归用途的基准结果，并忽略后续本地截图/审计产物。

# 2026-08-21 - 页面切换保持工作区状态

- 页面模块改为随桌面前端一次就绪，彻底移除路由级“正在打开页面”状态；访问过的工作区继续保持挂载，问答正文、输入草稿、滚动位置、页面列表和进行中的回答不会因切换页面被销毁。
- 学习上下文侧栏改为始终挂载、按场景隐藏，返回问答页时不再重新创建组件和请求历史；教材与会话摘要保留最近一次成功的本地快照，后续启动先显示快照、再后台校准，请求失败也不会清空已有历史。
- 验证：Frontend Vitest 19 files / 90 tests、TypeScript + Vite production build 通过；浏览器实测问答 → 复习 → 问答后草稿和历史区域保持，760px 最小窗口、1280px 普通窗口与 1600px 宽屏下当前工作区唯一且 Composer 可用。

# 2026-08-21 - 记事本与灰白黑外观主题

- 新增“记事本”与“灰白黑”主题。记事本采用温和纸面、墨色正文与暗金操作色；灰白黑采用中性壳层分区与黑色操作信号，不复制参考产品的具体色值或布局。
- 两套主题继续使用矿物、石墨和陶土相同的语义 token 合同，完整覆盖选择态、滚动条和学习热力图；切换即时生效并保存在当前设备。
- 扩展主题注册表与 Texa UI 契约测试；Electron 运行态已覆盖外观列表、两套主题切换、空会话与历史对话工作区。

# 2026-08-21 - 语义主题色与外观切换

- 将默认强调色从通用淡蓝调整为低饱和矿物绿，并重新校准冷中性背景、边框、正文层级、选择态和焦点态，降低默认 Web UI 与 Toy Project 感。
- 新增“矿物 / 石墨 / 陶土”三套浅色主题。设置页新增“外观”入口，选择后立即应用并保存在当前设备；主题通过统一注册表映射语义 token，后续可继续增加皮肤而无需改写业务组件。
- 学习活动热力图与表单焦点不再写死蓝色，改为消费主题 token；补充主题注册表单元测试与 Texa UI 契约约束。

# 2026-08-21 - 新会话“更多”菜单可用性修复

- 修复聊天输入框的“更多”菜单只在已有消息时渲染的问题；新建空会话现在也可直接使用学习日报、学习周报、随机抽题、查看/生成重点和错题速录。
- 新增 UI 契约回归约束，避免再次把 Composer 的 OverflowMenu 与 `messages.length` 绑定。
- 验证：前端定向 Vitest 9 项、ESLint、TypeScript 与 Vite 生产构建通过；Electron 在普通窗口和最大化宽屏下实测空会话可见并可展开“更多”菜单。

# 2026-08-20 - 模型方案管理与 Provider 切换状态修复

- 修复模型配置页切换 Provider 时清空 `configured` 状态的问题。Credential 改为独立槽位，同一 Provider 切走再切回会恢复已保存状态；显式槽位不会误用其他 Provider 遗留的角色密钥。
- 新增本地模型方案管理：方案可命名、保存、删除和一键启用，可组合推理模型、识图模型与 split/native 图片模式。方案结构保存在 `data/model_profiles.json`，API Key 仍只写入 `.env`，不会进入方案文件或接口响应。
- Provider 与模型方案改为带前后控制、snap 定位的横向滑动列表；自定义 OpenAI-compatible 被选中时立即显示服务地址和可选 API Key。
- native 图片模式下连接名称改为“普通问答连接 / 图片任务连接”；移除模型页说明卡、角色副标题和重复小字，保留单一保存动作。

## Validation

- Python 全量回归 486 项通过；Frontend ESLint、Vitest 18 files / 83 tests、TypeScript + Vite production build 通过。
- 本地隔离后端实测：Moonshot/Kimi → Qwen → Moonshot/Kimi 后 API Key 仍显示“已配置”；自定义 OpenAI-compatible 选中后同层立即出现服务地址；native 模式连接显示为“普通问答连接 / 图片任务连接”。
- 1280×800 与 1600×900 两轮截图复核通过：方案/Provider 滑动轨道不产生页面横向溢出，主层级无说明卡、角色副标题或小号模板文案。

# 2026-08-20 - 模型角色配置与 Multi-Provider 调用层解耦

- 新增 Provider 注册表、模型角色解析和 Transport 工厂，业务调用不再通过 `if provider == ...` 创建 SDK 客户端；内置 DeepSeek、Moonshot/Kimi、Qwen、Gemini、OpenAI、Ollama 与自定义 OpenAI-compatible 配置。
- 模型配置拆分为推理模型与识图模型，每个角色独立配置 Provider、模型名、凭据和 Endpoint；默认继续使用 DeepSeek 推理与 Moonshot/Kimi 识图，并兼容旧版环境变量。
- 设置页和首次运行引导共用角色配置组件。API Key 只提交给后端并写入本地 `.env`，状态接口不返回密钥；Base URL 默认折叠在高级连接参数中，可填写任意 OpenAI-compatible 地址和模型名。
- 图片任务保留 `split` 模式，并新增 `native` 模式让识图角色对应模型继续完成推理；目录识别、按页视觉阅读、章节图片问答和错题图片解析改为读取统一识图角色。

## Validation

- Python 全量回归 482 项通过，覆盖旧配置兼容、Provider/Model capability 校验、自定义 Endpoint/模型、密钥不回显与模型缓存。
- Frontend ESLint、Vitest 18 files / 83 tests、TypeScript + Vite production build 通过；仅保留既有 MathLive 大 chunk 提示。

# 2026-08-16 - 问答页教材来源面板可正常关闭

- 根因：来源/概念面板（`ContextInspector`）在窄窗 overlay 态下只有关闭按钮与 Esc 两种退出方式，点击面板外区域不会关闭，用户感知为面板“关不掉”。
- 在 `frontend/src/components/ui/ContextInspector.tsx` 为面板挂载 `ref`，面板打开期间在 `document` 捕获阶段监听 `pointerdown`，点击落在 `<aside>` 外即 `closeInspector()`；监听随面板卸载自动移除。与既有 `ComposerOverflowMenu` 的 outside-dismissal 模式保持一致。
- 未改动来源数据结构、引用逻辑与任何 backend；关闭按钮、Esc 关闭（`InspectorContext` 既有实现）与 `openInspector` 替换旧面板状态保持不变。

## Validation

- 在运行中的 Electron/前端（1280 宽、inspector overlay 态）用真实来源面板逐项验证：关闭按钮关闭 ✓、点击面板外关闭 ✓、Esc 关闭 ✓、来源→概念新面板替换旧状态且仅保留一个面板 ✓。
- Frontend TypeScript `tsc -b` 通过；Vitest 18 files / 83 tests passed。

# 2026-08-15 - Electron 原生窗口控制回归修复

- 在用户当前 Texa 窗口中复现：React 自绘最大化按钮的 46px DOM 区域可见，但真实桌面点击被 frameless drag hit-test 吞掉；此前用 CDP 触发 `.click()` 只能证明 IPC 可用，不能证明桌面指针命中正常。
- 移除 React 主界面与启动页的自绘最小化/最大化/关闭按钮，`BrowserWindow` 改用 Electron 官方 `titleBarStyle: hidden` + Windows/Linux `titleBarOverlay`，由原生窗口控件负责 DPI、hover、点击、最大化状态与关闭行为。
- 保留 64px Header drag region；交互元素继续使用 `no-drag`。React 只渲染 Electron presence marker，窗口控件安全区优先读取 `titlebar-area-*` CSS environment variables，并保留 138px Windows fallback。

## Validation

- 在 125% Windows 缩放、隔离 test profile 的真实 Electron 窗口中用桌面指针命中原生按钮：maximize 将 1280×820 窗口切换为 2048×1232，restore 回到 1280×820；minimize 后可正常恢复；close 后隔离窗口进程正常退出。用户原有 Texa 窗口未关闭，隔离 profile 已删除。
- Frontend ESLint、TypeScript + Vite production build 通过；Vitest 18 files / 83 tests 通过。Electron main/preload/runtime syntax check 与 runtime tests 3/3 通过；仅保留既有 MathLive 大 chunk 提示。

# 2026-08-15 - 学习问答页面定向 UI 与 Electron chrome 修复

- 将 Question 从带左侧强调线和浅灰底的块状样式改为 Reading Canvas 上的轻量 Query Header；附件文件名从用户消息的既有 `📎 filename` 前缀中做纯展示拆分，单独显示为 attachment row，正文与 Answer 继续共用 800px Content Axis 和 15px / 1.72 阅读排版。
- 学习 Sidebar 的 `Sessions` 改为“历史记录”；active row 删除 inset accent line，改用既有 Texa blue 8% tint、正常前景与 600 标题字重，不增加 border、shadow 或额外 indicator。
- Composer 明确由 `.composer-surface` 单独负责 border、background、radius 与 focus ring；提高内部 textarea 的透明背景/无边框规则优先级，清除全局 textarea focus shadow，toolbar 保持无边框，避免不同宽度下出现分段外框。
- 将原生 `details` 更多菜单替换为受控 `ComposerOverflowMenu`；支持 trigger toggle、捕获阶段 outside pointer dismissal、Esc 关闭并归还 trigger 焦点、菜单项执行前关闭，并在 unmount 时自动移除监听。
- 新增共享 `--app-header-height: 64px`，统一 Rail logo、学习 Sidebar Header、Main Header 和 Electron controls；Main title/scope 改为同一行 baseline 布局，Logo 使用固定 20px optical wrapper。Main Header、workspace 与 Composer surrounding area 统一使用 primary workspace surface，仅用底部分隔线建立层级。
- 首次修复仍沿用了 `frame: false` 的自绘 Windows controls；该方案随后在真实桌面指针测试中确认仍会被 drag hit-test 吞掉，已由上方原生 Window Controls Overlay 修复取代。

## Validation

- Frontend ESLint 通过；Vitest 18 files / 83 tests 通过；TypeScript + Vite production build 通过，仅保留既有 MathLive 大 chunk 提示。Electron main/preload/runtime syntax check 通过；Node runtime tests 3/3 通过。
- Browser 在 720px 与 1280px 复核：Question 无 border/background/shadow，正文与 Answer 同轴；Composer 无横向溢出，textarea/toolbar 均为透明无边框；更多菜单的 outside click、Esc、menu item 三种关闭路径均通过。
- Electron 初次隔离验证确认 64px Header、双击空白区 maximize/restore、边缘 resize 与页面布局正常；但窗口按钮只通过 CDP/DOM 事件触发 IPC，没有覆盖真实桌面指针 hit-test。用户后续复现的物理点击回归及最终原生控件验证见上方修复记录。

# 2026-08-15 - 学习问答 Reading Canvas 布局重构

- 删除学习 Sidebar 中重复的当前会话标题，Top Header 作为唯一 Session Title；Sidebar 只保留学习范围、新会话与会话历史，并在 session scope 与当前范围一致时省略重复 metadata。
- 将 Question 降级为紧凑的文档上下文块，将 Answer 定义为开放式 Reading Canvas；统一 Question、Answer 与 Composer 的 content axis，正文限制稳定阅读宽度，并通过 15px / 1.72 正文、600 字重与 section spacing 重建 Markdown 层级。
- 将图片、历史错题、公式、更多与发送收进单一 Composer surface；移除主结构中的外置工具布局，低频功能改为 toolbar 内 overflow menu，并补齐窄窗下的自然收缩规则。
- 审计问答生成 Prompt：当前 `graph/generator.py` 与 `graph/chapter_subgraph.py` 已明确限制粗体只用于核心结论、概念与关键因果/对比，因此本轮不修改 Prompt、RAG、citation 协议或会话数据。

## Validation

- Frontend ESLint 通过；Vitest 18 files / 81 tests 通过；TypeScript + Vite production build 通过，仅保留既有 MathLive 大 chunk 提示。
- Browser 实机复核通过：1600px 下 Canvas / Composer 均为 920px、正文为 800px；1100px 下 Sidebar 与 695px 主轴并列；720px 下 Canvas / Composer 均为 639px，overflow 与公式面板无裁切或横向溢出；900px 下学习 Sidebar 默认收为可打开抽屉。
- 已验证唯一 Session Title、相同 scope metadata 去重、Markdown strong / heading 均为 600、正文 15px / 25.8px line-height，以及图片、历史错题、公式、overflow、发送按钮的可访问名称与布局。

# 2026-08-14 - Texa frontend product rebuild

- Rebuilt the React/Electron presentation layer around a persistent learning-harness shell: expandable session/navigation sidebar, dominant workspace, and an optional contextual inspector for sources and concepts. No backend, API, retrieval, ONNX, Chroma, database, session-event, or user-data changes were made.
- Replaced page labels and routing with a user-object IA: 学习对话 / 复习计划 / 错题 / 练习 / 教材库 / 设置. `/books` is now the actual library manager and existing import is nested at `/books/import`; the duplicate Settings library tab was removed.
- Migrated QA from answer cards/chat bubbles to a document flow; made scope context persistent, simplified the empty state and Composer, and moved low-frequency reports/random practice/highlights/quick capture under progressive disclosure. Sources and concepts now open in a contextual inspector.
- Consolidated neutral/color/spacing/radius/type/shadow/motion tokens; removed route entrance animation, shell blur, Sparkles, KPI cards in mistake statistics, nested library cards, oversized radii, and promotional onboarding copy while preserving Markdown/KaTeX/citation/status behavior.
- Added the repo-local `.agents/skills/texa-ui-system/` reusable product authority and `docs/texa-frontend-rebuild-report.md`, including audit, IA, anti-slop review, UX flow review, screenshot evidence, tests, and final verdict.

## Validation

- Frontend ESLint passed; Vitest 18 files / 78 tests passed, including new IA/inspector/anti-slop/ONNX-repair UI contracts; TypeScript + Vite production build passed.
- Electron syntax check passed; runtime Node tests 3/3 passed; the Electron development window launched as the unique `Texa` window against the live Vite frontend.
- Targeted backend presentation-critical regression passed: 35 tests covering chat stream reliability, citations, conversation events, embedding assets/typed repair, and book lifecycle.
- Repo-local Skill validator and `git diff --check` passed. Browser visual QA covered onboarding, empty workspace, active QA with Markdown/LaTeX, source inspector, library, review plan, Settings, 720×560 minimum, and 1600×900 wide layouts.

# 2026-08-14 - Product rename to Texa

- 用户可见品牌统一为 `Texa`，桌面 npm 工程名、Docker 工程名、导出包名和安装包名统一使用 `texa` / `Texa`。
- Electron 继续显式使用改名前的 `userData` 目录，避免既有教材索引、错题、配置和学习记录在升级后失联；本次不迁移数据目录、不修改 `appId`、自动更新仓库标识、IPC、环境变量、API、数据库或 Chroma 标识。
- GitHub 仓库已从 `jayceto946-byte/kaoyan-assistant` 改名为 `jayceto946-byte/texa`，并更新 description、topics、homepage、Pages 地址、Electron update provider 与 embedding runtime release URL；旧 URL 仅保留在历史验证快照中。
- Electron 仍继续使用改名前的 `userData` 目录；独立迁移与回滚方案见 `docs/user-data-migration.md`，在实现、故障注入与升级回归通过前不得移除兼容路径。
- GitHub `latest` 曾被不含 Electron `latest.yml` 的 embedding runtime Release 占用；已将现有唯一含安装包、blockmap 与更新清单的 `v0.2.0` 恢复为 Latest。该遗留清单仍描述 `0.1.0` 安装包；在签名的 Texa `v1.0.0` 正式发布前，只保证旧客户端不会读取模型资源 Release，不把遗留 feed 表述为新的 Texa 发布。
- 当前 frontend 与 desktop npm 工程均为 private，仓库没有 Python registry 发布清单，因此本次没有 npm/PyPI 名称迁移或发布操作。

## Validation

- frontend ESLint 通过；Vitest 17 files / 74 tests 通过；`tsc -b && vite build` 通过。
- backend 全量 pytest 472 passed（1 条既有 Starlette/httpx2 弃用警告）。
- Electron main/preload/runtime 语法检查通过；Node tests 3 passed，包含 Texa metadata、旧 appId 与旧 `userData` 路径保护回归。
- PyInstaller 后端构建、electron-builder NSIS/ZIP 构建与 Standard release validator 通过；生成 `Texa.exe`、`Texa-Setup-1.0.0.exe` 和 `Texa-Setup-1.0.0.zip`，`latest.yml` 指向 Texa 安装包。
- README、静态站点与 Electron 截图使用隔离演示数据重新渲染，截图归档更新为 `screenshots/texa-electron-screenshots.zip`。
- 改名后 GitHub API 核验仓库管理员权限、Pages workflow、4 个 Release 与 6 个 embedding assets；新 Pages、更新清单、embedding 资源和旧仓库重定向均返回 HTTP 200。完整下载验证结果写入 `remote_asset_verification.json`：6 个文件的 HEAD/GET、Content-Length、下载大小与 SHA-256 全部 PASS，临时下载已移除；GitHub 服务端 size/digest 交叉核验也全部匹配 manifest。命令包装器在结果落盘后因网络连接未及时退出触发 4 分钟超时，不影响已落盘的完整性结果。

# 2026-08-14 - Texa embedding ONNX Runtime Phase 3 production migration

## Production runtime 与依赖

- `config.get_embeddings()` 的 production default 已从 SentenceTransformers/PyTorch 切换为冻结的 `BAAI/bge-small-zh-v1.5` FP32 ONNX provider；保持 lowercase、512 token 右侧 padding/truncation、CLS pooling、双 L2 normalization 与 512 维输出。provider、tokenizer、interactive ORT session 均为进程级 lazy singleton；ingestion session 按需创建。
- interactive 使用 2 个 intra-op threads、batch=1；ingestion 使用 physical core count、inter-op=1、sequential、ORT_ENABLE_ALL、batch=16 与 64/128/256/512 token buckets，完成后恢复输入顺序。独立 sessions 的并发实测不需要额外 scheduler/全局锁。
- Standard 不存在 silent Torch fallback。`TEXA_EMBEDDING_BACKEND=torch` 只保留为显式 development reference；Standard 缺少该 runtime 时返回 `TORCH_RUNTIME_UNAVAILABLE`。CrossEncoder 保留 lazy optional 边界，Standard 配置模型路径时给出明确 unavailable 状态并使用 deterministic reranker。
- 依赖拆为 `requirements-release.txt`、`requirements-dev.txt`、`requirements-build.txt`。Standard 锁定 ONNX Runtime/tokenizers 并移除 torch、sentence-transformers、transformers、safetensors；开发层继续支持 parity/export/debug，构建层只增加 PyInstaller tooling。

## Asset、repair 与 Electron

- 新增 `bge-small-zh-v1.5/onnx-fp32-v1/embedding-runtime.json`，记录 model/graph/tokenizer/Texa 版本、dtype、pooling、dimension、全部文件大小/SHA-256 与 versioned repair source mapping。正常启动使用 contract+size 快检，repair/发布验证执行完整 SHA-256。
- repair 统一使用临时 staging、完整哈希、versioned install 目录、原子提升与 `active.json` 原子指针；不覆盖正在使用的文件，不自动清理升级用户的旧模型目录。固定 GitHub Release tag `embedding-runtime-onnx-fp32-v1` 已发布六个 manifest assets；逐文件 HEAD/GET、Content-Length、下载大小与 SHA-256 全部通过。
- Electron 直接从只读 `resources/embedding-runtime` 加载约 95 MB graph，不再向每个 user-data 首启复制；启动状态拆为 runtime_check、asset_verify、embedding_load、index_discovery、ready。loading UI 消费结构化 typed failures，提供 retry/repair/logs，不向普通用户展示 traceback。
- 正式 failure contract 为 `code/stage/recoverable/message/repair_action/diagnostic_id`。真实 frozen 注入覆盖 MODEL_MISSING、MODEL_CORRUPT_OR_INCOMPATIBLE、TOKENIZER_MISMATCH 与 ORT_IMPORT_FAILURE；Windows x64 architecture contract 另有单元回归。

## Build、兼容与验证

- PyInstaller 移除 Torch-oriented collection/CPU-wheel/DLL checks，加入 ONNX Runtime、tokenizers、versioned assets 与 Chroma dynamic modules；release validator 对 forbidden packages/DLL、ORT、tokenizers、Chroma、manifest/hash 和 HTTPS repair mapping fail closed。
- 现有 49 collections / 100-query 回归未 rebuild：Recall@3/5/10 为 `78% / 88% / 89%`，Top-5 set overlap `98.8%`、Top-10 `96.4%`，全部通过 release gate。`第八章 热电式传感器` 的 HNSW `Nothing found on disk` 仍按既有数据问题单独记录，未混入迁移或全库重建。
- 最终 packaged 5-run：first health median `2.403s`，full-ready `2.759s`，first textbook retrieval `428.0ms`。20 次 batch=1 median/p95 `3.734/4.297ms`，RSS p95 `169.17MiB`；500-text 五次 warm median `27.27 texts/s`；并发 ingestion + query 为 `6.65/13.29ms` median/p95、ingestion `26.86 texts/s`。
- 最终 NSIS/ZIP/win-unpacked/backend 为 `254.20 / 324.96 / 752.56 / 342.10 MiB`。相对旧 installed `1283.06 MiB` 减少 `530.50 MiB / 41.35%`。最终产物 forbidden runtime 扫描为 0，asset hash、ORT、tokenizers 与 Chroma dynamic imports 通过。
- NSIS clean install 在隔离 user-data、离线标志与不含 Python/Node 的 PATH 下启动成功，embedding/retrieval ready 且输出 512 维；静默卸载成功并保留 user-data。旧 runtime data 升级 smoke 保留 books、vector files 与旧 model assets，已有教材直接检索，无自动 re-embedding。
- 后端全量 pytest：472 passed；仅保留既有 Starlette/httpx2 弃用警告。Electron main/preload/runtime Node syntax check、frontend TypeScript/Vite production build 与 `git diff --check` 通过。
- 真实 NSIS clean install 中移走 shipped graph 后，Electron 显示 typed `MODEL_MISSING` 与“修复模型资源”；UI repair 完成六文件临时下载、full hash、原子安装、provider 自动重启与两片段检索 smoke。shipped graph 恢复后，新 profile 在 blocked outbound proxy + HF offline 下直接从 app resources 启动、入库并检索成功。Windows 拒绝创建管理员防火墙规则，因此额外离线证据属于进程级 air-gap；建议在管理员控制的 release VM 再做物理断网复核。最终发布判定为 **PHASE 3 PASS / GO**。

# 2026-08-13 - Embedding ONNX Runtime FP32 可行性实验

## 实验链路与固定数据

- 在 `evaluation/embedding_backend` 新增完全隔离的 Torch/SentenceTransformers 与 ONNX Runtime FP32 provider；正式 `config.py`、默认 backend、Chroma 索引、chunk/retrieval/reranker 行为均未修改。
- ONNX 导出图包含 BERT backbone、CLS pooling 和与当前 SentenceTransformers encode 等价的两次 L2 normalization；运行时使用相同本地 tokenizer、512 token 右侧截断/填充、CPUExecutionProvider 与 2 个 intra-op thread。
- 修复直接加载 `tokenizer.json` 时遗漏 SentenceTransformers 根据 `sentence_bert_config.json` 注入 lowercase normalizer 的差异；最终 340/340 文本的 input IDs、attention mask 与 token type IDs 完全一致。
- 固定保存 340 条 parity fixture（50 短概念、100 教材段落、60 长 chunk、50 公式/符号文本、40 组高相似概念）及 500 chunk / 100 query retrieval fixture；后者含 40 条人工核对 relevant chunk 的高价值 query。benchmark 只读 fixture，不读取或写入真实 Chroma。

## 测量结果与判定

- Embedding cosine mean/median/min 为 `1.0 / 1.0 / 0.9999998808`；逐元素 max/mean absolute error 为 `3.576e-7 / 4.055e-8`。
- Top-1/3/5/10 集合 overlap 均为 100%；40 条人工 query 的 Torch 与 ONNX Recall@1/3/5 均为 `80% / 92.5% / 95%`，MRR@10 均为 `0.8646`。样本量只足以排查明显/系统性退化，不宣称统计等价。
- 5 个全新进程测得 cold total median：Torch `8.45s`、ONNX `0.60s`；模型加载 RSS 增量约 `313.1MB / 120.4MB`，首次 embedding 峰值增量约 `366.6MB / 160.9MB`。
- Warm 输入固定为单条短 query，以及 75% 中等/公式 chunk（不超过 900 字符）+25% 50–300 字符教材段落。ONNX 单条查询明显更快；batch 8/32 基本相当；batch 100 median 为 Torch `8.43s`、ONNX `10.25s`，出现约 21.6% 回归。
- 已安装分发口径下，Torch embedding gross stack 约 `846.7MB`，ONNX gross stack 约 `187.0MB`。但当前生产 fallback、可选 CrossEncoder reranker、legacy tooling 与 release build 检查仍依赖 Torch/SentenceTransformers/Transformers，实际可删除 dependency 与旧模型资产均为 `0MB`；为保留 fallback 而同时加入 FP32 ONNX 会让 release 额外增加约 `90.5MiB`。
- 结论为 **NO-GO**：质量门槛通过，cold/RAM 显著改善，但真实可删除发行体积无明显收益且大批量摄取性能退化。保留实验 provider 与 benchmark，PyTorch 继续作为正式默认 backend。

## Validation

- ONNX graph 经 `onnx.checker.check_model` 验证；完整 benchmark 连续复跑并保留最终 JSON/Markdown 报告。
- 新增纯指标回归测试；`tests/test_embedding_backend_metrics.py`：2 passed。
- 后端全量 pytest：455 passed；仅保留既有 Starlette/httpx2 弃用警告。

# 2026-08-14 - ONNX Runtime FP32 Phase 1 throughput feasibility

## 实验边界与根因

- 在上一阶段数值/检索 parity 已通过的前提下，新增完全隔离的 Phase 1 benchmark；未修改生产 embedding backend、正式 ingestion、Chroma、BM25、KG、reranker 或 release dependencies。
- 12 物理核 / 16 逻辑核 i5-12500H 上，使用 2 线程控制条件对 Torch 与 ONNX 的 batch 1/4/8/16/24/32/48/64/96/100/128 各完成 10 次 warm runs。batch=100 回归本轮为 6.9%，未稳定复现上一阶段 18–22% 的幅度；最大回归出现在 batch 16–48，为 22.6–26.6%。
- 短文本下 ONNX 与 Torch 持平或更快；正常段落的 padding ratio 随 batch 增大并放大回归；全 512-token 长文本在 padding ratio=1.0 时仍有 15–19.5% 回归，说明原因同时包含 padding strategy 与两线程下 ORT 长序列 compute/memory scheduling。
- batch=100 runtime 中约 99.8% 位于 `ORT session.run`；tokenization、NumPy input construction 和 result conversion 不是主要卡点。输入 batch/sequence axis 均为动态，未发现固定 shape。

## 实验优化与验收

- 单纯保持顺序的 micro-batching 最多只提升 4.8%；length-sorted batch=32 通过把 padding ratio 从 1.415 降至 1.040，在两线程下将真实 500-chunk 吞吐从 9.47 提升至 13.58 texts/s。固定长度桶也提升到 11.70 texts/s，输出写回原索引后的逐行 cosine minimum 为 1.0。
- ORT intra-op 是主要吞吐杠杆；12 线程在 batch=100 达到 20.50 texts/s。inter-op 1/2/4 与 parallel execution 无有效收益。`ORT_ENABLE_EXTENDED/ALL` 相比 DISABLE/BASIC 在 batch 32/100 快约 7–8%。
- 双 L2 normalization 的 single-normalization 实验图从 380 降为 374 nodes，但没有实质性能收益；340-text cosine mean 1.0，Top-1/3/5/10 overlap 100%。为保持 SentenceTransformers 兼容语义，baseline-compatible graph 不变。
- 真实 `传感器长书` 500 chunks：Torch current batch=32 为 10.63 texts/s、峰值 1022.6 MB；实验 ONNX length-bucket batch=16 + intra=12 为 27.47 texts/s、峰值 1011.1 MB，吞吐 2.58× 且 RAM -1.1%；global length-sort batch=16 为 32.49 texts/s、峰值 1057.6 MB。50-text ONNX/Torch cosine mean 1.0、minimum 0.99999988。
- Phase 1 判定为 PASS。建议仅作为后续候选：interactive 保持 batch=1 + 小线程池；offline ingestion 使用 0–64/65–128/129–256/257–512 bucket、batch=16、物理核心数 intra-op。生产默认 backend 未切换。

## Validation

- Phase 1 原始 checkpoint、完整报告、baseline-compatible graph 与 single-normalization 实验 graph 保存在 `benchmark_results/embedding_onnx_phase1`。
- 实验 provider/worker、export variant 和报告脚本均通过 Python AST；length plan/padding 专项回归通过。`git diff --check` 无空白错误。

# 2026-08-12 - 错题与问答多模态桥接层

## 可观察问答执行过程

- 问答助手消息新增可折叠的统一执行过程卡。执行中自动展开，完成、停止或失败后自动收拢；步骤显示真实状态、摘要和耗时，不展示模型隐藏 thinking。
- 普通聊天把既有 `context → plan → retrieve → chapter → generate → done` SSE 映射为“读取会话上下文、理解问题与确定范围、检索教材上下文、整理教材证据、综合证据与知识推理、生成答案、关联学习记录”等用户可理解的活动；阶段交接时会先声明下一项正在执行，而不是只显示事后记录。
- 图片问答新增 SSE 路径，真实报告“读取附件、Kimi 识别图片、综合题干与视觉关系、生成答案、关联学习记录”；DeepSeek 正文逐段流式显示，不再在长时间推理后整段跳出；视觉类型、实体/关系数量与不确定项作为可展开摘要展示。
- 历史错题讲解新增 SSE 路径，明确显示复用 Visual IR 缓存或旧题干降级，不再让长时间模型调用表现为无反馈阻塞。
- 活动事件采用稳定 `id` 原位更新，前端不会因 `active → completed` 重复增加步骤；失败步骤保留原因，教材不适用或概念未可靠匹配会显示为“已跳过”，不会假装成功。
- 普通回答、图片讲解和历史错题讲解统一支持停止；停止或异常会结算仍在运行的步骤，执行卡不会残留永久转圈。

## Kimi Vision → DeepSeek

- 新增独立 `multimodal_bridge` 服务。Kimi 不再只转写 OCR，而是输出有界的 `VisualProblemIR v1`：题干、图形类型、实体、连接/空间/拓扑关系、图内标注、公式、选项、手写步骤、圈画和视觉不确定项；DeepSeek 以该结构化视觉证据完成最终推理。
- 视觉证据在提示词中明确作为不可信只读数据处理，图片内指令不得执行；无法确定且会影响答案的信息要求显式提示用户校正，避免模型凭空补图。
- 错题记录新增向后兼容的 `visual_ir` JSON 字段，无需迁移 SQLite schema；旧记录继续从 `question_text/ocr_text` 降级讲解。

## 错题本与问答附件

- 错题页的识别、看图讲题和文本重讲统一复用多模态桥接层，保存时同时缓存题干转写与 Visual IR。
- 问答输入区新增图片附件和历史错题选择入口。新图片可直接讲解并显式选择是否导入错题本；历史错题优先复用缓存 Visual IR，不重复调用视觉模型。
- 问答图片入口改为输入框左侧始终可见的“图片”文字按钮，紧凑 Electron 布局不再退化为难以辨认的纯图标；选图后先进入与错题页共用的 `ProblemImageEditor`，支持框选、亮度、对比度、锐化和黑白扫描效果。
- 错题页原有裁剪与滤镜交互已收敛到同一共享组件，避免聊天端与错题端行为逐渐分叉。
- 图片问答完成后复用现有 KG 概念链接与 ConceptMemory 接触记录；导入错题后保留图片、Visual IR、讲解和概念标签。

## Validation

- 多模态 IR 解析、旧 OCR 降级、视觉证据提示边界和图片答案流式事件均有回归覆盖。
- 后端全量 pytest：448 passed；前端 Vitest：16 files / 72 tests passed；ESLint、TypeScript 和 Vite production build 通过。
- 使用本地 production build 实际检查问答页 DOM：存在可见且有无障碍名称的“上传题目图片”按钮，按钮正文为“图片”。

## 图片讲解请求中止修复

- 修复问答图片链路使用 150 秒总超时，却串行执行最长 120 秒 Kimi Vision 与最长 120 秒 DeepSeek 导致前端先行中止的问题。图片讲解统一使用 6 分钟总时限，单独 OCR 使用 3 分钟，并覆盖问答页、错题页和错题速录三个入口。
- `fetchWithTimeout` 现在区分超时、调用方取消和异常中止，不再把浏览器底层 `signal is aborted without reason` 原样展示给用户；超时会显示具体秒数和可执行的重试提示。
- 图片主答案返回前的概念关联改为只读本地 KG 快速路径，不再额外串行调用一次 LLM；Kimi Vision 禁用 SDK 自动重试，DeepSeek 图片解题使用 180 秒明确上限且禁用自动重试，避免请求时长不可预测。

## 图片讲解性能、发送状态与公式修复

- 依据执行卡实测将约 297 秒拆为 Kimi 视觉解析 69 秒和 DeepSeek 首段前隐藏推理 228 秒；附件保存与概念关联不是主要卡点。Kimi 视觉解析关闭默认 thinking、限制 Visual IR 输出规模；DeepSeek 图片讲题与主问答统一维持 `V4 Pro + high + thinking`，本轮不同模型/强度测试只作为评测记录，不接入生产路由。
- 同一张本地错题图的真实 API 中间基准（图片答案为 medium thinking）曾测得 Kimi 38.2 秒、DeepSeek 首段 104.1 秒、完整链路 155.3 秒；该档位仅用于性能观察，不作为当前生产配置。
- 图片附件、历史错题选择、问题文本和公式输入在点击发送后立即清空，不再等待远端 `done`；删除附件预览中的“Kimi 提取题干与图形关系，DeepSeek 负责推理讲解”小字。
- 图片讲题提示词强制所有 LaTeX 使用数学定界符；后端与前端兼容修复裸 `\\circ/\\text/\\approx`、跨 Markdown 段落错误配对的单个 `$`，因此新答案和已经保存的旧答案都可正常渲染。
- 使用同一张 E 型热电偶试题和固定 Kimi Visual IR 对 DeepSeek V4 Pro 进行真实付费单样本基准：Kimi 生产预处理后视觉抽取 42.50 秒；`medium + thinking` 首段 200.22 秒、完整 211.38 秒；`high + thinking` 首段 184.50 秒、完整 198.82 秒。两者四问结论一致，high 输出更完整但本次反而更快，说明单样本在线延迟不能用于建立 `effort → 时延` 的单调假设。
- 复用完全相同的 Visual IR 与 prompt 两次测试 `deepseek-v4-flash / high + thinking`：第 1 次首段 396.85 秒、完整 403.77 秒，第 2 次首段 361.54 秒、完整 368.92 秒。两次四问结论同样正确，第二次仅快 8.6%，平均完整耗时 386.35 秒，仍为 Pro medium 的 1.83 倍、Pro high 的 1.94 倍。首次慢响应不是一次重试后消失的孤立波动，但少量顺序样本仍不能区分模型自身耗时与端点持续负载，也不能视为长期性能排序。
- 基准产物保存在 `data/eval/image_reasoning_20260813_201703`，包含生产优化图、Visual IR、四份完整答案、JSON 指标和汇总报告；thinking 内容未保存。初始未复用生产图片预处理的目录已用 `EXCLUDED.md` 明确排除。

# 2026-08-12 - Session Resolver 学习行为收口与 Learning State v1

## Session Resolver 与跨 Session 桥接

- Resolver v2 新增确定性的 `resume_learning`、`start_learning`、`pause_learning`、`set_learning_goal`、`review_request`、`self_report_weakness` speech act。学习命令不推进当前 Session topic；普通新会话问题仍只读取当前 Session Ledger，不继承其他会话的 topic、artifact 或旧指令。
- 新增受控 `learning_state_bridge.py`：只有显式学习行为才读取长期 Learning State；唯一目标可恢复，多个目标要求用户指定教材，没有目标则要求先选择教材/章节。存储失败保留错误遥测并降级，不阻断普通 QA。
- SSE/非流式聊天在恢复目标后返回实际 `book_name/subject/conversation_id`；Electron 优先的 React 聊天上下文同步恢复后的 scope，避免下一轮因前端仍持有旧教材作用域而重新切断会话。

## Learning State v1 数据合同

- 将既有 `progress/learning_events.db` 从 schema v1 原位升级到 v2，新增 `learner_id`、稳定 `book_id`、`chapter_id` 与 `unit_id`；旧事件保留并默认归属本地单用户 `local_default`。迁移使用 `PRAGMA user_version`，不删除或重写旧错题、概念、复习和会话数据。
- 新增纯 `learning_state_reducer.py` 和应用服务 `learning_state.py`。append-only event 是权威事实源，`progress/learning_states/<learner>/<book>.json` 是可删除、可重建投影；状态包括 active goal、当前 chapter/unit、concept evidence、next action 和源事件 ID。
- 掌握证据保持保守：普通问答/讲解只增加 `exposure`，不会自动提高 mastery；显式不会、错题或低质量评分进入 weak/practicing；至少两次有评分的练习证据后才可能进入 stable。LLM/Router 不能任意写 mastery，只能提交白名单学习 operation，由服务校验后追加事件。
- 新增 `/api/learning-state` 与 `/api/learning-state/operations`，并把现有练习、错题和概念复习事件补充稳定教材/章节身份。LearningContextPack 与 ConversationContextPack、EvidencePack 分离，教材事实仍只来自本轮 EvidencePack。
- storage manifest 中 `learning_events` 升级为 v2，并登记 rebuildable Learning State v1。数据库结构变化与验证方式记录于本条；现有特征存储继续兼容，尚未删除旧 `ConceptMemory`、`StudyMemory` 或 SM-2 数据。

## 验证

- Learning State v1/API/旧库迁移专项：10 passed。
- Resolver、Context 安全、Learning Memory 与迁移组合回归：50 passed；另一次核心组合回归 41 passed。
- 后端全量：442 passed；仅保留既有 Starlette/httpx2 弃用警告。
- 前端 ESLint 通过；TypeScript + Vite production build 通过，仅保留既有 MathLive 大 chunk 提示。
- `git diff --check` 通过；本次未调用外部模型，也未运行付费评测。

# 2026-08-12 - Resolver 模块化、受控语义回退与证据连续性 v2

## Resolver 边界与语义回退

- 将 `session_context.py` 中的引用解析观测、speech act 分类和 state operation 派生拆为独立纯模块；检索动作继续由 `graph/retrieval_policy.py` 独立负责。兼容入口和确定性规则保持不变；接入受控语义编排后主文件为 916 行，低于原先 1000+ 行，且三项职责已有独立测试边界。
- 新增默认关闭的 `semantic_resolver.py`。只有显式启用且确定性方法为低强度的 `unresolved_reference` / `incomplete_ordinal_resolution` 时才可尝试；模型只能从 Ledger 有界候选中选择一个 `resolve_reference`，或返回 `clarify`。任意新对象、自由 query、多个 operation、`set_topic` 等直接状态写入均被校验拒绝，错误自动保持澄清路径；输出先过滤 thinking。此次未启用、未调用外部模型。
- RAG Trace 保存 semantic attempted/error 的有界遥测，不保存 semantic prompt、模型原文或 thinking。`confidence_kind` 继续明确为 `rule_strength`，未改称概率或准确率。

## 反馈统计与 active evidence

- 回答反馈通过既有 `request_id` 与 RAG Trace 关联，新增按 resolver method 的运行结果与用户反馈代理统计，不迁移反馈数据库。每个 method 少于 30 条反馈时 `routing_decision_ready=false`；统计明确标记为 feedback proxy/runtime outcome，而非校准准确率。
- 当前最近 500 条 trace 中可识别 `identity_no_history` 234 条、`unresolved_reference` 28 条（均进入澄清），另有旧 trace/无 method 238 条；当前没有绑定反馈样本，因此不具备启用语义路由的依据，保持默认关闭。
- EvidencePack source 新增 chunk 内容 SHA-256 截断指纹；assistant 消息和 Session Ledger 的 active evidence 新增教材 ID、教材/索引版本、有效 scope 与失效原因。教材/学科 scope、topic 或 corpus version 变化会记录原因并强制 full retrieval；复用时重新读取 chunk 并校验内容指纹，失配则禁止复用并降级为 full retrieval。
- 以上均属于兼容的派生元数据扩展；未修改教材索引格式、数据库 schema、错题或学习记录。Retrieval policy version 升级为 `evidence-continuity-v2`，用于反馈与回归版本绑定。

## 验证

- Resolver/语义协议/证据连续性/聊天可靠性专项：56 passed；追加模块与指纹专项均通过。
- 后端全量：431 passed；仅保留既有 Starlette/httpx2 弃用警告。
- Context Eval v2 strict：Resolver 100/100、Retrieval 12/12、离线 Answer snapshot 12/12，全部门槛通过。
- Context Eval v3 离线生产检索：12/12，release gate 通过；本次未再次调用付费 Answer Eval。
- `git diff --check` 通过。

# 2026-08-11 - Context Eval v3、回答反馈闭环与 Context 安全回归

## 真实回放与生产检索评测

- 新增 `evaluation/context_replay.py`：从本地 append-only 会话筛选用户纠正、话题返回、复杂约束、assistant artifact、多步追问和长会话候选；输出前过滤 thinking，并脱敏 token、邮箱、手机号、身份证号、URL 与本地路径。候选默认写入 `data/eval`，保持 `status=candidate`，只有人工补全期望并标记 `approved` 后才能进入发布评测。
- 本机现有历史共筛出 7 条困难候选，数量不足计划中的 30-50 条，因此没有把它们冒充真实金标或提交到版本库。负向回答反馈会自动进入同一候选生成链路。
- 新增 `evaluation/context_eval_v3.py` 与 12 条 `传感器长书` production-corpus/context 合同。Retrieval 层实际运行 Resolver、生产 KG/Chroma/BM25 检索和最终 EvidencePack，不再使用 fixture candidates；首轮真实结果为 9/12，暴露普通数字列表“第四点”解析失败、测量条件纠正丢失原对象，以及一处金标措辞未使用教材原文。修复后二次实跑为 12/12。
- 真实 Answer Eval 复用生产 `_build_generate_prompt` / `generate_node`，默认完全关闭；必须同时传入 `--online --confirm-paid-model` 才会调用现有 DeepSeek 配置。获得明确授权后已执行 12 条付费 DeepSeek 案例，但首轮 CLI 在全部检索与调用完成后，因 Windows GBK 不能编码回答中的上标字符而在 `print(payload)` 处失败；旧实现又把报告写盘放在打印之后，因此本轮答案与通过率不可恢复，不能表述为 Answer 层已通过，也没有未经授权重复调用。
- 修复 CLI 报告耐久性：先以 UTF-8 写入评测报告，再尝试控制台输出；控制台编码失败时降级为 ASCII-safe JSON。新增回归测试模拟 GBK 编码异常，保证终端输出故障不再导致付费评测结果丢失。
- 获得第二轮明确授权后重跑同一批 12 条，报告成功落盘。生产检索为 12/12；原始精确字符串 Answer 合同为 9/12。人工核查确认 3 个失败均为评分误判：“极小/很小”同义表述、“高、低温/高低温”标点差异，以及禁止词错误命中“不适合高频动态测量”的否定语境，并非答案事实或引用失败。
- Answer scorer 新增同义候选、中文顿号归一化和否定语境感知，针对上述三类误判加入确定性回归。对同一批已保存答案离线重评分为 12/12，在线 Answer 发布门槛通过；重评分未再次调用模型，原始 9/12 报告和修正后 12/12 报告均保留，避免覆盖原始观测。

## 主聊天反馈与版本绑定

- 新增本地 `progress/answer_feedback.db`，支持 helpful/unhelpful 覆盖更新和五类负向原因：答错对象、忘记前文条件、错用旧证据、教材依据不足、答非所问或重复。反馈绑定 `conversation_id/message_id/turn_id/request_id`，并保存 model、prompt、Context policy、retrieval policy 和 corpus version；消息投影保存轻量反馈快照，历史重载后仍可显示。
- SSE/non-streaming 回答均返回持久化 `message_id`，会话消息和 RAG Trace 同步保存版本标识。前端回答卡新增轻量赞/踩与原因选择，不在 React state updater 中执行副作用。
- 新增 corpus version 保护：新消息保存教材索引版本；若紧邻回答版本与当前教材版本不同，Evidence Continuity 不再复用旧 chunk，强制走 full retrieval。旧索引没有 manifest 时使用本地 lexical index 的 size/mtime 版本标识，旧历史没有版本字段时保持兼容。
- `answer_feedback` 加入 storage manifest v1，位于既有 `progress` 备份范围；未修改教材、错题、学习记录或现有向量数据格式。

## Resolver 与安全修复

- Assistant Artifact Index 支持“第四点”等普通中文列表引用；测量条件形式的“我问的是高频动态测量，不是低频”会保留上一轮实体与问题结构，不再退化为缺少对象的泛化解释。
- 新增历史 prompt injection 边界、教材版本失效、Ledger 损坏重建、并发 Ledger 写入、Agent 风格回答进入普通历史后的连续追问、在线模型失败隔离等回归。

## 验证

- 原 Context Eval v2：Resolver 100/100、fixture Retrieval 12/12、离线 Answer snapshot 12/12，strict gate 通过。
- Context Eval v3 第二轮：生产检索 12/12；DeepSeek Answer 原始精确匹配 9/12，修复评分器后对相同已保存答案重评分 12/12，online release gate 通过。评分与报告器专项测试 6/6 通过。
- 后端全量：419 passed；仅保留既有 Starlette/httpx2 弃用警告。
- 前端：15 files / 70 tests passed；ESLint、TypeScript 与 Vite production build 通过，仅保留既有 MathLive 大 chunk 提示。
- `git diff --check` 通过。

# 2026-08-10 - venv310 环境重建与依赖锁定修复

## 原因

- venv310 长期混装 PaddleOCR / Marker / Surya / MinerU 等可选 OCR 运行库，未纳入锁定文件，`pip check` 报告 protobuf、numpy、pillow、openai 等版本冲突，环境不可复现。
- 核实生产 OCR 路径：错题图片 OCR 走 Kimi Vision（`backend/api/mistakes.py`），教材解析走外部 MinerU（`ingestion/mineru_client.py`，纯 httpx API）；`ingestion/ocr.py` 的 PaddleOCR/PPStructure 只被遗留 CLI（`ui/cli.py`）与独立 agent（`agents/coordinator.py`）引用，生产路径不依赖本地 OCR 运行库。

## 动作

- 旧环境改名保留：`venv310` → `venv310-mixed-backup`（6.1G，未删除），包清单备份至 `logs/venv310_pip_freeze_backup.txt`（305 项，被 gitignore 忽略）。
- 用 Python 3.10.11 全新创建 `venv310`，按 `requirements-dev.txt` 精确安装（torch 2.11.0+cpu、openai 2.46.0、chromadb 1.5.9 等），体积约 848M。
- 修复锁定文件：`requirements-release.txt` 中 `openai==1.109.1` 与 `langchain-openai==1.2.2`（要求 `openai>=2.26,<3`）冲突，说明该锁定集此前从未从零安装验证；改为 `openai==2.46.0`（与已验证通过全量测试的本地环境版本一致）。

## 影响

- 主 venv310 回归纯净锁定集，`pip check` 通过、可复现；Electron/CI 的 fresh-env 安装现在可解析成功。
- `ingestion/ocr.py` 缺 PaddleOCR 时按原有 try/except 降级返回“[PaddleOCR 不可用]”提示，不阻塞导入；CLI / `agents/coordinator.py` 的本地 OCR 功能不可用（生产路径不受影响）。
- 未修改数据库、向量索引、教材、错题或学习记录。

## 验证

- `pip check`：No broken requirements found。
- 后端全量 pytest：403 passed（88.8s），仅既有 Starlette/httpx2 弃用警告。
- uvicorn 启动冒烟：`/api/system/health` 200、`/api/system/version` 200，embedding 本地快照加载，2.3s。
- git：`requirements-release.txt` 的 openai pin 修复与本次环境重建记录已随独立 commit 提交；旧环境 `venv310-mixed-backup` 已于确认后删除，磁盘释放约 6G。

# 2026-08-09 - Read-only Agent 超时与可观测性修复

- Read-only Agent 新增 50 秒总预算、8 秒单工具预算和 35 秒模型总结预算；Agent 专用 LLM 请求禁用自动重试，并以相同的请求超时约束底层客户端。超时工具只标记为局部不可用，模型总结超时则保留已读取证据并返回明确提示，不再无限占用前端请求。
- 每个工具输出新增执行状态、耗时和超时预算；响应新增总耗时、逐工具 trace 与模型总结 trace。后端只记录 conversation id、工具名、成功数、总结状态和总耗时，不记录问题或证据正文；前端 Agent 卡片显示总耗时、逐工具耗时和总结超时/失败标记。
- 前端 Agent 请求上限调整为 55 秒，普通回答降级设置 60 秒上限；发生 Agent 网络/协议失败时，阶段文案明确切换为“正在降级到普通回答”，不再保留误导性的工具读取状态。普通非流式回答也获得 130 秒有界超时。
- “我今天复习什么”等复习任务精简为 `build_review_plan` 与 `get_weak_concepts`，不再重复调用到期错题、错题统计，也不再附加无关的教材与概念搜索。加入错题提案不会再因包含“错题”而同时触发复习计划。
- 未修改数据库、向量索引、教材、错题或学习记录格式。验证：后端全量 390 passed；前端 Vitest 15 files / 70 tests passed；ESLint、TypeScript、Vite production build 与 `git diff --check` 通过。构建仅保留既有 MathLive 大 chunk 提示。

# 2026-08-09 - 主聊天接入 Read-only Agent

- 主聊天发送链路新增保守的学习任务路由：明确的复习计划、学习进度、组题练习和教材例题查找进入 Read-only Agent；概念解释、讲题、证明推导、普通追问和依赖历史对象的“把这道题加入错题本”继续走既有 SSE/RAG，避免误路由和错误写入提案。
- Agent 请求复用 ChatContext 的全局 loading/abort 生命周期，支持停止；请求失败或没有选择到工具时自动降级到 `/api/chat/ask` 普通回答。Agent 成功回答通过 `/api/chat/log` 写入 append-only 会话历史，保存完成后才重新开放下一轮输入，避免紧邻追问读不到刚完成的 Agent turn。
- `runReadOnlyAgent` 接入 AbortSignal；通用 fetch timeout 现在会合并外部取消与内部超时，避免传入 signal 后丢失超时保护。
- Agent 卡片补齐教材例题、薄弱概念、习题筛选、最近进度和练习提案标签；展示成功工具、局部失败数量和待确认操作，并明确标记提案“尚未执行”，不提供虚假的确认按钮。
- 新增确定性前端路由回归，覆盖 5 类正例、6 类普通 RAG 负例、无教材 scope 和四类阶段文案。验证：前端 15 files / 69 tests passed，ESLint、TypeScript 与 Vite production build 通过；后端 Agent 工具专项 9 passed，`git diff --check` 通过。构建仍只有既有 mathlive 大 chunk 提示。

# 2026-08-09 - 首批学习 Agent 工具补全

- 补齐并注册首批工具中的四个缺口：`find_textbook_examples`、`get_weak_concepts`、`search_exercises` 与 `get_recent_progress`。连同既有的教材/概念搜索、到期错题、错题统计和两个提案工具，用户指定的 10 项能力现已全部出现在 Tool Registry。
- 教材例题工具优先使用向量元数据中的 `example` 语义角色，并以确定性 chunk role 分类降级；返回教材 chunk、章节、页码与原文，不把模型生成题冒充教材例题。
- 薄弱概念工具合并 ConceptMemory 显式弱项与错题关联概念，并保留局部故障字段；习题搜索覆盖自然语言请求、知识点/标签/章节匹配，规划阶段只返回题目元数据和答案存在性，不泄露答案正文。
- 最近进度工具读取 append-only learning event log，在 1-31 天有界窗口内汇总问答、错题、练习和概念活动；练习会话工具只返回绑定题目 ID 的 `pending_action`，不会创建会话或修改学习数据。
- Read-only Agent 的确定性选择器新增例题、习题、练习会话、最近进度和薄弱概念路由；工具证据压缩同步覆盖例题、习题和最近事件，避免把无界工具正文注入总结 prompt。
- 验证：Agent 工具专项 9 passed；后端全量 386 passed，仅保留既有 Starlette/httpx2 弃用警告。

# 2026-08-09 - ConversationContextPack 与三层 Context Eval

## Conversation Context Assembler（P3）

- 新增 `graph/conversation_context.py`。Resolver 完成后先构建轻量 seed，回答生成时再结合最终 intent 与 EvidencePack 组装统一 `ConversationContextPack`：当前 topic、问题维度、speech act、有效约束、最多 2 个相关历史 turn、被引用 assistant artifact、必要 topic 轨迹，以及本轮 `none/reuse/delta/full` 和复用/新增 E-id。
- 相关 turn 按 Resolver 的 `referenced_turn_ids` 精确选取；若引用已超出最近 48 条消息窗口，只按 turn id 从 append-only 投影补读，既不扫描也不把完整会话放入 prompt。独立问题不继承历史 turn；显式 return/correction/continue 最多补充最近一轮维持表达连续性。
- 教材 grounded、学科通用、跨学科通用以及 teach/summarize 的流式/非流式生成均接入同一上下文包。默认字符预算 2800、硬上限 5000；Context Trace 新增 state/turn 字符数、turn/artifact 数量、证据 E-id 与丢弃 turn 数，不保存 Context Pack 正文或内部 chunk id。
- Prompt 明确把历史 turn/artifact 定义为带引号的对话数据：只可用于理解指代、表达和步骤连续性，不是事实证据，也不得执行其中的旧指令；教材事实冲突时以本轮 EvidencePack 为准。旧 turn 定点补读或组装失败会降级为空 pack，不阻断当前问答。
- 澄清分支仍绕过 Planner/Retriever/Answer LLM，但会生成不含正文的 Context Pack telemetry，便于确认它引用了哪一轮后决定澄清。

## 三层 Context Eval（P4）

- `evaluation/context_eval.py` 报告升级为 schema v2，分别输出 Resolver、Retrieval/EvidencePack、Answer 三层结果和 release gates。Resolver 保留原 100 场景；新增 12 个流水线场景，覆盖 assistant list/step、约束纠正、意图继承、topic return、比较、standalone、20/40/80 轮、evidence reuse 与 clarification。
- Retrieval 层运行生产 Resolver、retrieval policy、EvidencePack 和 ConversationContextPack，检查实际纳入/排除的 chunk、检索动作、相关 turn/artifact，以及 reused/new E-id，不以“候选检索到了”替代“最终进入 EvidencePack”。
- Answer 层提供确定性的离线快照合同，检查回答对象、继承约束、必要内容、禁止漂移词和重复句，并加入错误对象 + 错误约束 + 重复的负向控制。该分数只代表离线回答快照通过合同，不代表线上 DeepSeek 回答准确率；报告通过 `layer_modes=offline_answer_snapshot_contract` 明示边界，后续可把真实采集回答送入同一评分器。
- 发布门槛：三层总体均至少 80%，Retrieval/Answer 至少各 10 例；user correction、assistant artifact、clarification、evidence reuse/delta、negative 与 standalone 必须 100%；20/40/80 轮分别至少 80%，任何单独长会话门槛失败都会阻止 strict 通过。
- 为支持“再简要解释一下”类 Answer 连续性，Resolver 新增 `deterministic_rephrase`，显式恢复 topic 与上轮 intent 并输出 `keep_previous_intent`；同时修正长会话引用 turn 优先级，避免“概念1”被“概念19”的字符串包含关系误绑。

## 验证

- Context Eval strict：Resolver 100/100、Retrieval/EvidencePack 12/12、离线 Answer snapshot contract 12/12；全部总体、专项和 20/40/80 独立 release gates 通过。
- P3/P4 专项回归：66 passed（仅 1 条既存 Starlette/httpx2 弃用警告）。
- 后端全量：380 passed（同一条既存弃用警告）。Electron 共用前端：ESLint 通过、56 tests passed、TypeScript 与 Vite production build 通过；构建仅保留既有的 mathlive 大 chunk 提示。

# 2026-08-09 - Append-only 会话历史、Session Ledger 与 Resolver v2

## 会话历史与分页

- 会话消息改为 SQLite append-only event log：`conversations/_conversation_events.db` 保存不可变事件，`conversation_messages` 作为可分页读取的当前投影。原有单会话 JSON 保留为最近 40 条消息的轻量兼容投影，不再承担完整历史存储；列表中的 `message_count` 来自完整投影。
- 旧 JSON 会话在首次读取/追加时惰性导入一次，迁移使用 `conversation_imports` 防重复。迁移不会修改教材索引、ChromaDB、错题或学习记录；若旧 JSON 在本次升级前已经裁掉了更早消息，那部分历史没有数据来源，无法事后恢复。
- 会话详情和独立消息接口支持 `limit/before_seq` 游标分页。前端首次只加载最近 40 条，顶部可继续加载更早消息并保持滚动位置，不再把完整会话一次送入 React state。
- 更新概念标签、证据支持状态、会话重分类和 turn 拆分时，同时更新消息投影并追加对应事件；重分类/拆分会使派生 Ledger 失效并在下次请求重建，原始事件不删除。

## Session Ledger

- 新增 `backend/services/session_ledger.py`，为每个会话保存有界的结构化状态：topic stack、最近 100 个实体及 first/last mentioned turn、entity groups、assistant artifacts、constraints、comparison frame、intent 和 active evidence。
- Resolver 请求只读取最近 48 条消息与 Ledger；Ledger 缺失或落后于最新消息时，才从完整事件投影重建。完整历史用于重建状态，不直接塞入 Planner/Answer prompt。
- Ledger 使用原子 JSON 写入和按会话分片的重入锁，避免同一会话并发读改写造成文件损坏或静默丢更新。80 轮专项回归确认：近期窗口已经不含第一轮时，“回到第一个”仍能解析到首轮实体。

## Resolver v2

- Resolver trace 在 `resolved_query` 之外正式输出 `speech_act` 与 `state_operations`。当前稳定操作包括 `set_topic`、`return_to_topic`、`select_artifact`、`replace_constraint`、`correct_entity`、`keep_previous_intent`、`add_constraint` 和 `clarify`。
- 已覆盖条件替换、实体纠正并继承上轮意图、显式返回旧话题、长序数引用、多实体/assistant artifact 引用和独立问题防错误继承。澄清请求不再推进 `state_after`，避免无法解析的指代污染当前主题。
- Context Trace v2 对 `speech_act/state_operations` 做有界持久化；Context Eval 同时校验这两个字段，不再只检查字符串改写是否碰巧正确。

## 验证

- Context Eval strict：100/100；resolution、follow-up、references、clarification、speech act、state operations、state、retrieval action/query、scope change 和 standalone preservation 均为 100%。其中包含真实展开的 20/40/80 轮场景。
- 后端全量：371 passed（仅 1 条既存 Starlette/httpx2 弃用警告）。前端：ESLint 通过、56 tests passed、TypeScript 与 Vite production build 通过。
- 新增专项测试覆盖 261 条消息的完整读取与两页无重叠分页、旧 JSON 单次导入、append-only event 数量、80 轮 Ledger 回指、Resolver v2 条件替换和澄清状态不变。

# 2026-08-09 - Assistant Artifact Index、主动澄清与 Evidence Continuity

## Assistant Artifact Index

- 新增有界、确定性的 assistant 输出索引。Resolver 会从最近回答中提取可被后续指向的列表项、步骤、例题/反例、公式、Markdown 标题、表格数据行、结论和命名方法；普通正文不进入索引，单条回答最多保留 32 个 artifact，会话状态最多保留 48 个。
- 支持“第一个/第二道题/第二步/第一部分/第二行/前者/后者/这个式子/这个结论/它的条件”等引用，并在 Context Trace 中记录 `deterministic_assistant_artifact`、引用对象和 assistant turn id。
- Artifact Index 从现有会话正文即时重建，不新增数据库、不改历史会话格式，也不把整段 assistant 回答写入 RAG Trace。

## 主动澄清

- Resolver 对缺少候选集合的序数、前者/后者及无锚点代词返回 `resolution_action=clarify`，保留用户原问题并生成简短澄清请求；不再把低置信度猜测送入教材检索。
- SSE 与 `/api/chat/ask` 均有独立 clarification 路径：保存 user/assistant 消息，但完全绕过 Planner、Retriever 和回答 LLM；Context Trace 记录 `retrieval_action=none` 与 `clarification_no_generation`。

## Evidence Continuity

- 会话从上一条 assistant 消息读取 sources 与最终 `evidence_support_status` 快照，结合 topic、intent、教材/学科 scope 和是否请求新维度，选择 `none/reuse/delta/full`。
- `reuse` 通过 chunk id 从本地教材词法索引恢复原始证据正文并跳过向量库/KG 初始化；无法恢复正文时如实降级为 `full`。`delta` 保留已恢复的旧证据，并运行检索补充新维度，最终分别记录真正进入 EvidencePack 的 reused/new/dropped ids。
- 只允许紧邻的上一条 assistant 回答提供 active evidence；中间出现无来源回答、topic 改变、教材/学科切换或旧证据不可恢复时，不复活更早的 stale evidence。上一轮 support 为 `partial` 时，即使同一维度也强制走 `delta`。
- 会话 JSON 新增可选的 `evidence_support_status` 消息字段，旧会话无需迁移；教材索引、ChromaDB、错题和学习记录均未修改。

## 评测与验证

- 100 场景 Context Eval 从初始 41/100 提升到 64/100：assistant artifact 16/16、clarification 3/3、evidence reuse 2/2、evidence delta 2/2、retrieval policy 10/10；core 7/7 与 negative 9/9 保持不变。剩余 36 个失败主要属于长程早期实体、用户纠正、条件替换和更复杂意图链。
- 新增生产路径测试覆盖 artifact 解析、澄清绕过 Graph、SSE/非流式协议、reuse 不初始化向量检索、delta 合并旧/新证据、partial support 强制补检和 support 快照持久化。
- 针对性回归 58 passed；后端全量 366 passed，仅有既存 Starlette/httpx2 弃用警告；`git diff --check` 通过。

# 2026-08-09 - Context Trace v2 与多轮 Context Eval 基线

## Context Trace v2

- 会话 Resolver 在保持原改写结果不变的前提下，新增有界的解析观测：`raw_query / resolved_query`、规则来源、规则强度、引用实体与 turn、以及 `state_before / state_after`。规则强度明确标记为 `rule_strength`，不冒充统计校准后的概率。
- Chat 的 SSE 与非流式路径统一写入 Context Trace；检索侧记录 `none/reuse/delta/full` 动作、实际 retrieval query、复用/新增/丢弃的 chunk id、支持状态与降级错误。该初始基线尚未实现 evidence reuse，因此当时教材问答如实记录 `full` 和空的 reused 集合。
- Generation 记录最终组装上下文的字符预算，包括实际 prompt、query、教材证据、学习历史、教学内容、scaffold、EvidencePack 候选/纳入/丢弃数量和 Planner prompt 字符数。Trace 只存大小与标识，不保存 prompt 正文、回答或 thinking。
- RAG trace SQLite schema 升级到 v2，新增非空 `context_json`（默认 `{}`）。迁移使用现有 `PRAGMA user_version` runner，旧记录原样保留并回读为空 context；写入改为显式列名，避免后续加列破坏历史兼容。

## Educational Conversation Eval

- `evaluation/context_eval.py` 与 JSONL 黄金集扩展为 100 个多轮场景：指代 16、序数 14、比较 12、assistant artifact 16、用户纠正 4、scope 8、retrieval policy 10；另外分别包含 4 个 20/40/80 轮场景。测试对各类最小覆盖数量设有 release guard，避免后续删用例虚增分数。
- 长会话使用受限的 `history_spec=topic_sequence` 确定性展开为真实 user/assistant turns，报告保存展开后的 `history_turn_count`；不是把一个摘要假装成长会话。教材/学科切换会校验 scope change；检索场景校验 action 与实际 retrieval query。
- 新增显式 `graph/retrieval_policy.py` 边界并接入生产 Retriever。初始策略严格等价于旧行为：禁用教材时 `none`，启用教材时 `full`；active-evidence 输入先用于定义后续 `reuse/delta` 黄金目标。
- 报告提供 resolution/follow-up/reference/state/clarification/retrieval-action/retrieval-query/scope accuracy、standalone preservation、按 tag 分组和逐例失败详情；默认生成报告但不因已知缺口退出失败，`--strict` 可用于未来 CI release gate。
- 100 场景扩展基线为 41/100（41%）：core 7/7、negative 9/9、no-retrieval 3/3；20/40/80 轮均为 2/4。assistant artifact 0/16、clarification 0/3、evidence reuse 0/2、evidence delta 0/2；这些均是未实现能力的真实红灯，不是本轮回归。retrieval action 为 77.8%，retrieval query 与 scope-change checks 均为 100%。

## 影响与验证

- 针对性回归：49 passed，覆盖 v1 -> v2 SQLite 迁移、trace 裁剪、SSE 主链路、状态前后快照、上下文预算、长会话展开、coverage guard、clarification 红灯和 retrieval policy 红灯。
- 后端全量：356 passed；仅有既存 Starlette/httpx2 弃用警告。`git diff --check` 通过。
- 未改变 Planner、Retriever、EvidencePack 排序或回答策略；未修改会话文件、教材索引、向量库、错题和学习记录。现有 RAG trace 数据不删除。

# 2026-08-09 - Citation 协议收口与来源层级整理

- 畸形引用根因：模型偶发输出全角/半角混用的 `［[cite:E7]］`；原前端只识别标准 ASCII `[[cite:E7]]`，因此协议文本会直接显示。会话抽查中对应 E1/E6/E7 的结构化来源均存在，问题不是多轮 metadata 丢失。
- 新回答修复：生成收口阶段统一规范标准、全角混合和折叠 citation token，并按本轮 EvidencePack 的 E-id 白名单删除越界引用；规范化统计随 RAG trace timings 保存。持久化内容与最终 UI 内容使用同一份清洗结果。
- 历史兼容：前端解析器兼容已经保存的全角/半角混合 token，旧会话无需迁移即可恢复为上标引用。
- 编号乱序根因：正文编号按首次引用顺序派生，但来源列表此前仍按 EvidencePack 检索顺序渲染，形成 `1、2、5、3、6、4`。现改为先按正文编号排序，再展示。
- 来源整理：将检索中已有的 `section_path`、`chunk_index` 和推断的 `heading_level` 贯通到 EvidencePack/UI；来源按“教材 → 章 → 现有标题路径”分组，同一位置的多个证据段合并显示，未被正文引用的检索材料默认二次折叠。章名与节名相同时去重，避免 `第六章 / 第六章`。
- 边界：本轮不重建教材索引，不补造索引中缺失的中间标题，不修改向量库、教材数据、数据库结构或依赖。现有 metadata 只有“章 → 三级标题”时，UI 会忠实展示该路径，不会假定其所属二级标题。

## 验证

- 后端针对性测试：21 passed；后端全量：343 passed（仅既有 Starlette/httpx 弃用 warning）。
- 前端 citation 工具：16 passed；前端全量：54 passed；ESLint 与生产构建通过。
- 新增覆盖：全角/半角混合 token、折叠 token、越界 E-id 删除、正文顺序排序、同位置合并、章名去重、现有 section_path 贯通。

# 2026-08-08 - Session 上下文追问 + ConceptMemory + Citation + 对话 UI 专项修复

## 一、Session 内上下文追问（P0）

- 现状确认：此前只有 `backend/conversation_memory.py::rewrite_followup` 的词法拼接（把上一条用户消息拼进 query），没有真正的 Conversation Resolver；graph 从未收到 history，概念抽取/retrieval/answer LLM 都只看改写后的单条 query。
- 三个 Context 测试失败原因（均已实测复现）：
  - Test1 Q3「那前者通常用在哪些传感器里？」：“前者”不在旧 follow-up 标记里 -> 原样进检索 -> KG 只命中「传感器」-> 答错对象。
  - Test2 Q2「条件呢？」：非 follow-up 标记 -> 原样进检索 -> 无法检索到支撑证据。
  - Test3 Q2「再解释一下霍尔效应。」：「再解释」被识别为 follow-up -> 拼接成「解释压阻效应。；再解释一下霍尔效应。」-> retrieval gate 因 focus 词覆盖失败判 `insufficient` -> 拒答。实测 standalone「再解释一下霍尔效应」单独检索完全正常（`supported, matched=[霍尔效应]`），拒答纯粹是错误拼接造成。
- 修复（`backend/conversation_memory.py::rewrite_followup` 重写为规则式 Resolver，毫秒级、无 LLM）：
  1. 自足检测：query 含显式概念时绝不拼接历史（修复 Test3 拒答根因）；
  2. 「前者/后者」：取最近用户消息的比较对（含对侧指代解析）解析（Test1）；
  3. 纯省略追问（条件呢/定义呢/性质呢...）：锚点概念 + 问题模板（Test2）；
  4. 指代词（它/这个/...）：替换为当前显式概念或历史锚点；话题切换引导词（回到刚才的）剥离（Topic Switch Test）；
  5. 解析失败且有指代信号才回退旧拼接。
- 附带修复 `graph/retrieval_node.py`：`_SUPPORT_FILLER_PHRASES` 增加应用场景功能词（通常/用在/用于/应用于/哪些...），避免「通常用在哪些」被当成无法覆盖的 focus 词导致误拒答；缺点/特点/性质 等真实 focus 校验不变。

## 二、ConceptMemory 延迟（P1）

- 确认：`link_concepts_for_response`（UI 概念标签）同步运行在 answer 关键路径（done 事件之前）；确定性部分（词典/别名/KG 扫描）实测 1-3ms，唯一慢点是 `_targeted_repair` 的 LLM 逐项验证（仅当 query 含非 KG 并列概念时触发，约数秒）。`ConceptMemory` 持久化（`_record_concept_memory`）本就在后台线程。真实 trace 显示用户观察到的 5-10s 停顿主要是 plan LLM（非 fast-path 查询），概念链路本身不是主因。
- 修复（`graph/feedback_node.py`）：`link_concepts_for_response` 走 `allow_llm_repair=False` 快速路径（无 LLM），UI 概念标签不再被 LLM 阻塞；完整（含 LLM repair）解析由后台 `_record_concept_memory` 执行，能力保留。增加 fast/full pipeline 耗时日志。

## 三、Container 概念过度抽取（P1）

- 根因：KG 概念无 type 字段；「传感器」「线性代数」等 container 作为 KG 概念被 `query_dictionary` 命中，`coverage_gate` 判 `auto_missing` 后被 `_targeted_repair` 无条件补回（confidence=1.0），成为 core concept。
- 修复：`_targeted_repair` 对与当前 book/subject/chapter container 同名的 `auto_missing` 候选默认不补回（`_container_names_for_state`，book 名去 长书/短书/教材 等后缀）；「什么是传感器？」这类显式询问仍由 kg_matched 路径保留。

## 四、Citation 泄漏（P1）

- 根因：`frontend/src/utils/citations.ts::parseCitations` 正则只匹配 `[[cite:E1]]`；模型连续引用输出的折叠形式 `[[cite:E1][cite:E5]]` 不匹配，原样泄漏进正文。实测单引用/相邻/空格间隔正常，仅折叠形式泄漏。
- 修复：正则升级为 `[[cite:E<id>](?:[cite:E<id>])*]`，单/多/连续/折叠引用统一替换为上标；非法 id 仍剔除。live streaming 与 history 共用同一 parser，两端同步生效。

## 五、概念历史持久化（P2）

- 根因：`append_message` 只持久化 content/sources，`linked_concepts` 只存在于前端内存 state；历史会话重载时概念消失。
- 修复：`append_message` 新增 `linked_concepts` 参数；流式回答在 done 阶段用 `update_message_linked_concepts` 把概念快照补写回原消息（不新增消息、不重新抽取）；`/ask` 路径直接随消息持久化。

## 六、输入框双重蓝线（P2）

- 根因（Electron 实测）：`.chat-question-box` 有 `focus-within:border-accent` 蓝边（预期焦点指示），同时全局 `textarea:focus-visible { outline: 2px solid ...accent }` 因特异性 (0,1,1) 高于 textarea 的 `outline-none` (0,1,0) 而生效，形成内外两层蓝框（“双重输入框”）。box-shadow 已被 `focus:shadow-none` 抑制，非本因。
- 修复：`index.css` 增加 `.chat-question-box textarea:focus-visible { outline: none }`，仅取消内层冗余 outline，外层 focus 指示保留。

## 验证

- 新增回归测试：`tests/test_conversation_followup.py`（Context A/B/C + Topic Switch + 负例）、`tests/test_evidence_support_gate.py`（TestA gate + focus 校验保持）、`tests/test_query_concepts.py`（container 过滤 2 例）、`tests/test_citation_pipeline.py`（概念持久化 2 例）、`frontend/src/utils/citations.test.ts`（折叠引用 3 例）。
- 后端全量 301 passed；前端 vitest 49 passed；`tsc -b` 与 `vite build` 通过。
- 端到端：三个 Context 测试 + Topic Switch 经 resolver -> retrieval gate 均 `supported/partial`，不再拒答。
- 未改动依赖、索引格式、数据库结构、环境要求。

# 2026-08-07 - 关键概念抽取：Query-first 候选 + Coverage Gate + Targeted repair

- 问题：教材激活时最终概念集几乎完全由 KG 驱动（`ConceptLinker` 只返回能精确/别名命中 KG 的概念），且 LLM fallback 仅在 `not book_name and not concepts` 时运行。用户并列列出多个独立概念时，只要其中任何一个不是 KG 中的独立概念（如 "横向效应" 不在 KG、"压电效应" 只有 横向/纵向/正/逆压电效应 子类型而无裸形式），就会漏失。实测 "总结一下横向效应、压阻效应、压电效应的定义和区别" 最终只有 `压阻效应`。
- 实现（新增 `knowledge/query_concepts.py`，只读、无副作用）：
  1. `extract_query_candidates`：确定性并列结构切分（、，,/ 和 与 以及 及 或）+ KG 字典/别名扫描，正常情况不调用 LLM；词典精确命中视为已确认。任务词（定义/区别/特点/优点/缺点/应用 等）与通用噪声在切分时过滤。
  2. 子串包含去重："随机误差、系统误差和粗大误差" 中 "误差" 从未独立出现，不再把 "误差/绝对误差(别名 误差)" 当独立候选；"什么是误差和随机误差的区别" 中 "误差" 有独立出现，保留。精确 canonical 命中优先于别名碰撞。
  3. `coverage_gate`：按 concept_id / 归一化名称比较 query 显式候选与 final concepts；绝不使用 embedding/fuzzy 相似度（压阻效应 vs 压电效应 不会被误合并）。返回 auto_missing（字典确认缺失）与 validate_missing（启发式缺失）。
  4. Targeted repair：字典确认缺失直接补回（不调 LLM）；启发式缺失做一次受限逐项验证（constrained classification，非重新自由生成），仅本地 KG 激活时执行。
- 接入 `graph/feedback_node.py`：`_resolve_final_concepts` 统一 query-first -> 现有 KG linking -> merge -> coverage -> repair；`link_concepts_for_response`（UI）与 `_record_concept_memory`（学习记忆）共用同一结果；后台记忆线程复用 `state["linked_concepts"]` 避免重复 LLM 调用。非教材上下文（学科路由）保持原行为。
- `knowledge/concept_memory.py`：`_CONCEPT_EXTRACT_PROMPT` 改为穷尽式识别语义（不按重要性排序、并列项逐项独立判断、任务词不作概念、上限 8->12）。
- 新增回归测试 `tests/test_query_concepts.py`（覆盖任务 CASE 1-12）。
- 未改动依赖、索引格式、数据库结构、环境要求；未改动检索/证据/Citation/前端。

### Validation

- 真实 pipeline（传感器长书 + DeepSeek repair）："总结一下横向效应、压阻效应、压电效应的定义和区别" 最终概念集 = `[压阻效应(question_mention), 横向效应(query_repair), 压电效应(query_repair)]`，无 "定义/区别"。
- normal case（热敏电阻/正态分布/金属应变片/随机误差等）0 次额外 LLM 调用；repair case 每轮 +1 次受限验证调用，后台记忆不重复调用。
- 精度："随机误差、系统误差和粗大误差？" 精确得到 3 个概念，不再带出 误差/绝对误差；"热敏电阻的定义、特点、优点、缺点和应用" 仅得 热敏电阻。
- 全量测试 284 passed（含 22 个新测试）。
- 残余 best-effort：generic QA（无教材）仍走既有 LLM `extract_concepts`（prompt 已改穷尽式）；"绝对误差" 别名碰撞在既有 linker weak-intent boost 下仍可能进入（KG 数据问题，非本次引入）；"金属应变片" 依赖 KG 中 电阻应变片 的 应变片 别名。

# 2026-08-07 - Desktop dev 模式恢复「接管已有后端」工作流

- 修复：dev（非打包）下 `npm run dev` 现在先探测 `BACKEND_URL/health`，若端口上已有健康后端（如手动启动的 uvicorn）则直接接管、跳过 spawn，不再因端口被手动后端占用而报 `后端进程退出：code=1, signal=null`。
- 根因：8-03 提交 `55fcaf45` 引入的 instance_id 身份握手 + 「自拉后端退出即判失败」逻辑，破坏了「手动起后端 + npm run dev」这一既有工作流——此前自拉失败会被容忍并静默连上手动后端。
- 实现（仅 `desktop/main.cjs`）：`startBackend` 改为 async，dev 路径 spawn 前调用 `probeExistingBackend()` 探测，命中则记录 `dev: adopting existing backend ...` 并返回；`waitForBackend` 的 fail-fast 与 identity 校验改为仅对 `app.isPackaged` 生效；dev 下自拉后端退出时保留 fallback 窗口，确无可用后端才以记录的退出原因判失败；退出处理器按打包/开发模式分流。
- 打包版行为保持不变：仍严格校验 instance_id，自拉后端退出即失败。
- 未改动任何数据、索引、数据库结构或依赖。

### Validation

- dev + 手动后端在 8000：日志出现 `dev: adopting existing backend at http://127.0.0.1:8000 (spawn skipped).`，无 10048、无 code=1，Electron 正常打开并接入手动后端；`node --check` 语法通过。
- dev + 无后端（测试端口 8011）：自拉后端成功（`Uvicorn running on http://127.0.0.1:8011`），前端加载与 API 调用全部 200，无回归。
- 打包版路径未做运行时验证（需完整打包构建），代码与改动前一致。

# 2026-08-04 - Electron textbook retrieval smoke acceptance

- Ran the packaged Electron UI against the local FastAPI backend with the `专业课 / 传感器` textbook scope selected.
- Verified one normal sensor question through the complete UI path, then submitted four consecutive textbook-external questions covering a future market size, a general market-size claim, a sales forecast, and an unrelated Mars-agriculture scenario.
- Closed and cleanly relaunched Electron, restored the sensor scope, and verified a second normal textbook question to confirm that the rebuilt index remained usable across a desktop restart.
- This was a read-only acceptance run: no textbook index, vector collection, mistake record, exercise record, or learning history was modified.

### Validation

- Normal grounded answers: 2/2 completed with correct textbook content and visible chapter/section citations. The post-restart thermistor query returned 10 evidence items and completed in 7.52 seconds.
- Textbook-external refusal: 4/4 correctly refused to fill unsupported facts from model knowledge. All six RAG traces finished with status `done`, empty error fields, and no surfaced HNSW failure.
- Retrieval stage latency across the six requests was 0.77-1.29 seconds. The first normal answer took 36.17 seconds backend total, dominated by 28.38 seconds to generation TTFT; this fails a strict no-obvious-wait latency expectation even though retrieval correctness and stability passed.
- System health after the run was `healthy`; vector-store health reported 49 active chapter indexes and RAG trace storage was healthy.
- Observed UX follow-up: scoped refusal messages still render a textbook source/tag derived from topic-overlap evidence, which can misleadingly imply that the refused fact itself has a citation.

# 2026-08-03 - Sensor index repair and bounded dense fallback

- Created and verified a complete pre-change backup including derived vector data: `learning_data_20260803_233450_pre_sensor_index_rebuild.zip`, SHA-256 `69BA32AF4C652C334F5A46B867631AC046CD9CBA106457A67AF8FFCFE691E665`.
- Rebuilt `传感器短书` through the versioned schema-4 pipeline from 562 preserved OCR chunks. Exact chapter-heading boundaries mapped all chunks to 13 chapters with zero unmatched rows; the activated index now has 13 chapter collections plus one validated whole-book aggregate, version `e883c88af247f5fe`.
- Extended the supported reindex script to hydrate empty chapter shells from exact, monotonic section headings. Missing or out-of-order headings still fail closed instead of guessing.
- Aggregate query failures are now logged and quarantined for the process. Dense fallback receives a BM25 chapter shortlist capped at 12; an unavailable aggregate without a shortlist cannot fan out across more than 12 chapter collections.
- Did not rebuild `传感器长书`: after bounded BM25 preselection it searches only 3-5 chapters in the measured workload, so another index mutation had limited incremental value.

### Validation

- Active short-book mapping: 13 chapter collections + 1 aggregate, 14/14 present, schema 4, 562 lexical/vector chunks, no source fallback.
- Ten repeated short-book aggregate searches: median 23 ms, p95 150 ms, maximum/first query 554 ms; no HNSW errors.
- Real 13-case textbook evaluation: Top-10 complete recall 100%, factual point recall 100%, unanswerable refusal 4/4; total run about 22 seconds versus about 69 seconds before repair.
- Full backend suite: 259 passed with one existing Starlette/httpx2 warning.
# 2026-08-03 - Textbook evidence sufficiency gate and factual-list recall

- Added a query-level evidence sufficiency gate that separates the requested fact from the general topic. Topic-only BM25/vector hits no longer authorize a textbook-grounded answer for unsupported market-size, sales-forecast, or unrelated scenario questions.
- Propagated explicit `supported`, `partial`, `insufficient`, `unavailable`, and `not_applicable` evidence states into generation. Insufficient evidence now produces a scoped refusal; partial evidence must disclose its limitation.
- Kept full section titles in literal and evaluation matching, and retained the complete lexical chunk when dense and BM25 hits share a chunk ID.
- Added an explicit selected-book marker independent of core/reference role. For factual enumeration questions only, selected-book BM25 order is preserved so list members split across consecutive sections survive Top-10 fusion; other intents retain hybrid reranking.
- Expanded the retrieval evaluation set with three topic-overlap but unanswerable questions. No textbook index, vector collection, mistake record, exercise record, or learning history was modified.

### Validation

- Real 13-case textbook evaluation at Top-10: complete recall 100%, factual point recall 100%, and unanswerable refusal 4/4 (100%).
- Full backend suite: 254 passed with one existing Starlette/httpx2 warning.
- Observed but did not modify two independent index/performance issues: one corrupted Chroma HNSW segment is skipped through the existing degradation path, and a 479-chapter dense scan took about 40 seconds.
# 2026-08-03 - Desktop startup identity and SPA route reliability

- Added a constrained React SPA fallback for client-side routes while preserving real 404 responses for unknown API and missing asset paths. Refreshing `/settings`, `/books`, and other application routes now reloads the React entry point.
- Added a per-launch desktop/backend instance ID handshake. A normal Electron launch no longer accepts an unrelated process that merely responds on the configured port; `KAOYAN_SKIP_BACKEND=1` remains the explicit opt-in path for an existing backend.
- Made `parse_method=auto` fall back to local PDF text extraction when neither MinerU API nor CLI is configured, while explicit `mineru` and legacy `require_mineru=True` behavior remain strict.
- Replaced double-escaped updater status strings with actual Chinese messages.
- No textbook index, vector collection, mistake record, exercise record, or learning history was migrated.

### Validation

- Focused SPA, health identity, MinerU routing, and system-health regressions: 12 passed.
- Full backend suite: 247 passed with one existing Starlette/httpx2 warning.
- Frontend Vitest: 38 passed; ESLint and TypeScript/Vite production build passed.
- Electron main-process syntax check and `git diff --check` passed.
# 2026-08-03 - Explicit textbook parsing modes

- Replaced the ambiguous high-quality-recognition checkbox with explicit MinerU parsing and local text extraction choices. Explanations are available from adjacent help buttons instead of permanent secondary copy.
- Added a validated parse_method import field. Selecting local now always bypasses configured MinerU services and uses the PDF text layer; selecting mineru requires the configured API or CLI.
- Kept legacy require_mineru callers compatible when parse_method is absent. External parsed ZIP import remains a separate source option.
- Clarified that local extraction does not perform OCR and is unsuitable for image-only scanned textbooks.

### Validation

- MinerU/local routing regression: 6 passed.
- Frontend TypeScript and Vite production build passed.
- Full backend suite: 243 passed with one existing Starlette/httpx2 warning.

# 2026-08-03 - Versioned textbook indexing and asynchronous concept extraction

- Added one supported schema-4 indexing pipeline for normal imports and manual rebuilds. It builds versioned chapter and whole-book Chroma collections off to the side, validates exact counts plus a real dense query, stages the lexical corpus, validates a real BM25 query, and only then switches the active collection map and lexical file. Failed builds keep the previous active assets.
- Index health now distinguishes `vector_ready`, `lexical_ready`, `source_fallback_active`, `status`, and `index_version`. Legacy direct Chroma-writing maintenance entry points are disabled; `scripts/reindex_book.py` is the supported rebuild command.
- Created and verified a complete pre-change backup including Chroma, progress, books, imports, uploads, and MinerU output: `learning_data_20260803_125018_pre_stable_index_pipeline_error_.zip`, SHA-256 `190910097881834e55b505cd30d95d1988be6e043a6918d949f4a18049f88a79`.
- Rebuilt `error theory and data processing` from its 511 preserved OCR chunks while retaining chunk IDs. The activated index has 7 chapter collections, one whole-book collection, 511 persisted lexical rows, schema 4, version `b0a00943f1bc0436`, and no source-file fallback.
- Textbook import now offers an explicit, default-off option to send selected excerpts to the configured external LLM for concept-index extraction. The searchable textbook finishes first; concept extraction runs as a separate durable job and cannot turn a successful import into a failure.
- Renamed the learning-page action from the misleading knowledge-relation wording to `extract textbook concept index`. Candidate checkpoints are content-fingerprint aware, and a completed graph is activated from a dedicated directory only after extraction finishes.

### Validation

- Real hybrid retrieval for the rounding question returned `status=ok` and included the exact `digital rounding rules` section with all three rules.
- Full backend suite: 242 passed with one existing Starlette/httpx2 warning.
- Frontend TypeScript and Vite production build passed.

# 2026-08-03 - Read-only retrieval fallback for imported source chunks

- When a persisted lexical index is absent, textbook retrieval now reads existing `*_middle_chunks.json` import artifacts as a cached, read-only BM25 source.
- Persisted lexical indexes remain preferred. The fallback does not create or modify Chroma collections, lexical index files, textbook data, or learning records.
- This restores direct evidence retrieval for the imported error-theory textbook, whose source chunks exist but whose Chroma and persisted lexical indexes are absent.

### Validation

- Fallback regression passed; real error-theory retrieval included the rounding section and all three rules in the generation prompt; full backend suite passed 240 tests with one existing Starlette/httpx2 warning.

# 2026-08-02 - Thread-safe vector-store startup

- Serialized the process-wide `ChapterVectorStore` singleton initialization so startup warmup and an early retrieval request cannot create competing Chroma `PersistentClient` instances for the same path.
- Vector-store reset now uses the same lifecycle lock. Constructor failures leave the singleton empty so a later request can retry normally.
- No vector collection, mapping, textbook index, or user learning data was changed.

### Validation

- Concurrency regression passed; a real 8-thread probe produced one initialized instance; full backend suite passed 238 tests with one existing Starlette/httpx2 warning.

# 2026-08-01 - Subject routing and conversation scope isolation

- Lexical subject routing now compares the current subject's textbooks too; another subject must clearly outperform the current one before a transfer is suggested.
- Each conversation ID is bound to one exact subject and textbook scope. Scope changes create a new ID in the frontend, with a matching backend safeguard.
- Legacy mixed-scope conversations expose only messages from their current scope. Move-turn and reclassify-conversation workflows remain supported.

### Validation

- Real-index routing checks passed for three error-theory questions; backend 236 passed; frontend lint and TypeScript/Vite production build passed.

# 2026-07-23 - 教材、学习汇总与页面初始化性能优化

- 教材 PDF 列表、metadata、章节 JSON 和索引健康状态增加线程安全文件快照缓存；文件签名变化自动刷新，章节或 metadata 写入后主动失效。
- KG 学习汇总增加 5 秒依赖感知缓存；概念记忆、错题 SQLite/WAL 或学习事件 SQLite/WAL 变化会立即重算，失败响应不缓存，概念复习成功后主动清空。
- 新增习题与错题 overview 聚合接口并保留全部旧接口；习题页初始化从列表、统计、活动会话 3 个请求降为 1 个，错题页从列表、待复习 2 个请求降为 1 个，错题统计请求改为并行。

### Validation

- 教材缓存微基准：约 2000 条章节 JSON 连续读取 100 次，从约 270 ms 降至约 41 ms，当前环境约 6.6 倍。
- 缓存、KG 与聚合端点定向回归：18 passed；聚合流程扩展回归：14 passed。
- 后端全量回归：187 passed。
- 前端 ESLint、Vitest 14 项、TypeScript 与 Vite 生产构建通过。
# 2026-07-23 - 保守解耦第二批

- 将习题练习会话的创建、读取、作答、暂停、恢复、放弃和幂等错题转换编排迁入 `ExercisePracticeService`；SQLite 原子状态转换继续由现有 `ExerciseBank` 负责。
- 将教材 OCR 章节形态识别、目录解析、标题降级和前端章节格式化迁入无 I/O 的 `backend/services/book_chapters.py`。
- 原 API 路由、响应字段和兼容函数名保持不变；教材导入提交、失败回滚、向量索引与当前教材状态没有迁移。

### Validation

- 练习会话定向回归：14 passed。
- 教材章节与导入相关定向回归：22 passed。
- 后端全量回归：177 passed。
# 2026-07-23 - 保守解耦第一批

- 将知识图谱学习汇总中的日期计算、错题摘要和概念复习优先级迁入无 I/O 的 `backend/services/kg_learning_summary.py`；API 保留原函数签名和错题库读取职责。
- 将错题图片上传、暂存、优化、提交和清理迁入 `MistakeImageStore`；API 保留同名兼容包装，OCR 路由和图片事务语义不变。
- 将错题图片裁剪/锐化工具及习题、错题无状态展示组件迁入 `frontend/src/features`；页面请求、状态和交互流程不变。
- 教材导入和习题练习状态机暂未迁移，避免在第一批同时触碰高风险写入链路。

### Validation

- KG 定向回归：10 passed。
- 错题图片与 API 定向回归：20 passed。
- 后端全量回归：174 passed。
- 前端 ESLint、Vitest 14 项、TypeScript 与 Vite 生产构建通过。
# 2026-07-23 - P0/P1 稳定性与安全修复

- 修复流式 `<think>` / `</think>` 标签跨 chunk 时推理内容泄漏；未闭合推理块与不完整标签片段会安全丢弃。
- 收紧本地 API Origin 校验，不再信任请求可控的 `Host`；错题图片识别/解答补充 24 MiB 请求上限，移动采集令牌也不能绕过上传限制。
- MinerU 配置改为调用时读取，API、CLI 与显式本地降级路由均可达；移除从未被代码支持的 `OCR_API_URL` 部署项并纠正文档。
- 教材 PDF 先写入暂存区，解析成功后才进入资料库；导入失败或取消时清理新建 PDF、章节、MinerU、词法与向量产物，同名教材使用唯一存储名。
- 后台任务完成与取消改为 SQLite 条件更新，消除“取消请求覆盖已完成任务”及“取消后仍提交完成”的竞态。
- 错题 OCR 图片先进入待提交区，保存错题后才转为永久文件；识别、解答、数据库保存失败及删除错题时清理对应图片，过期待提交文件自动回收。

### Validation

- P0/P1 定向回归：45 passed。
- 后端全量回归：171 passed。
- 前端 ESLint、Vitest 11 项、TypeScript 与 Vite 生产构建通过。
- Electron 主进程/预加载脚本语法检查、Python AST 检查、Docker Compose YAML 解析和 `git diff --check` 通过。
# 2026-07-21 - 教材抽题页码映射修复

- 修复习题工作区使用 PDF 物理页码，而现有 MinerU/OCR/source package chunk 使用教材印刷页码时，已有 chunk 被误判为空并触发 Kimi Vision OCR 的问题。
- 抽题时读取 PDF page labels：显式选页先映射到印刷页检索现有 chunk；仅按章节抽取时则把印刷页反向映射到 PDF 物理页，供 PDF 文本层和 OCR 降级使用。
- 未手动填写章节时，根据映射后的印刷页范围自动推断唯一章节，并将章节字段传递到候选题和习题库记录。
- 页码范围跨越多个章节或无法匹配目录时，停止生成可导入候选并提示缩小范围或手动填写章节，避免无章节题目进入题库。
- 不修改教材索引、OCR 产物、向量库或学习记录。

### Validation

- 真实教材验证：不填写章节时，传感器短书 PDF 第 52 页映射为印刷第 42 页，自动归入“第二章 电阻式传感器”，命中 1 个 source package 习题 chunk，未调用 OCR。
- 教材抽题与入库定向回归：14 passed。

# 2026-07-18 - AutoDL MinerU 教材解析全流程说明

- 将 `docs/mineru_deploy.md` 重写为 AutoDL 全流程教程，覆盖租卡与镜像选择、独立环境安装、上传、5 页试跑、整本解析、产物打包下载、桌面端导入、关机计费、SSH 隧道直连和故障排查。
- 明确 `GPU Host` 是远端 GPU 实例的泛称；默认推荐输出包流程，直连则使用本地 SSH 隧道端点 `http://127.0.0.1:9001`，避免暴露无认证 API。
- 同步修正首次运行向导、系统设置和 `.env.example` 中含糊的 `gpu-host` 示例。
- 指令依据 MinerU 3.x 与 AutoDL 当前官方文档核对；未租用真实付费实例执行 MinerU。
# 2026-07-18 无教材通用问答学习记录修复

- 无教材科目的通用问答统一写入 `default` 学习空间；学习情况页不再强制要求选择教材，并可按科目查看概念、活动与复习队列。
- 学习情况页新增“最近问答题干”，通用问答即使没有形成严格概念，也会保留完整问题并参与每日问答统计。
- 通用问答在回答完成后的后台反馈阶段启用概念抽取降级；仅保留置信度不低于 0.85、且概念名或有效别名直接出现在问题中的严格概念，其余仅存为候选，不影响复习统计。
- 有教材问答仍优先使用本地知识图谱关联，不新增 LLM 调用；知识关联增强仍只对真实教材开放。

### Validation

- 后端定向回归：7 passed（反馈节点与学习记忆 API）。
- 前端 TypeScript 与 Vite 生产构建：通过。
# 2026-07-18 Electron sidebar and window-control fixes

- Standardized expanded and collapsed sidebar navigation icons at 18px, including the sidebar toggle icons.
- Kept desktop sidebar states mounted and added a restrained width/cross-fade transition, with a `prefers-reduced-motion` fallback.
- Restored reliable frameless-window control hit testing by giving the title-bar overlay its real 52px height and explicitly keeping the control capsule and buttons out of Electron drag regions.
# 2026-07-18 Learning-summary concept criteria and review feedback

- Unified strict concept/exposure criteria at confidence >= 0.85 plus a direct concept or meaningful alias mention; explicit mistake links remain eligible. Strict concepts count unique names, while high-confidence exposures count events.
- Stopped treating ordinary definition/formula/property requests as automatic weakness. Weak concepts now come from mistakes, explicit learner difficulty, review quality 0-2, or manual marking. Legacy QA-only false positives are ignored in statistics and queues.
- Added an in-progress state and durable success feedback for concept review. Concepts reviewed today are removed from both concept-review queues to prevent repeated no-op clicks.
- Added criterion help text to the three concept metric cards.
## 2026-07-16 - 扫描教材按页抽题与桌面标题栏避让

- 修复扫描教材已选择 PDF 页码、但既有 OCR 切分缺少页码元数据时无法抽题的问题：现有 source package、MinerU、外部 OCR 和 PDF 文本层均未命中后，对明确选择的最多 8 页执行 Kimi Vision 按页 OCR，并复用页面缓存。
- Kimi 按需阅读统一使用 `KIMI_VISION_MODEL` 与 `MOONSHOT_API_BASE`，避免把正文 LLM 模型名错误发送到 Moonshot Vision 接口。
- 习题工作区顶部增加 Electron 窗口控件安全区，右上角刷新按钮不再被最大化/关闭状态栏遮挡。
- 不修改教材索引、向量库、外部 OCR 切分或学习记录。

### Validation

- 教材抽题定向回归：6 passed。
- 后端完整回归：119 passed，1 条第三方 TestClient 弃用警告。
- 前端 ESLint：通过。
- 前端 TypeScript 与 Vite 生产构建：通过。

## 2026-07-15 - 存储版本治理与稳定教材身份 P0-P1

### P0：版本、备份与原子写入

- 新增 `data/storage_manifest.json`，统一记录业务组件版本，并明确区分不可重建数据、昂贵派生产物和可重建检索索引。
- 学习进度、测验历史、聊天历史和间隔复习卡片改用临时文件 + `fsync` + 原子替换；保持旧 JSON 数组/对象形状，现有直接读取路径无需迁移。
- 备份格式升级到 v2，加入数据 schema、组件版本和数据分类；恢复端可在内存中将 v1 manifest 迁移到 v2，旧备份继续可用。
- 默认备份新增存储组件清单；Chroma 仍是可选的可重建派生索引，未迁入 SQLite。
- 错题库、习题库、学习事件、后台任务和 RAG trace SQLite 文件接入统一迁移执行器，并写入 `PRAGMA user_version = 1`；遇到比程序更新的数据库版本会拒绝静默打开。

### P1：稳定教材身份与生命周期

- 新增版本化 `book_registry.json`，教材使用 UUID `book_id` 作为稳定身份，物理 `storage_name` 与可修改 `display_name` 分离。
- 启动时为现有教材补齐 `book_id` 和元数据；不移动 PDF、进度目录、SQLite 文件或 Chroma collection。损坏的 metadata 会跳过并报告，不会被静默覆盖。
- 教材列表、当前教材、切换和更新响应返回 `book_id`；相关接口兼容旧存储名与新 ID。
- 资料库支持逻辑重命名、归档列表和恢复。逻辑重命名只更新展示名称，物理存储名保持不变。
- 新错题和习题自动写入对应 `book_id`，旧 JSON blob 记录缺少该字段时继续按默认值读取。
- 彻底删除增加影响预览、精确 `book_id` 二次确认和删除前完整安全备份；归档仍不删除任何文件、索引或学习记录。

### Compatibility and validation

- 未执行现有教材文件搬迁、Chroma 重建或真实数据删除。
- v1 备份、无 `book_id` 的教材元数据、旧错题/习题记录及旧学习 JSON 均保留兼容路径。
- 后端最终全量回归：117 passed，1 条第三方 TestClient 弃用警告。
- 前端 ESLint 通过；Vitest 3 个测试文件共 9 项通过；TypeScript 与 Vite 生产构建通过。
- `git diff --check` 通过。
## 2026-07-13 - v1.0.0 教材范围与桌面端体验修复

- 将问答范围从“物理教材文件”提升为逻辑教材范围。具有相同资料组，或同一科目下的主要教材与辅助教材，在对话界面合并为一个范围；当前传感器短书与长书统一显示为“传感器”。
- 保留检索层的主辅优先级：短书继续作为主要来源，长书作为辅助来源参与补充，不删除、不迁移任何教材索引。
- 设置页将“检索角色”改为更易理解的“教材用途”，使用“主要教材 / 辅助教材 / 独立使用”，并直接说明辅助教材补充的资料组及其在问答中的行为。
- 有教材时不再提供通用 QA 入口。首次进入会优先选择当前学科下的逻辑教材范围；只有尚未导入任何教材时才保留通用 QA。
- 合并范围兼容既有历史会话：短书和长书下保存的旧传感器对话会一起显示，加载后归一为传感器学科范围。
- 桌面模式下，新建会话和加载历史会话不再自动折叠侧边栏；紧凑布局仍保持抽屉式自动关闭行为。
- 教材范围菜单改为基于视口定位的浮层，自动选择向上或向下展开，并限制在窗口边界内，修复非全屏时左侧菜单被裁切的问题。
- 收紧“考研助手”和“学习对话”的标题字号，提高学科范围字号，使标题、导航和选择器层级更均衡。
- Electron 顶部标题区域支持标准双击最大化或还原；右上角按钮行为保持不变。

### Compatibility

- 无数据迁移，无索引重建，不修改已有教材、错题、向量库或学习记录。
- 旧会话中保存的传感器短书或长书名称继续有效。
- 显式资料组优先于科目分组；没有有效主要教材的辅助教材组不会被错误隐藏。

### Validation

- Frontend production build passed: `tsc -b && vite build`.
- Frontend lint passed: `eslint .`.
- Frontend unit tests passed: 9 tests across 3 files, including logical textbook-scope grouping and invalid-group fallback.
- Local UI regression passed at 1280x720 and 900x650: sensor scope appeared once, the menu stayed inside the viewport, old short/long-book conversations remained visible, and the desktop sidebar stayed expanded after new/load conversation actions.
- Settings UI regression confirmed the primary/auxiliary labels and the explicit “辅助传感器” guidance.

## 2026-07-13 - Generalize textbook indexing, retrieval groups, and KG enhancement

- Removed inferred prerequisite/extension KG paths from answer generation and concept linking. Runtime KG retrieval now uses evidence occurrences and verbatim formulas only; unverified directional relations remain disabled.
- Added a canonical textbook chunk model that preserves page index, bounding box, formula text, semantic role, section hierarchy, source Markdown, and neighboring chunk IDs through MinerU import.
- Added a schema-3 versioned whole-book Chroma collection. Rebuilds create the new aggregate before switching the collection map, while existing per-chapter collections and lexical indexes remain available for degradation fallback.
- Added opt-in KG enhancement for any imported textbook as a durable background job. The UI estimates the selected excerpt volume and requires explicit confirmation before sending excerpts to the configured external LLM. Extracted names, definitions, aliases, and formulas are checked against source text; no directional relations are generated.
- Replaced sensor-specific retrieval routing with metadata-driven `standalone`, `core`, and `reference` roles. Core/reference books can share an explicit resource group or, when no group is set, the same subject; priorities are configurable without changing code.
- Persisted import source paths so downstream exercise extraction and PDF lookup can use metadata for user-imported books before legacy packaged-data fallbacks.
- Index acceptance remains an internal system check (non-empty/healthy vector and lexical indexes plus rebuild consistency); users are not asked to know or enter chapter or chunk counts.

### Compatibility and migration

- Existing textbook indexes are not deleted or mutated automatically. The schema-3 aggregate is created on the next explicit import/reindex.
- Existing books default to `standalone`, so retrieval behavior does not broaden until a user assigns `core`/`reference` roles.
- Existing packaged sensor/error-theory source aliases remain read-only fallbacks for old data; new imports use recorded metadata paths.

### Validation

- Python compile check passed for all changed backend, ingestion, retrieval, KG, utility, and test modules.
- Frontend TypeScript and Vite production build passed.
- New textbook-generalization regression suite passed with a clean exit: 5 passed.
- Full backend suite completed all assertions: 92 passed, 1 dependency warning in 25.75s. The command wrapper timed out during process cleanup after pytest printed its completed report.
- FastAPI route smoke check confirmed the KG enhancement, estimate, and generic job-status routes are mounted.
- `git diff --check` passed.

## 2026-07-12 - Textbook exercise extraction page scoping

- The PDF picker now navigates the embedded preview to the entered page and the selection action sets both range endpoints to that page, preventing a stale end page from expanding a single-page request into a large range.
- Explicit page-scoped extraction now rejects chunks with unknown page metadata instead of treating them as matches for every page.
- Page resolution now supports zero-based page_idx values, page/page_number/pdf_page/page_no fields, source_markdown filenames, and page references.
- Source-package fallback warnings now report the selected range and retain that same range for fallback extraction.

### Validation

- Full backend test suite: 85 passed, 1 dependency deprecation warning.
- Frontend npm production build: passed.

## 2026-07-12 - Runtime shutdown and non-blocking startup

- Background textbook prereading now clears its running flag and persists a terminal completed/stopped/failed status even when reader initialization or progress persistence fails.
- FastAPI startup now exposes /health immediately and performs embedding/vector-store warmup in a daemon thread. The health payload includes a separate warmup state, and embedding initialization is protected against duplicate concurrent loads.
- Chat SSE explicitly closes the underlying graph generator when the client disconnects, allowing generator cleanup to run promptly.
- Electron shutdown now waits for backend cleanup. On Windows it uses taskkill /T /F for the backend PID so Python/PyInstaller and descendant processes are removed before the desktop app exits; updater installation follows the same cleanup path.

### Validation

- .\\venv310\\Scripts\\python.exe -B -m pytest -q -p no:cacheprovider: 83 passed, 1 dependency deprecation warning.
- node --check desktop/main.cjs and git diff --check: passed.

## 2026-07-12 - Harden PDF preview, durable answer generation, and OCR highlight lookup

- Served textbook PDFs with an explicit inline content disposition and reduced the exercise PDF modal to a compact desktop-friendly size.
- Hid the unfinished agentic review-plan actions and reserved title-bar space for Electron window controls.
- Reworked the exercise workspace into a full-width question followed by editable user-answer and standard-answer areas.
- Moved standard-answer generation to persistent background jobs. The frontend resumes queued/running jobs after navigation and only saves the generated draft after user review.
- Fixed chapter and subsection highlight source discovery to prefer the populated external OCR output and infer chapter boundaries for legacy chunks without page metadata.

### Validation

- Confirmed the packaged sensor PDF exists and is returned as application/pdf with an inline filename header; Chromium rendered it in the page-select modal.
- Confirmed the real short-book OCR source returns 32 chunks for chapter 1 and 18 chunks for its first subsection.
- Added regression coverage for durable answer jobs and page-less external OCR chunks; the full backend suite passed with 81 tests and the frontend production build passed.

---
## 2026-07-12 - Merge sensor course scope, restore TOC, and ground exercise answers

- Unified the normal frontend scope selector into one 专业课/传感器 entry displayed as “传感器（短书重点 + 长书补充）”; the highlight repository intentionally keeps the two physical books separate.
- Canonicalized sensor retrieval to use 传感器短书 as the primary KG/vector/BM25 source and 传感器长书 as the lower-priority reference source, including legacy long-book selections.
- Kept the existing core/reference reranking bias so short-book evidence wins when both books cover the same concept, while long-book chunks can fill missing details.
- Restored data/progress/传感器短书/_chapters.json from Chapter.md: 13 chapters and 65 subsections. The former 479-item OCR-heading file is preserved as _chapters.bak_before_chapter_md_restore_20260712.json.
- Changed chapter persistence to collapse external OCR heading/chunk records into a real TOC before saving, preventing future reimports from exposing hundreds of chunks as chapters.
- Tightened chapter-highlight generation to evidence-only OCR summarization: no model-memory completion, self-authored questions, external analogies, or internal chunk identifiers. Bumped the prompt version so old artifacts are marked stale.
- Replaced the inline exercise PDF iframe with a large modal viewer that opens on textbook selection or page entry, supports direct page navigation, and can copy the selected page into the extraction range.
- Added exercise answer draft APIs and UI: retrieve with the same hybrid textbook strategy as QA, enforce the evidence gate, generate an editable answer draft, and save only after user review.

### Validation

- Python AST validation passed for all changed backend/retrieval/highlight modules; the full backend suite passed: 79 tests, 1 deprecation warning.
- Frontend TypeScript and Vite production build passed; this is the static frontend served by the Electron backend.
- The actual highlight service returned 13 chapters / 65 subsections, including “第二节 等效电路与测量电路” at p107.
- A read-only “霍尔效应是什么” probe returned 6 grounded evidence items; short-book evidence occupied the top two ranks. Runtime role fallback now labels legacy long-book lexical rows as reference without requiring an index rebuild.

---
## 2026-07-12 - Restore chat concept feedback after external OCR index rebuild

- Backed up the three imported textbooks' existing learning metadata under `data/backups/kg_learning/20260711-235745` before generating knowledge graphs.
- Added `scripts/build_external_ocr_knowledge_graph.py` to assemble runtime knowledge graphs from the existing reviewed OCR concept candidates and long-book concept links without repeating LLM extraction.
- Generated local runtime graphs for 传感器短书 (282 concepts), 传感器长书 (86 linked concepts), and 误差理论与数据处理 (184 concepts) under each book's `hybrid_auto_external` directory.
- Updated `KnowledgeGraph` discovery to load `hybrid_auto_external` graphs and updated the three-book OCR index rebuild script to regenerate matching graphs after vector indexing.
- Mirrored runtime graphs into each book's progress seed and desktop/sample_data_three_books, so packaged Electron installs can load the same graphs from user data without relying on the repository-level MinerU directory.
- Changed strict chat exposure acceptance from confidence 1.0 to 0.85 while retaining the direct question mention requirement and generic-alias exclusion. Uncertain or indirect matches remain candidates.
- Preserved stable concept IDs using canonical-name hashes so repeated rebuilds do not break existing ConceptMemory links.

### Validation

- Runtime graph loading passed for all three books; concept counts were 282 / 86 / 184.
- Concept-link quality probes found 压阻效应, 传感器, 系统误差, and 随机误差 from representative questions.
- End-to-end learning write probe for “什么是压阻效应” linked the canonical concept at confidence 0.88 and increased the formal exposure count from 0 to 1.
- Targeted feedback and system-health tests passed: 5 passed, 1 warning.

---
## 2026-07-10 - CPU-only desktop installer with three-book sample data

- Audited the desktop release changes after the previous CUDA DLL packaging failure.
- Confirmed the release dependency set pins torch 2.11.0+cpu and the GitHub desktop workflow installs requirements-release.txt.
- Found two remaining verification gaps: torch.cuda.is_available() can be false for a CUDA build without a working driver, and the old post-build check allowed a complete CUDA DLL set to pass.
- Hardened scripts/build-desktop-backend.ps1 to require an explicit +cpu torch version, require torch.version.cuda to be null, validate required sample data, and fail on any CUDA binary or PE import.
- Added scripts/verify_cpu_only_build.py, which parses Windows PE import tables without third-party dependencies and checks every packaged EXE/DLL, including shm.dll.
- Bundled desktop/sample_data_three_books as the seed dataset: 6435 files / 689.6 MiB, including the PDFs, OCR imports, progress/KG data, CPU embedding model, and clean Chroma index for 传感器短书、传感器长书、误差理论与数据处理. 优化设计 remains excluded.
- Rebuilt the PyInstaller backend and generated release/kaoyan-assistant-desktop-setup-0.1.0.exe.

### Validation

- Build environment: torch 2.11.0+cpu, torch.version.cuda=null, torch.cuda.is_available()=False.
- Fresh backend build passed the PE verification: 67 EXE/DLL files inspected, zero CUDA/NVIDIA binary names, and zero CUDA import references.
- Packaged shm.dll imports torch_cpu.dll and c10.dll; it does not reference torch_cuda.dll.
- Packaged seed contains 6435 files. All three PDF hashes match the source seed, and vector_db/chroma.sqlite3 also matches.
- Installer size: 564147970 bytes (538.0 MiB).
- Installer SHA-256: 57BFE1C17C539968BB24A5701B2F2AF9E258EE8D71032D5BD6338024C9ABE9E7.
- Frontend production build, PyInstaller backend build, and electron-builder NSIS build passed.
- A packaged-process /health smoke launch was attempted but blocked by the Codex execution-approval quota; this was not counted as passed.

---
## 2026-07-10 - High-priority reliability and local data safety fixes

- Moved streaming feedback persistence off the user-visible completion path. Streaming and non-streaming answers now survive learning-memory write failures; the SSE done event is no longer replaced by an error.
- Split local KG concept linking from background learning records and removed the automatic post-answer LLM concept-extraction fallback, preventing a hidden second LLM call before completion.
- Replaced automatic deletion of non-empty SQLite WAL/SHM/journal files with conservative recovery that removes only zero-byte artifacts and preserves files that may contain recoverable transactions.
- Added a URL scheme allowlist and a restrictive Content Security Policy to generated chapter-highlight HTML; executable, data, file, and protocol-relative links are no longer rendered as anchors.
- Lifted active chat cancellation into ChatContext, added AbortSignal support for non-streaming chat, and guarded stream callbacks by request generation so new/loaded conversations cannot be overwritten by stale events.
- Added striped per-conversation locks around JSON read-modify-write persistence to prevent concurrent message loss.
- Added regression coverage for stream completion, no automatic feedback LLM call, concurrent conversation writes, conservative SQLite recovery, and chapter-highlight HTML safety.

### Validation

- Full backend test suite passed: 71 passed, 3 warnings.
- Targeted high-priority regression suite passed: 12 passed, 3 warnings.
- Frontend tests passed: 2 test files, 7 tests.
- Frontend production build passed.
- Frontend lint completed with no errors and the existing HighlightRepositoryDialog.tsx hooks dependency warning.

---
## 2026-07-03 - RAG retrieval hardening and Chroma recovery

- Preserved final prompt chunk metadata in retrieval state via `retrieval_debug_items`, including rank, chapter, chunk id, source, role, section title, page index, direct-hit flag, TOC-like flag, and preview text.
- Changed the RAG evaluator to score the final prompt chunks instead of an intermediate KG-only order, and added `bootstrap` support for expanding KG-derived golden sets.
- Improved KG concept ranking so exact short concept names win over longer partial matches, while TOC/directory chunks are filtered or downranked before prompt assembly.
- Added section title and page index metadata to newly built vector chunks.
- Added `scripts/rebuild_vector_store_from_mineru.py` to safely rebuild Chroma from MinerU middle chunks with timestamped backups.
- Rebuilt the optimization-design vector store from MinerU output. Previous vector DBs were kept at `data/vector_db.backup-20260703-221607` and `data/vector_db.backup-20260703-222412`.
- Kept third-layer generated-answer evaluation opt-in; the external API retry was not used because it would send local textbook context outside the machine without explicit authorization.

### Validation

- `./venv310/Scripts/python.exe -B -m pytest tests/test_rag_retrieval_eval.py tests/test_rag_degradation.py tests/test_chat_stream_reliability.py -q` passed: `8 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --golden data/eval/rag_golden_optimization_40.jsonl --output data/eval/rag_eval_report_40_top_level.json` completed outside the Windows sandbox so Chroma/SQLite journal writes could run normally.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag_ir_measures.py --report data/eval/rag_eval_report_40_top_level.json --output data/eval/rag_eval_ir_measures_report.json` passed using the external `ir_measures` library.
- Final 40-sample report: retrieval status `ok=40`, Hit@1 `0.775`, Hit@3 `0.975`, Hit@5 `1.0`, MRR `0.8729166667`, expected chapter hit rate `1.0`.
- External `ir_measures` cross-check matched the retrieval metrics and added ranking quality scores: `R@1=0.775`, `R@3=0.975`, `R@5=1.0`, `R@10=1.0`, `RR@10=0.8729166667`, `nDCG@3=0.8946394630`, `nDCG@5=0.9054063770`, `nDCG@10=0.9054063770`.
- Non-escalated SQLite probes still fail in the restricted Windows sandbox with `disk I/O error`; escalated local probes and the rebuilt Chroma evaluation succeed, indicating the observed failure is sandbox/journal related rather than a remaining retrieval-node crash.

---

## 2026-07-03 - Local RAG evaluation harness

- Added `scripts/evaluate_rag.py` for three-layer RAG checks: deterministic retrieval metrics, context relevance proxies, and optional generated-answer quality proxies.
- Added a starter JSONL golden set at `data/eval/rag_golden_optimization.jsonl` for the current optimization-design textbook index.
- Kept external evaluator libraries out of runtime dependencies; generated-answer checks are opt-in with `--with-generation` so retrieval experiments can run without API/network access.

### Validation

- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py --help` passed.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --limit 6 --output data/eval/rag_eval_report.json` completed; vector retrieval degraded because Chroma returned SQLite `disk I/O error`.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --limit 1 --with-generation --output data/eval/rag_eval_report_generation_sample.json` was attempted without escalation and recorded `Connection error`; escalated external API retry was rejected because it would send local textbook context to an external LLM.

---

# 2026-07-03

- Refined the Electron-only startup and window chrome polish: `desktop/loading.html` now uses the current black/white/blue Apple-inspired visual language with a frosted-glass panel, subtle entrance motion, reduced-motion fallback, and readable Chinese startup/error copy.
- Changed the Electron title controls from a full-width top strip into a floating glass control capsule with a narrow invisible drag strip, so the desktop app no longer looks like a browser page wrapped by a separate title bar.
- Kept the glass/motion treatment scoped to Electron startup/chrome as a low-risk trial before applying similar transitions to broader web/Electron modal surfaces.
- Added frontend typography tokens and mapped the Electron desktop chat shell, sidebar, home cards, toolbar, and composer to a smaller unified type scale.

### Validation

- `./venv310/Scripts/python.exe -B scripts/check_encoding.py --json encoding_audit_report.json --fail-on-issues` passed: `invalid_utf8=0`, `bom_files=0`, `suspicious_files=0`.
- `npm.cmd run build` passed.
- `npm.cmd run lint` completed with no errors and the existing `HighlightRepositoryDialog.tsx` React hooks dependency warning.

---
# Patch Notes - Texa

This file records version changes, bug fixes, migration notes, validation results, and environment repair records.

Note: Earlier historical entries contained mojibake from an encoding mismatch. Those damaged details were compressed on 2026-07-03 instead of being guessed back into Chinese text. For long-term constraints and architecture, use `AGENTS.md`.

---

## 2026-07-03 - Stage closeout cleanup

- Cleaned `patch_notes.md` so the file is UTF-8 readable and no longer carries historical mojibake blocks.
- Kept this file focused on durable release notes and validation results; unstable or damaged historical prose was replaced with this explicit note.

### Validation

- `./venv310/Scripts/python.exe -m pytest -q` passed: `59 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -B scripts/check_encoding.py --json encoding_audit_report.json --fail-on-issues` passed: `invalid_utf8=0`, `bom_files=0`, `suspicious_files=0`.
- `npm.cmd run lint` completed with no errors and one existing React hooks dependency warning in `HighlightRepositoryDialog.tsx`.
- `npm.cmd test` passed outside the Windows sandbox after the sandboxed run hit `spawn EPERM`: `2 passed`, `7 passed`.
- `npm.cmd run build` passed.

---

## 2026-07-03 - Controlled Learning Tool Registry

- Added `backend/tools/` with a controlled tool registry for textbook search, concept search/linking, due mistakes, mistake stats, review-plan building, and confirmation-only write proposals.
- Added `/api/agent/tools`, `/api/agent/tools/call`, and `/api/agent/read-only` as the first read-only agent orchestration surface.
- Mounted the new agent router in `backend/main.py`.
- Added frontend API client helpers and TypeScript response types for listing tools, calling a tool, and running the read-only agent.

### Validation

- `python -m pytest tests/test_agent_tools.py -q` passed in the original feature run.
- Importing `backend.main.app` confirmed `/api/agent/read-only` was registered.

---

## 2026-07-03 - Read-only agent frontend entry points

- Connected the controlled read-only agent to chat quick workflows for today's review plan and recent weak-point/mistake analysis.
- Added `AgentResultCard` to show synthesized answers, collapsed tool evidence, and confirmation-only pending actions.
- Added an AI review-plan action to the Learning page header.

### Validation

- `npm.cmd run build` passed in the original feature run.
- `python -B -m pytest tests/test_agent_tools.py -q` passed in the original feature run.

---

## 2026-07-03 - Project encoding audit

- Added `scripts/check_encoding.py` to scan project text files for UTF-8 decode failures, BOMs, replacement characters, long question-mark runs, and common Chinese mojibake fragments.
- Removed UTF-8 BOM noise from source and documentation files.
- Fixed mojibake in `memory/exercise_importer.py` prompt text, `knowledge/concept_memory.py` docstrings, and affected tests.
- Recorded that `patch_notes.md` was the only remaining suspicious file before this cleanup.

### Validation

- `python -B scripts/check_encoding.py --json encoding_audit_report.json` previously reported `invalid_utf8=0`, `bom_files=0`, and `suspicious_files=1` for `patch_notes.md`.
- The closeout run should regenerate this report after the cleanup.

---

## 2026-07-03 - Chapter highlight repository task state and compact layout

- Fixed chapter-highlight repository progress so background-generation state only appears for the matching selected book, chapter, section, and job target.
- Bound highlight jobs to a concrete generation scope and surfaced completion prompts that jump to the generated highlight result.
- Moved the highlight repository dialog to a portal attached to `document.body`, improving compact-window and Electron layout behavior.
- Lowered the Electron desktop minimum window size to `720x560` to support compact layout verification.

### Validation

- `npm.cmd run build` passed in the original feature run.
- Full-chapter highlight generation remained serial by section; this is still the primary latency point.

---

## 2026-07-03 - Mistake image crop interaction

- Reworked mistake-image capture cropping from numeric sliders into a draggable selection rectangle on the image.
- Added drag-to-move, eight edge/corner resize handles, and drag-to-create region selection.
- Preserved brightness, contrast, sharpening, and black-white scan tuning controls.

### Validation

- `npm.cmd run build` passed in the original feature run.

---

## 2026-07-03 - Chapter highlight background task behavior

- Fixed chat quick actions so background chapter-highlight generation no longer blocks unrelated chat workflows.
- Added duplicate-scope reuse and serial execution for chapter-highlight background jobs.
- Reduced extra LLM repair calls by preferring local LaTeX cleanup and validation before one optional formula repair pass.
- Reviewed other long-task paths: textbook import and external OCR import already run as background jobs; mistake OCR/solve, reports, and random practice remain local synchronous actions.

### Validation

- `npm.cmd run build` passed in the original feature run.
- Import checks for `ChapterHighlightService` and `HighlightJobStore` passed in the original feature run.

---

## 2026-07-02 - Study cockpit, book management, and highlight background tasks

- Added a richer chat home panel with current subject/textbook context, due-mistake review, weak-concept review, random exercise, highlight, report, and quick mistake capture actions.
- Added settings-center textbook management so imported books can have their subject corrected and can be set as the current chat book without renaming paths or touching indexes.
- Added `PATCH /api/books/{book_name}` for safe textbook metadata updates.
- Added chapter-highlight deletion for generated artifacts.
- Adjusted exercise Word/PDF import copy to clarify that low-confidence repair uses the text LLM backend by default.

### Validation

- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint` passed.
- `npm.cmd test` passed after rerunning outside the Windows sandbox EPERM.

---

## 2026-07-02 - Chapter highlight split and frontend lazy rendering

- Split `knowledge/chapter_highlights.py` into focused modules for source assembly, LLM generation, LaTeX validation/repair, artifact writing, shared types/constants, and background job management.
- Preserved public imports for `ChapterHighlightService`, `ChapterHighlightError`, `PROMPT_VERSION`, and `HighlightJobStore`.
- Lazy-loaded rich Markdown/KaTeX rendering through `MarkdownRenderer.tsx`.
- Added `useVisibleList()` and applied client-side pagination to long exercise and mistake lists.
- Extracted settings health polling into `useSystemHealth()`.

### Validation

- `./venv310/Scripts/python.exe -B -m pytest tests/test_generator.py tests/test_job_manager_and_roles.py -q` passed in the original feature run: `15 passed`.
- `./venv310/Scripts/python.exe -B -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-02 - Retrieval isolation and main workflow hardening

- Scoped new Chroma collections by `book_name + chapter_title`, with legacy chapter-only collections still readable as fallback.
- Rebuilt target scoped collections before writing new documents to prevent duplicates and stale chunks.
- Passed active `book_name` into planner, retrieval, chapter teaching, and mistake explanation RAG calls.
- Added safe vector-store adapters so Chroma failures degrade instead of breaking user-facing flows.
- Fixed chat quick mistake capture book loading, textbook import polling cleanup, external OCR output copy, and chat stop behavior.
- Lazy-loaded frontend route bundles.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_job_manager_and_roles.py tests/test_external_mineru_output_import.py tests/test_rag_degradation.py tests/test_chat_stream_reliability.py -q` passed in the original feature run: `13 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - External OCR output import path

- Added `import_textbook_from_mineru_output()` for workflows where MinerU runs on another machine and the desktop app only builds local chapters and Chroma indexes.
- Added `POST /api/books/import-mineru-output` for safe zip uploads with path traversal checks.
- Changed book listing/switching so externally imported books can appear and be selected without a local source PDF.
- Exposed `MINERU_API_URL` as the recommended external-service path and kept local MinerU CLI as advanced configuration.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_external_mineru_output_import.py -q` passed in the original feature run: `2 passed`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `55 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - Exercise import LLM repair and release lock

- Changed `memory/exercise_importer.py` to produce scored candidate splits before labeling.
- Added optional low-confidence LLM repair for uncertain exercise-import blocks while keeping the rule pipeline as the default.
- Added `split_confidence`, `split_reasons`, `refined_by_llm`, and `summary.llm_refined` to exercise analysis responses.
- Added `requirements-release.txt` as a release-only pinned backend/build dependency set.
- Updated the desktop backend build script to exclude legacy agents, OCR runtimes, and extra data-science/dev packages.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_exercise_importer.py tests/test_exercise_file_importer.py -q` passed in the original feature run: `5 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `53 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - Learning event log and packaging trim

- Added `memory/learning_events.py`, a SQLite append-only timeline for chat QA, concept exposure/candidates, mistakes, and exercise actions.
- Added `book_name`, `subject`, and `conversation_id` plumbing to concept exposure and chat graph state.
- Changed mistake and exercise APIs to write best-effort learning events for add/review/explain/practice/import/transfer actions.
- Trimmed the desktop PyInstaller build by excluding retired UI/dev packages.

### Validation

- Backend tests and frontend build passed in the original feature run.

---

## 2026-06-23 to 2026-06-30 - Historical compressed notes

The detailed historical notes for this period were damaged by mojibake before this cleanup. The reliable high-level record is:

- Added and iterated the exercise bank, including manual entry, Word/PDF import, rule-based candidate splitting, batch add, status updates, and mistake/exercise transfer flows.
- Added mistake image OCR/solve workflows, Kimi Vision OCR configuration, image preprocessing, and SM-2 review improvements.
- Hardened streaming chat, including SSE stage ordering, frontend accumulation safety under React StrictMode, long-answer rendering fallback, LaTeX sanitization, and ASGI error conversion.
- Improved retrieval with KG exact hits, vector fallback, role-aware retrieval, example completeness handling, and Chroma degradation.
- Added desktop packaging, first-run resource guidance, local asset status/download APIs, sample-data preparation, and data-safety tooling.
- Added chapter highlight generation, HTML artifacts, highlight reading page, chapter/section navigation, image support, LaTeX validation, and job-backed generation.
- Added project-level `AGENTS.md` conventions and moved durable architecture guidance out of patch notes.

### Validation

- Multiple historical runs of backend pytest and frontend production builds passed during those changes.
- Exact old command outputs are not reconstructed here because the source entries were encoding-damaged.

## 2026-07-04 OCR 教材向量索引导入

- 新增 `scripts/import_ocr_chunks.py`，用于将租卡 OCR 产物 `data/imports/kaoyan_ocr_20260704/deliverables/*_chunks.jsonl` 导入 Chroma。
- 已导入三本教材：`传感器短书` 562 chunks、`传感器长书` 943 chunks、`误差理论与数据处理` 511 chunks。
- `传感器短书` 与 `误差理论与数据处理` 标记为 `core`，`传感器长书` 标记为 `reference`，metadata 保留 `subject`、`book_role`、`rag_priority`、`review_status`、`source_markdown`。
- 因 `D:\AI\agent\kaoyan-assistant` 所在目录的 Windows 压缩/SQLite I/O 问题，Chroma 最终写入 `C:\tmp\chroma_smoke_test`，并在 `.env` 中设置 `VECTOR_DB_PATH=C:\tmp\chroma_smoke_test`。
- 验证：`get_vector_store()` 可加载 1589 个 collection；检索 `霍尔效应是什么` 能命中 `传感器短书` 中的定义 chunk。

## 2026-07-04 OCR 检索聚合索引优化

- 为三本 OCR 教材新增按书聚合 Chroma collection：`传感器短书`、`传感器长书`、`误差理论与数据处理` 各 1 个 aggregate collection，同时保留原有章节级 collection 供精确章节检索使用。
- `ChapterVectorStore.search_all()` 优先使用 book aggregate collection；无聚合索引时回退到旧的逐章节扫描。
- 启动预加载从全部章节 collection 改为只预加载 aggregate collection，避免 1500+ collection 冷启动开销。
- 最终 rerank 透传并使用 `book_role` / `rag_priority` metadata，使 `core` 教材优先于 `reference` 补充材料。
- 验证：`霍尔效应是什么` 在 `传感器短书` 内检索从约 40s 降至约 0.6s；跨书检索 `不确定度怎么合成` 扫描 3 个 aggregate collection，约 1.1s 返回 `误差理论与数据处理` 相关章节。


## 2026-07-04 OCR 教材 LLM 概念抽取与长书挂接

- 新增 scripts/extract_kg_candidates.py，支持对 OCR chunk 增量调用 DeepSeek V4 Pro 抽取 KG 候选，并过滤 thinking 内容，只落结构化 JSONL。
- 已对 传感器短书 与 误差理论与数据处理 的高价值语义块（definition/formula/theorem/derivation/example/exercise）完成主干概念抽取。
- 已按 传感器短书 高置信概念，将 传感器长书 高价值语义块挂接为 same_concept、expansion、proof、condition、edge_case、example_more、background 等关系。
- 产物位于 data/imports/kaoyan_ocr_20260704/deliverables/：kg_candidates_sensor_core.jsonl、kg_candidates_error_theory.jsonl、concept_links_sensor.jsonl、kg_review_queue.jsonl。
- 验证：传感器短书 165 chunk rows / 292 concepts；误差理论与数据处理 181 chunk rows / 228 concepts；传感器长书 364 links、32 no-match rows；低置信 review queue 49 rows。
## 2026-07-04 教材内习题抽取导入

- 新增教材抽题入口：`/api/exercises/textbook-analyze`，从已导入教材中按章节或页码范围提取候选题，并复用现有规则切题、低置信 LLM 修复和人工确认导入流程。
- 新增 `memory/textbook_exercise_importer.py`，抽取顺序为 chapter highlight `source_package.json`、MinerU `*_middle_chunks.json`、PDF 文本层；不修改现有教材索引、Chroma 向量库或题库结构。
- 前端习题库新增“从当前教材抽题”面板，支持章节/页码范围、习题页优先/章节例题/整页文本三种模式，候选题继续由用户勾选确认后入库。
- 验证：`python -m pytest tests/test_textbook_exercise_importer.py tests/test_exercise_importer.py -q` 通过；`npm run build` 通过；本地“优化设计”教材 page 50 可从 source_package 抽出候选题。

补充验证：已按 Electron 桌面端路径执行构建。`scripts/build-desktop-backend.ps1` 生成 `build/backend/backend_server/backend_server.exe`；`desktop/npm run dist` 生成 `release/win-unpacked` 与 `release/kaoyan-assistant-desktop-setup-0.1.0.exe`，内置 `frontend/dist` 时间戳已更新。

## 2026-07-04 教材问答概念与 OCR 抽题修复

- 修复流式问答 `done` 事件在 `feedback_node` 后台执行前就返回的问题，现在会把本轮 `linked_concepts` 同步写回 SSE state，避免非《优化设计》教材问答阶段前端拿不到概念链接。
- 教材抽题新增外部 OCR JSONL 读取路径，支持 `data/imports/.../*_chunks.jsonl` 产物；未找到 MinerU `middle_chunks` 时不再直接退化为“未提取到可切分文本”。
- Books API 对 `external_ocr_jsonl` 导入产生的“chunk 标题目录”做运行时目录折叠，从内嵌目录文本解析真实章节/小节，不改写现有 `_chapters.json` 数据文件。
- 前端习题库的教材抽题面板新增源 PDF/origin.pdf 预览入口，用户可先查看教材页，再输入起止页执行抽题。`r`n- 源 PDF 查找新增 `D:\OCR_NEEDED` 别名：`传感器短书 -> CGQ_1.pdf`、`传感器长书 -> CGQ_2.pdf`、`误差理论与数据处理 -> WC.pdf`，不复制原件。

### Validation

- `python -B -c "compile(...)"` 解析检查通过：`graph/main_graph.py`、`memory/textbook_exercise_importer.py`、`backend/api/books.py`。
- OCR 教材目录加载已折叠：`传感器短书` 13 章、`传感器长书` 12 章、`误差理论与数据处理` 7 章；外部 OCR 抽题路径返回 `external-ocr-jsonl` 文本。
- `npm.cmd run build` 通过。

## 2026-07-05 三本教材目录与桌面安装包打包

- 将 `Chapter.md` 中 Kimi 识别的目录写入三本教材：`传感器短书` 13 章、`传感器长书` 12 章、`误差理论与数据处理` 7 章；覆盖前保留 `_chapters.bak_chapter_md_*` 备份。
- 将 `D:\OCR_NEEDED\CGQ_1.pdf`、`CGQ_2.pdf`、`WC.pdf` 复制为 `data/books/传感器短书.pdf`、`传感器长书.pdf`、`误差理论与数据处理.pdf`，供桌面端 PDF 预览和 seed 数据使用。
- 新增错题/习题详情页删除入口，复用已有后端 DELETE API；删除后同步刷新列表、复习队列和统计状态。
- 构建了仅包含三本新教材的干净 Chroma 向量库与 `desktop/sample_data_three_books` seed 数据，不包含 `优化设计`。
- `scripts/build-desktop-backend.ps1` 增加 `-SampleDataDir` 参数，允许桌面后端构建显式指定 seed 数据目录。
- PyInstaller 输出中移除了本应用 CPU embedding 不需要的 CUDA/cuDNN DLL，使 NSIS 安装包避开 2GB mmap 限制；最终生成 `release/kaoyan-assistant-desktop-setup-0.1.0.exe`。

验证：

- `npm run build`：通过。
- `python -B` 编译检查 `backend/api/books.py`、`memory/textbook_exercise_importer.py`、`graph/main_graph.py`、`ingestion/pdf_parser.py`：通过。
- `scripts/build-desktop-backend.ps1 -SkipSampleDataPrepare -SampleDataDir desktop\sample_data_three_books`：通过。
- `npm run dist`：通过，生成 NSIS 安装包。
- release 内置 `sample_data` 抽查：6435 个文件，含三本 PDF，不含 `优化设计` 路径。
## 2026-07-11 教材 RAG 准确率 P0-P3 改造

### 原因与数据修复

- 定位“电容式传感器是否适合动态测量”只回答“质量轻”的根因：运行环境曾指向 `C:\tmp\chroma_smoke_test`，正式 `data/vector_db` 中没有《传感器长书》索引，模型实际依赖自身知识作答。
- 将运行时 `VECTOR_DB_PATH` 恢复为项目约定的 `./data/vector_db`；旧烟雾测试库保留，不执行删除。
- 为《传感器长书》在正式库中重建 12 个章节 collection、1359 个结构化 chunk；Dense 与 BM25 索引数量一致，健康检查通过。
- 本地 `torchvision` 与 `torch` 二进制不匹配会阻断 `sentence-transformers`。文本 Embedding 加载阶段现会隔离不需要的可选 `torchvision` 探测，不卸载或重装依赖。

### P0：索引完整性与安全降级

- 本地 PDF 导入现在也会构建教材索引，不再只解析章节而返回 `indexed_chunks=0`。
- 新增每本教材的 `collection_count`、`chunk_count`、`lexical_chunk_count`、`healthy` 健康统计，并在 Books API 列表中返回。
- 新增 `POST /api/books/{book_name}/reindex`，只重建派生检索资产，保留 PDF、OCR 原文、错题和学习记录。
- 教材存在但索引为空时返回 `book_index_empty`；教材模式无直接证据时强制拒答，不再静默使用模型参数知识补齐。

### P1：背诵准确模式与混合检索

- 新增 `factual_recall` 意图，用于原因、特点、优缺点、条件和并列要点等专业课背诵问题。
- 新增持久化本地 BM25 索引，采用 Dense Top 20 + BM25 Top 20 + RRF 融合；取消“第一个 role 有结果就停止”的硬过滤，role 改为软加权。
- 原 `_merge_and_rerank()` 的固定优先级排序改为问题相关的融合评分，保留 Dense/BM25/KG 来源、覆盖率和最终分数调试信息。
- 新增可选本地 Cross-Encoder 接口；设置 `RERANKER_MODEL_PATH` 后启用，未配置时使用确定性融合精排。
- 生成提示要求每个事实结论由选定教材证据支持；列表题必须穷尽证据中的并列项并附章节、小节、页码和 chunk_id。教材生成温度降为 0.1。
- 对年份、公式编号、英文缩写和数字参数增加精确字面证据约束，避免只有主题相似的段落冒充直接证据。

### P2：结构化切块与上下文补全

- 默认切块由 2000/100 字符调整为 700/80 字符，并优先按 Markdown 标题和自然段边界切分。
- chunk 新增 `section_path`、`parent_id`、`prev_chunk_id`、`next_chunk_id`、`parent_content` 和仅供检索使用的教材/章节前缀。
- Chroma 同时保存带上下文的 `retrieval_text` 与不带前缀的 `raw_content`；生成阶段使用原始教材正文。
- BM25 命中后支持相邻块扩展；公式、例题和列表可沿文档顺序补足上下文。

### P3：评测与回归

- 新增 `evaluation/rag_eval.py`，支持离线计算 Recall@K、MRR、要点完整率以及不可回答题拒答结果。
- 新增 `evaluation/datasets/textbook_recall.jsonl` 首批专业课背诵评测集，以及事实意图、RRF、切块关系、要点完整率和空索引拒答测试。
- 关键回归“电容式传感器是否适合动态测量”在正式库中排名 Top 1，Dense 与 BM25 双命中，同一证据完整包含“静电引力很小、质量很轻、介质损耗小”。
- 当前 10 题离线基线：Recall@10 为 80%，要点召回率为 83.3%；剩余薄弱项主要是完整特点块的标题排序和跨连续小节的列表聚合，作为后续调参基线保留。

### Validation

- `.\venv310\Scripts\python.exe -B -m pytest -q`：77 passed，3 warnings。
- `frontend/npm.cmd run build`：通过，Vite production build 成功。
- 正式《传感器长书》索引健康统计：12 collections / 1359 vector chunks / 1359 lexical chunks。
- 关键案例 Top 1 chunk：`3e87d09788d31566`，章节“第4章 力敏传感器”，融合来源 `dense + bm25`。

## 2026-07-11 传感器问答检索与展示修复

- 从保留的 OCR chunks 重建传感器短书索引：479 个章节 collection、562 个 chunk，并补建 562 条 BM25 索引；未改动长书索引、OCR 源和学习记录。
- 传感器问答改为分层联邦检索：短书为 core 主证据，长书作为 reference 补证；两库保持独立以保留来源追踪。
- 生成提示与前端双重隐藏内部 chunk ID；Markdown 不再保留源文本缩进空白，并折叠过量空行。
- 追问改写不再把所有短问题一律视为追问，只对显式指代词启用上下文；历史输入会清除内部索引号。
- 重建脚本复用项目文本嵌入加载器，规避不兼容 torchvision，并支持 KAOYAN_IMPORT_BOOKS 选择性重建。

验证：Python 语法检查通过；frontend npm run build 通过；短书 Chroma 与 BM25 计数见上。


## 2026-07-11 - P0/P1 evaluation, latency trace, and runtime convergence

- Extended the gold-set evaluator with expected chunk recall/MRR, forbidden-chunk detection, expected-page hits, and per-query retrieval latency.
- Added bounded SQLite RAG traces (last 500 requests) with request ID, fast-path flag, TTFT, total time, stage timings, and evidence metadata; answer text and model thinking are not stored.
- Added `GET /api/system/rag-traces`, trace database health, and LLM runtime-configuration health.
- Added request IDs and elapsed milliseconds to chat SSE events and replaced backend startup/chat `print` diagnostics with structured logging.
- Retired the obsolete Gradio web entry and removed Gradio from the development dependency list. Electron + React + FastAPI remains the supported product path; the root CLI is explicitly legacy.

### Validation

- `python -B -m pytest -q`: 79 passed, 1 dependency deprecation warning.
- `frontend/npm.cmd run build`: passed (TypeScript and Vite production build).
- `git diff --check`: passed.


## 2026-07-12 - 资料库目录统一（方案 B）

- 设置中心合并“教材管理”和“学科管理”为单一“资料库”入口，采用左侧学科/科目树与右侧教材内容区。
- 教材归属不再提供自由文本编辑入口；教材只能在已有目录间移动，未分类教材集中展示。
- 非空学科或科目禁止重命名和删除；后端保存目录前再次校验现有教材归属，避免产生孤儿分类。
- 本次仅更新学科目录与教材 subject 元数据的管理方式，不移动或改名 PDF，不修改章节数据，不删除或重建 Chroma 索引，不迁移学习记录。
- 验证：前端生产构建通过；前端 7 项测试通过；后端 87 项测试通过；当前教材归属只读检查结果为 `used_assignments=['专业课']`、`orphaned=[]`。

- 后续交互修正：每本教材增加“归属到”分组下拉框，可直接选择如“专业课 / 传感器”的二级科目；原有间接移动区已移除。


## 2026-07-12 - 章节重点查看、公式与断网续生成修复

- 桌面端打开重点改为在现有 React 路由内跳转，避免相对地址被 FastAPI 当作服务端路由并返回 404。
- 清理未解析的图片/公式索引，并移除会导致 KaTeX multiple tag 报错的公式编号、标签和引用命令。
- 生成任务按小节保存 generation_checkpoint.json；重新启动同一范围时复用已完成小节，成功后删除断点。前端轮询使用退避重连，连续失败后停止空转并恢复可重试状态。
- 提示词减少非必要逐行推导，增加背诵要点、教材证据支持的直观类比及章内对比联动，同时禁止无依据扩展和自拟题。
- 独立 highlight.html 定位为本机产物；应用内重点页使用打包的 KaTeX，本机离线可显示，直接发送 HTML 不作为可移植分享格式。

### Validation

- 重点相关后端测试：18 passed。
- 前端 TypeScript 与 Vite 生产构建通过。

- 桌面 release 数据支持在 sample_data/mineru_output 中携带 OCR 产物；首次启动时会复制到用户 mineru_output 目录，GitHub sample_data 仍可只保留单本演示教材。

## 2026-07-13 - 产品化 P0：1.0.0 发布、数据恢复与访问边界

### 发布治理

- 新增根 `VERSION`，统一前端、Electron、FastAPI 和设置页版本为 `1.0.0`。
- 新增版本设置/一致性检查脚本；桌面发布 tag 必须与 `VERSION` 一致。
- 新增 CI，发布前强制执行后端测试、前端测试、lint 和生产构建。
- Electron 发布工作流接入可选 Windows 代码签名 secrets；证书本身仍需由发布者提供。

### 数据安全

- 设置中心新增“备份恢复”：默认备份教材、章节、图片、错题、习题和学习记录，可选包含 Chroma 与 MinerU 派生数据。
- SQLite 使用在线 backup API 生成一致性副本；压缩包包含版本化 manifest、SHA-256 和展开安全限制，不包含 `.env` 或 API Key。
- 恢复前自动创建当前状态安全备份；恢复登记后在下次启动、向量库预热前执行目录替换，失败时自动回滚。
- Electron 新增安全重启 IPC，使桌面端可以完成“选择备份 → 安全快照 → 重启恢复”闭环。

### 安全边界

- Docker 默认端口映射收紧为 `127.0.0.1:8000`。
- 非本机 API 访问默认拒绝；配置 `KAOYAN_API_TOKEN` 后使用 `X-Kaoyan-Token` 认证，前端支持通过 URL fragment 一次性写入本地令牌。
- Electron 启用 renderer sandbox，并拦截窗口内外部导航，HTTP(S) 外链交给系统浏览器。

### Validation

- P0 定向测试：9 passed。
- 后端完整测试：99 passed，1 条第三方 TestClient 弃用警告。
- 前端测试：7 passed；ESLint：0 warning / 0 error。
- 前端 TypeScript 与 Vite 生产构建：通过。
- `scripts/check_version_consistency.py`：通过，版本与 lockfiles 均为 `1.0.0`；Electron Node 语法检查通过。


## 2026-07-14 - 习题导入校对工作台与连续练习会话 P0

### 导入校对与数据安全

- 习题候选新增切题边界、选项完整性、题干长度、知识点缺失和题库重复检测；重复检测一次构建题干指纹映射，避免按候选题重复扫描题库。
- 习题页保留完整导入原文作为对照，候选题支持异常/重复筛选、题干/答案/解析/题型/难度/标签/来源/章节编辑、选中合并和按空行拆分。
- 批量导入改为单个 SQLite 事务，记录 `exercise_import_batches` 批次；默认跳过题库已有题和同批重复题，导入完成后可按批次回滚。
- Word/PDF 文件导入支持可选的独立答案文件；仅按明确题号确定性配对，未匹配候选会标记异常，不使用 LLM 猜测答案。
- 新表为兼容性增量创建，不改写现有 `exercises`、错题、教材、Chroma 或学习记录。

### 连续练习会话

- 新增持久化 `exercise_practice_sessions`：固定题目队列、筛选条件、随机种子、当前进度、逐题答案、自评结果、错题关联和完成摘要。
- 习题页支持设置题数、优先复习/随机顺序、自动下一题、暂停、恢复、结束和重启后继续未完成会话。
- “做错”会在记录本题练习结果的同时转入错题本；暂停状态禁止提交，服务端校验提交题目必须与当前会话进度一致。
- 随机模式只打乱按“需复习 → 练习中 → 新题 → 已掌握”选出的优先题池，不会把已掌握题随机混入有限题量。

### Validation

- 后端完整测试：105 passed，1 条第三方 TestClient 弃用警告。
- 前端 Vitest：9 passed。
- ESLint：通过，0 error。
- 前端 TypeScript 与 Vite 生产构建：通过。
- `git diff --check`：通过。

## 2026-07-15 - Electron 学习工作台视觉收敛

### 交互与视觉层级

- 移除全局主按钮胶囊化规则，统一桌面端按钮、导航、输入框和容器圆角，主色只用于当前状态与关键操作。
- 对话首页改为“优先复习 + 其他入口”的任务列表，去除问候语、装饰性 AI 图标和重复推荐卡；空白对话不再重复显示底部快捷工具栏。
- 习题页拆分为“练习 / 题库 / 导入”三个工作区，避免练习、检索、文件导入和候选校对同时堆在同一屏；导入空状态补充确定性流程说明。
- 教材导入页缩短上传区，补充导入目标说明，并将 MinerU 选项改写为面向结果的“扫描件必须完成高质量解析”。
- 学习情况、错题本补充页面说明；知识增强改为“完善知识关联”；错题空状态增加明确的录入入口，并强调 OCR 后人工校对。

### Validation

- 前端 TypeScript 与 Vite 生产构建：通过。
- Electron 开发模式实机检查：对话、学习情况、错题本、习题练习、题库、习题导入、教材导入和设置窗口均可打开；分段切换、导航和空状态无明显溢出。
## 2026-07-15 - 录入流程、教材导入与设置页结构化

### 工作流重构

- 错题录入拆分为“添加题目、校对内容、归因保存”三个阶段；图片 OCR 与看图讲解均先进入可编辑校对步骤，手动录入不再依赖图片或自动讲解。
- 归档步骤始终允许补充来源、学科、章节、标签、难度与错因；保存成功、识别失败和处理中状态使用统一反馈样式。
- 教材导入改为“PDF 教材”和“MinerU 输出包”二选一，避免两套参数与操作同时堆叠；PDF 参数顺序与后端请求保持不变。
- 设置从全局浮层迁移到 `/settings` 独立页面，并加入主导航；服务器健康、版本更新、备份恢复、资料库和模型配置功能保持不变。

### 状态系统

- 新增 `AsyncState` 组件族，统一页面加载骨架、空状态、错误/成功提示和带进度后台任务。
- 教材导入、学习情况、错题录入和设置页已接入统一状态组件。
- 系统健康组件由重复卡片改为可扫描列表，并补全“检索记录”“模型连接”等中文标签及运行状态文案。

### Validation

- 前端 Vitest：9 passed。
- ESLint：通过。
- TypeScript 与 Vite 生产构建：通过。
- `git diff --check`：通过。
- Electron 实机检查：错题添加与手动校对、PDF/MinerU 方式切换、独立设置页及健康状态加载正常。

## 2026-07-15 - 学习情况页去卡片化与页面标题收敛

### 视觉层级

- 学习情况页将四张指标卡合并为单一统计带，只用网格分隔线区分指标，不再为每个数字单独添加圆角容器。
- 待复习错题、今日概念复习和待复习概念合并为连续折叠分组；概念、错题与空状态改用行级留白和稀疏分隔线，移除卡片套卡片结构。
- 高频概念、错题薄弱点和最近每日活动合并为同一分析区；活动详情、教材线索和错题预览使用轻背景层级，不再重复叠加边框与圆角。
- 后台任务状态由双层面板改为单层状态区，保留错误、进度和无障碍语义。

### 页面标题

- 移除学习对话、学习情况、错题本、习题工作区、教材导入和设置标题下方的泛化说明句。
- 顶部页面标题统一为 19px/600 字重；正文中的操作说明、错误信息和真实来源元数据不受影响。

### Validation

- 前端 TypeScript 与 Vite 生产构建：通过。
- ESLint：通过，0 error。
- 前端 Vitest：9 passed。
- 定向 `git diff --check`：通过；相关页面未新增 em dash 字符。
- Electron 窗口视觉检查授权超时，未取得实机截图；应用内浏览器访问本地地址被客户端安全策略阻止，未绕过限制。

## 2026-07-16 - 一级页面标题栏位置统一

### 界面一致性

- 新增共享的 app-page-header 与 app-page-title 规则，统一一级页面标题栏为 64px 最小高度、20px 水平内边距、19px/600 标题和垂直居中。
- 学习对话、学习情况、错题本、习题工作区、教材导入和设置全部迁移到共享规则；移除教材导入与设置标题的居中内容容器。
- Electron 无边框窗口统一为所有一级标题栏预留右上角窗口控件安全区，并保持标题栏内按钮可交互；紧凑布局继续使用相同的 20px 水平基线。

### Validation

- ESLint：通过。
- 前端 Vitest：3 files / 9 tests passed。
- TypeScript 与 Vite 生产构建：通过。
- 应用内浏览器 1280px 桌面视口实测：六个标题栏均为 64px 高，标题左偏移 20px、顶部偏移 19.6px、文字高度 24px。


## 2026-07-18 - 备份恢复安全与练习会话原子性修复

### 备份与恢复

- SQLite 备份仅接受 `sqlite3.backup()` 生成且 `PRAGMA quick_check` 通过的快照；数据库锁定或备份失败时不再退化为缺少 WAL 的主文件拷贝。
- 恢复前始终创建包含向量库和 MinerU 产物的完整安全备份；目标备份未包含的派生数据在恢复时会被失效，避免旧学习数据与新索引混用。
- 待恢复压缩包缺失、pending JSON 异常或安装失败时，记录失败与回滚结果并消费 pending 请求，不再阻塞每次后端启动。
- 恢复后若向量索引已失效，设置页会明确提示重新索引教材。

### 练习会话

- 习题练习记录与会话进度改为同一 SQLite `BEGIN IMMEDIATE` 事务，任一写入失败时整体回滚。
- 重复提交已作答题目时直接返回持久化结果，不再重复增加练习次数。
- 练习会话转入错题本使用稳定错题 ID 和幂等写入；跨数据库写入中断后可安全重试，不会生成重复错题。

### Validation

- 后端完整测试：126 passed，1 条第三方 TestClient 弃用警告。
- 新增回归覆盖 SQLite 备份失败、缺失恢复包、派生索引失效、练习事务回滚和重试幂等。
- ESLint 通过；TypeScript 与 Vite 生产构建通过。

## 2026-07-18 - Learning-state concurrency, local API boundary, and upload limits

### Learning-state consistency

- Added path-scoped re-entrant locks shared by all ConceptMemory, StudyMemory, and SpacedRepetition instances.
- Every read/modify/write operation reloads the latest JSON snapshot while holding the shared lock, preventing background feedback and concurrent API requests from overwriting each other.
- Kept the existing JSON storage format; no user-data migration is required.
- Added multi-instance concurrency regression tests for concept exposures, chat history, and SM-2 cards.

### Local API boundary

- Electron now creates a random 256-bit API token for each launch, requires it in the backend, and bootstraps it into the renderer through a URL fragment that the frontend immediately removes.
- Valid tokens are accepted before the loopback development fallback; packaged desktop requests therefore remain authenticated.
- Development mode rejects unsafe local API requests carrying an untrusted Origin, while trusted Vite origins and non-browser CLI clients remain supported.
- Upload endpoints reject oversized multipart requests from Content-Length before Starlette parses or spools the body.

### Upload and archive limits

- PDF, DOCX, and external MinerU ZIP uploads now use bounded streaming copies, exclusive destination creation, partial-file cleanup, and a minimum free-disk reserve.
- ZIP and DOCX inspection now limits file count, per-member size, total expanded bytes, and compression ratio, and rejects encrypted members, symbolic links, and unsafe paths.
- Failed external-output extraction removes its job-specific partial directory.
- Default limits are configurable through KAOYAN_MAX_* and KAOYAN_MIN_FREE_DISK_BYTES environment variables.

### Validation

- Backend: 137 passed; one existing Starlette TestClient deprecation warning.
- Frontend: 3 files / 9 tests passed; ESLint passed; TypeScript and Vite production build passed.
- Electron main-process syntax and changed Python source syntax passed.
- git diff --check passed (line-ending warnings only).
## 2026-07-18 - 开源发布材料与桌面入口实测

### 项目审计与展示材料

- 基于实际目录、入口、API、持久化和调用链新增 PROJECT_AUDIT.md，并重写根 README。
- 新增 docs/images 下六张 1440 × 900 实机截图，覆盖工作台、资料库、教材问答会话、习题、错题和学习情况。
- 新增无构建工具的 site/ 静态项目页，包含响应式布局、系统明暗模式、真实截图、功能边界与 Roadmap。
- 新增 scripts/seed_docs_demo.py，用稳定 ID 向显式隔离目录写入非个人展示数据，并拒绝正式 data/ 与 desktop/sample_data。

### Electron

- 修复 desktop/main.cjs 中 desktopAppUrl 被错误定义在 loadAppUrl 内部的问题。
- 修复前 Electron 窗口停留在未进入应用的状态；移动为模块级函数后，dev:existing 已进入真实 React 应用并显示首次使用引导。

### Validation

- Python 3.10.11；后端完整测试 137 passed，1 条既有弃用警告。
- 前端 Vitest 3 files / 9 passed；ESLint 和 TypeScript/Vite 生产构建通过。
- FastAPI 隔离实例 health 返回 200；Electron dev:existing 实机进入应用。
- 浏览器自动化在 1440 × 900 和 390 × 844 下通过；主要页面与静态宣传页无控制台错误。
- README 六张图片、site 本地资源和页内锚点均存在；六张 PNG 均为 1440 × 900。
- demo seed 直接运行、幂等运行和受保护路径拒绝均通过。
- 未调用真实付费 LLM、OCR、MinerU，没有构建 Docker、PyInstaller 或 NSIS 产物。
## 2026-07-18 - 静态宣传页截图与配色调整

### 展示体验

- 将截图从 Hero 和功能文本卡中移除，统一放入独立截图资源区。
- 六张缩略图使用固定 16:10 容器，点击后通过原生 dialog 按原始比例展开。
- 功能区保留三个文本入口，可直接打开对应截图；灯箱支持关闭按钮、Escape、点击背景关闭和焦点恢复。
- 页面配色从绿色倾向调整为冷白、灰蓝和单一钴蓝强调色；暗色模式改为中性石墨与海军蓝，不再使用深绿色 token。

### Validation

- 桌面 1440 × 900 与移动 390 × 844 均无横向溢出。
- 6 个截图卡、9 个预览入口和 6 个唯一截图资源均通过检查。
- 所有截图容器比例均为 1.6，灯箱图片成功加载为 1440 × 900。
- 移动导航、灯箱打开/关闭、焦点恢复和控制台检查通过。
- site 本地资源无缺失，JavaScript 语法通过，页面可见文案不含 em dash。
## 2026-07-18 - GitHub Pages 发布

### Deployment

- 新增 `.github/workflows/pages.yml`，从 `site/` 打包并部署静态项目页。
- 仓库 Pages 发布源已切换为 GitHub Actions，并启用默认域名 HTTPS。
- Pages 工作流使用 `actions/checkout@v6`、`actions/configure-pages@v6`、`actions/upload-pages-artifact@v4` 与 `actions/deploy-pages@v4`。
- 公开地址为 `https://jayceto946-byte.github.io/kaoyan-assistant/`。

### Validation

- GitHub Actions `Deploy Project Site` 第二次运行成功，耗时 17 秒。
- 公开页面标题、样式表、6 张截图与 9 个预览入口加载正常。
- 1440 × 900 截图灯箱在公开站点实测可打开，浏览器控制台无错误。

## 2026-07-18 - 隐藏教材默认范围修复

### Fix

- 教材隐藏后若仍是当前对话范围，前端在教材列表刷新完成后会清除该失效选择。
- 切换学科时会同时清除已隐藏或已移除的教材，不再保留陈旧的教材名称。
- 学科没有匹配教材时保持通用问答，不再回退到全局第一本教材。

### Validation

- `npm.cmd test -- textbookScopes.test.ts`：4 项测试全部通过，覆盖父/子科目匹配和无关科目不得回退。
- `npm.cmd run build`：TypeScript 检查与 Vite 生产构建通过。

## 2026-07-18 - Electron 原生窗口控制与折叠侧栏对齐

### Fix

- 放弃容易被拖拽命中区吞掉点击事件的 React 自绘窗口按钮，改用 Electron `titleBarStyle: hidden` 与 Windows/Linux 原生 `titleBarOverlay`。
- 保留页面标题区域的 drag/no-drag 划分，并为原生窗口按钮预留安全间距。
- 折叠侧栏 rail 补充全高约束，避免折叠后导航内容按自身高度向顶部收缩。
- 左右桌面标题栏统一为不可收缩的 64px 高度，避免窗口变矮时左侧品牌栏被 flex 压缩而导致分隔线错位。

### Validation

- `desktop/main.cjs` 与 `desktop/preload.cjs` Node 语法检查通过。
- 前端 TypeScript 与生产构建通过。

## 2026-07-24 - 解耦分支复审修复

### Fix

- `BookReadCache` 在缓存存取边界使用防御性复制，避免调用方修改 JSON 或索引统计后污染后续请求；小型元数据文件增加内容指纹，可靠识别 Windows 同尺寸快速覆盖，同时避免大型章节文件每次重读全文。
- KG 复习计划增加概念名稳定排序兜底，并兼容有/无时区时间相减。
- KG 错题关联改为一次构建“显式概念 -> 错题摘要”和“规范化题干 -> 错题 ID”索引，不再用短概念或问题子串扫描全文，减少误命中和重复遍历。
- 删除 books API 中无语义的一行转发函数，移除未使用的参数和导入，直接调用章节纯函数。
- 错题图片服务改为模块级单实例，路由直接调用其生命周期方法，不再逐次重建相同服务或保留私有转发层。
- 图片大小错误信息从 `max_image_bytes` 动态生成；Pillow 缺失或图片无法解码时记录降级原因，其他优化异常记录堆栈并向上抛出。
- `/mistakes/recognize-image` 的失败文案改为 OCR 识别失败，不再误报为讲解失败。

### Validation

- `python -m pytest -q tests/test_book_read_cache.py tests/test_kg_learning_summary_service.py tests/test_mistake_image_lifecycle.py`：16 passed。
- 覆盖缓存结果隔离、同尺寸覆盖、KG 稳定排序、时区兼容、短概念误匹配、题干子串误匹配、图片路径约束、失败清理、动态大小提示和意外优化异常向上抛出。
- 完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - 解耦复审第二批边界整理

### Backend

- `ExercisePracticeService` 移除 `Any`、请求 DTO、响应字典和序列化回调，改为明确的 `ExerciseBank`、`MistakeBook`、`ExerciseRecord`、`PracticeSession` 类型。
- 新增 `PracticeAnswerResult`，由应用服务表达作答、稳定错题 ID 和可重试的错题写入失败；FastAPI Router 独立负责 Pydantic 序列化、成功/失败响应和用户文案。
- 作答已经持久化但错题写入失败时，仍记录一次正常练习事件；重试继续复用稳定错题 ID，不重复作答。

### Frontend

- 新增 `useExerciseAnswerJob`，集中管理标准答案任务恢复、轮询、失败终止、草稿编辑和保存。
- 新增 `useExerciseImportCandidates`，集中管理候选题筛选、选择、编辑、合并、拆分和摘要统计；所有跨状态更新均位于事件处理流程，不在 React state updater 中产生副作用。
- `ExercisesPage` 从 909 行降至 820 行，删除重复工作流实现，没有继续抽取纯样式叶子组件。

### Validation

- 后端练习与 overview 针对性测试：12 passed；完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - 解耦复审第三批工作流拆分

### Review corrections

- 复审发现原 `ExercisePracticeService` 仍包含四个只转发到 `ExerciseBank` 的方法；移除这些方法并收窄为只承载幂等作答、错题写入和学习事件协调的 `PracticeAnswerService`，会话查询与状态切换由 Router 直接调用题库。
- 候选题 hook 不再向页面暴露原始 `setCandidates` / `setSelectedIds`，改为替换候选、移除已选、全选和清空选择等语义操作。
- 候选题合并、拆分、筛选和摘要提取为纯操作并增加测试；合并现在真正校验所选题目相邻，避免界面提示与行为不一致。
- 答案任务创建未返回任务 ID、轮询返回失败或缺少任务数据时会结束 busy 状态并给出明确提示，不再无限等待。

### Workflow split

- 新增 `usePracticeSession`，集中连续练习启动、暂停、恢复、作答、转入错题本、当前题选择和本地状态同步；`ExercisesPage` 进一步降至约 716 行。
- 新增 `useMistakeReview`，集中到期复习展开状态、评分提交、记录同步以及到期列表和统计刷新。
- 保留 `_bank()` / `_mb()` 配置入口：它们统一绑定教材范围和 `PROGRESS_PATH`，不是纯改名转发。
- 暂不把截图裁剪强行抽成综合 hook；该流程仍与 DOM ref、Canvas 和裁剪弹窗紧密耦合，待先拆出稳定的图片处理状态模型后再迁移。

### Validation

- 前端 ESLint 通过。
- 前端 Vitest：5 个测试文件、18 项测试通过。
- 前端 TypeScript 检查与 Vite 生产构建通过。
- 后端练习与 overview 针对性测试：12 passed。
- 完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - RAG EvidencePack 与问答时序优化

### RAG generation

- 将生成阶段重复注入的 `chapter_contents`、`evidence_items` 和 `concept_results` 收敛为单一 `EvidencePack`；按 `chunk_id` 与规范化正文去重，并使用 9000 字符总预算和 1800 字符单段上限。
- `EvidencePack` 保持为显式接收 `evidence_items`、`chapter_contents`、`intent` 的纯函数，不直接依赖完整 GraphState、环境变量、索引或存储，避免破坏现有检索与解耦边界。
- 证据数量限制按意图区分：普通定义保持同章最多 2 段；公式/性质最多 3 段；推导、应用、教学等最多 4 段；事实背诵允许保留检索层同章最多 6 段，避免漏掉并列要点。旧索引缺少 `evidence_items` 时仍从 `chapter_contents` 降级。
- 检索调试项和最终证据继续分离；仅补齐 `book_name`、语义角色和命中来源等既有元数据。引用标签优先使用真实教材名，未知页码不再显示 `p.?`，未改动检索排序、证据门禁、向量库或知识图谱格式。

### Runtime

- 复用相同不可变配置下的 LangChain/OpenAI/Ollama 客户端，保留 DeepSeek V4 Pro、thinking 与温度配置，不引入 Planner 模型降级。
- 修正 SSE 阶段计时归属，分别记录 context、plan、retrieve、chapter、generate TTFT、generate total 和 total；仅增加事件观测字段，不改变事件顺序和正文累积协议。

### Benchmark

- 固定问题“什么是电容式传感器”和同一检索结果的隔离生成测试中，Prompt 从 6782 字符降至 4419 字符（-34.8%）；3 次中位 TTFT 从 23220.97 ms 降至 10169.70 ms（-56.2%），生成总时长从 27500.96 ms 降至 14664.82 ms（-46.7%）。
- 完整链路前后各仅 1 次，改动后总时长高 11.2%；该结果包含 Planner 和外部模型波动，样本不足，不能宣称完整链路稳定提速。前后答案及原始计时保存在 `benchmark_results/`。

### Validation

- EvidencePack、生成、通用教材资源组、检索降级与 SSE 定向回归：29 passed。
- 完整后端测试：201 passed，1 条既有 Starlette/httpx2 弃用警告。
- 前端 TypeScript 与 Vite 生产构建通过；Electron `main.cjs`、`preload.cjs` Node 语法检查通过。
- `git diff --check` 通过。`compileall` 因现有 `__pycache__` 目录权限无法写入而未作为验证依据；完整 pytest 已成功导入并执行相关 Python 模块。

## 2026-07-24 - 解耦分支功能契约修复

### Compatibility and fault isolation

- KG 概念复习优先使用 `linked_concepts` 与标签精确关联；某概念没有显式命中时，再从旧错题的题干、OCR 与解析文本做兼容包含匹配。单字符概念不进入全文兜底，最近题目关联还要求最短四字符且长度比例不低于 0.75，避免短片段误命中。
- `PracticeAnswerService` 改为接收 `MistakeBook` provider；仅在 `add_to_mistake=True` 且尚无稳定错题 ID 时初始化错题库，普通作答不再受错题数据库权限或损坏影响。
- 习题与错题 overview 保留主体列表，将统计、活动会话和到期复习队列作为隔离的可选部分；辅助模块失败时返回局部数据及 `errors` 字段。

### RAG quality contract

- EvidencePack 继续保留 9000 字符总预算与单条 1800 字符上限，同时为定义、列举、比较、普通原理问答、推导、应用题和跨章节问题设置显式的每章证据覆盖基线。
- 新增确定性多题型回归测试；它验证证据覆盖边界，不调用付费 LLM，也不把单次模型延迟当作答案质量结论。

### Validation

- 针对性后端测试：41 passed，覆盖五类 KG 关联来源、短概念防误匹配、惰性错题依赖、overview 局部失败和 EvidencePack 多题型矩阵。
- 完整后端测试：218 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- Electron `main.cjs`、`preload.cjs` Node 语法检查通过；版本一致性检查通过。
- 当前 CI 已配置 `pull_request` 触发；合并前仍需让当前真实 HEAD 通过远端完整 CI。未调用真实付费 LLM、OCR 或 MinerU。

## 2026-07-24 - 本地 API 卡片请求 Origin 分类修复

### Fix

- 本地 API 安全边界不再只按 HTTP 方法判断写操作；`/exercises/list`、`/exercises/overview`、`/mistakes/list`、`/mistakes/overview` 虽使用 POST 传递筛选条件，但按只读请求处理。
- “按薄弱点抽题”和“随机抽一道题”不再因只读 `/exercises/list` 被误报 `UNTRUSTED_ORIGIN`；习题库 overview、错题列表和错题 overview 同步恢复。
- 将后端自身提供的本地 UI Origin `http://localhost:8000` 与 `http://127.0.0.1:8000` 加入明确白名单。Electron 仍优先使用每次启动生成的 API token。
- 真正写入或产生外部成本的卡片操作仍受保护，包括错题速录保存、练习提交、复习评分、教材重点生成、设置修改和数据恢复；未知 Web Origin 不能借只读豁免调用这些接口。

### Card audit

- 到期错题复习、概念复习是前端本地卡片；学习日报/周报和教材重点读取使用 GET，不受此次误分类影响。
- 教材重点生成、错题图片识别与保存、题目作答等写入型操作统一通过带桌面 token 的 API client；本地 8000 UI 可正常使用，其他来源仍需显式配置可信 Origin 或有效 token。

### Validation

- 安全边界定向测试：12 passed；覆盖未知 Origin 只读 POST 放行、真实写请求继续拒绝、尾斜杠归一化、本地 5173/3000/8000 Origin 和桌面 token。
- 相关 API 定向测试：28 passed。
- 完整后端测试：220 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- Electron `main.cjs`、`preload.cjs` Node 语法检查通过；`git diff --check` 通过。
## 2026-07-24 - 章节重点任务终态与卡片停止状态修复

### Fix

- 章节重点生成失败或取消时，同时把 SQLite 后台任务和对应 `metadata.json` 写入 `failed` / `cancelled` 终态；即使元数据写入本身失败，任务表也会结束，不再永久保留 `running`。
- 章节重点列表会按同范围最新任务修复后端重启造成的陈旧 `running` 元数据；只修复已有的临时状态，不复活用户已删除的重点记录，也不覆盖较新的成功产物。
- 前端轮询收到 `completed`、`failed`、`cancelled` 或 `interrupted` 后统一清理活动任务并刷新章节状态；启动缺少任务 ID、连续网络失败也会解除本地“生成中”。
- 章节重点卡片新增“终止生成”，复用持久化任务取消接口；任务完成改用原子完成操作，取消与完成并发时由取消状态优先。

### Adjacent card audit

- 教材导入卡片现在把 `cancelled`、`interrupted` 作为终态，停止轮询、解除按钮禁用并显示错误态。
- 学习页知识关联卡片在 `cancelling` 时保持禁用并显示终止中；`cancelled`、`interrupted` 不再继续显示加载态。
- 习题标准答案任务原有轮询已完整处理 `failed`、`cancelled`、`interrupted`，无需修改。

### Validation

- 章节重点任务定向回归：10 passed，覆盖失败元数据落盘、重启中断修复、工作线程失败和取消前置检查。
- 完整后端测试：223 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- `git diff --check` 通过。

## 2026-07-27 - 问答数学符号辅助输入第一版

### Frontend

- 问答输入区新增数学符号面板，按常用、微积分、线性代数和希腊字母分组提供 48 个 LaTeX 符号与公式模板；复用现有 Markdown + KaTeX 消息格式，不修改后端请求协议、数据库或模型调用链。
- 模板按当前光标位置插入；选中文字后可直接套用分数、根式、函数、向量等结构，插入完成后恢复输入焦点并选中下一处待填写内容。
- 面板支持当前输入预览、点击外部关闭和 Escape 关闭；2×2、3×3 矩阵使用独占行块级定界符。紧凑布局下对面板内部按钮做局部尺寸隔离，并验证 390px 移动视口无横向溢出。

### Validation

- 前端 Vitest：7 files / 25 tests passed，覆盖光标插入、选区套用、占位定位、矩阵块定界符和模板标记清理。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地实际界面验证通过：桌面 1280×720 下分数插入、KaTeX 预览和矩阵渲染正常；390×844 紧凑布局下面板边界、分类标签和模板点击区域正常。
- 未新增第三方依赖，未调用真实 LLM、OCR 或教材索引。

## 2026-07-27 - 问答可视化公式编辑与矩阵输入

### Frontend

- 将第一版的“把 LaTeX 源码直接插入 textarea”调整为“自然语言输入 + 可视化公式卡片”。公式在 MathLive 编辑器中按排版结果填写，保存后以 KaTeX 卡片展示，可再次编辑或删除；发送时再统一组合为 Markdown + LaTeX，后端接口和 LLM 输入约定保持不变。
- 48 个原有模板不再暴露占位源码，点击后进入带灰色占位框的公式编辑器；占位未填写时禁止保存，并可选择行内公式或独立公式。
- 新增矩阵构造器：支持 1–5 行、1–5 列，方括号、圆括号、行列式和无括号四种外框；逐格输入并实时预览，所有格子填写后生成标准矩阵 LaTeX。
- 移除已被替代的旧版原始 LaTeX 弹层与输入预览组件，保留模板数据和纯转换测试。

### Dependency and performance

- 新增 `mathlive@0.110.0`，仅用于前端可视化公式编辑；MathLive 使用动态导入，并在 Vite 中拆分为独立 `vendor-mathlive` 资源，避免混入通用 vendor 首屏包。
- 不修改数据库、后端 API、RAG、错题或教材索引格式；本次依赖变化只影响前端安装与构建产物。

### Validation

- 前端 Vitest：10 files / 33 tests passed，新增覆盖文字与公式组合、模板占位转换、矩阵缩放、矩阵序列化和空格校验。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地实际界面验证通过：桌面端完成分数可视化编辑、2×2 矩阵逐格填写、实时预览、公式卡片添加及二次编辑；390×844 紧凑布局下模板面板可用且无页面级横向溢出。
- 未调用真实 LLM、OCR 或教材索引。

## 2026-07-27 - 公式快捷键与输入法页面位移修复

### Frontend

- 可视化公式编辑器下方新增单行快捷键，包含平方、立方、0–9、x/y/z、加减等号与圆括号；快捷键保持公式框当前选择，不会因为按钮获得焦点而丢失输入位置。
- 模板载入后显式定位到第一个公式占位框，快捷键通过 MathLive 的键盘输入命令填写，避免第一次点击数字时覆盖整条公式。
- 禁用 MathLive 在输入、组合输入和光标变更时对宿主节点执行 `scrollIntoView()`；程序化聚焦使用 `preventScroll`，并在焦点事件后恢复页面滚动位置。
- Electron 桌面布局改用稳定的 `100vh` 工作区高度，不再随输入法造成的动态可视视口变化压缩主页面；紧凑移动布局仍保留动态视口适配。

### Validation

- 前端 Vitest：11 files / 35 tests passed，新增快捷键唯一性以及平方、立方命令测试。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地界面实测：极限模板载入后，数字快捷键只填写当前占位框且保留 `lim` 结构；变量后添加平方正常；连续聚焦和快捷输入前后 `scrollY=0`、应用顶边为 0、应用高度与视口高度均保持 720px。

## 2026-07-27 - 问答框公式附件

### Frontend

- 可视化编辑完成后的操作统一为“插入问答框”，插入成功即关闭公式面板；公式在问答框内部以“公式 1”“公式 2”等编号附件显示，并保留预览、编辑和删除操作。
- 自然语言与公式附件共用一个输入容器，避免用户直接修改 LaTeX 源码；发送时按照界面编号组合为 Markdown + LaTeX，LLM 仍收到完整、结构化的数学表达式。
- 本版未引入富文本 `contenteditable` 或拖拽排序，避免扩大输入法、光标定位和无障碍交互的风险；多公式按插入顺序稳定编号。

### Validation

- 前端 Vitest：11 files / 35 tests passed；ESLint 与 Vite 生产构建通过。
- 本地界面实测：连续插入无穷符号和希腊字母后，问答框内正确显示“公式 1”“公式 2”，面板自动关闭，编辑、删除与发送入口可用。

## 2026-07-28 - Conservative subject-routing correction for chat

### Backend

- Chat requests and persisted messages now share a stable `turn_id`; persisted messages also receive a stable message `id`. Existing conversation files remain readable without migration.
- Added a conservative subject router that combines the configured subject catalog, explicit subject/course terms, textbook metadata and local BM25 evidence. A suggestion is emitted only when its score and lead over the runner-up pass feedback-adjusted thresholds.
- Subject-routing failures are isolated from the main answer path. A failed classifier or local index read does not turn a successful answer into an SSE error.
- Added conversation scope APIs for relabeling a whole conversation and for moving one identified turn into a new conversation. Both preserve message bodies and record scope history; mistake records, learning events and RAG traces are intentionally not rewritten.
- Accepted and dismissed suggestions are counted per source/target route. Repeated acceptance can slightly lower the threshold, while repeated dismissal raises it.

### Frontend

- Assistant answers can show an actionable subject suggestion card with confidence and evidence.
- The card supports moving only the current turn, relabeling the whole conversation, or dismissing the suggestion. Moving one turn opens the newly created conversation under the corrected subject/book scope.
- Conversation history restores stable message and turn identifiers, and chat rendering uses stable keys when available.

### Validation

- Targeted backend regression: 9 tests passed, covering routing, current-scope suppression, feedback persistence, concurrent conversation writes, whole-conversation relabeling, turn splitting, and SSE persistence failure isolation.
- Full backend regression: 228 tests passed with one existing Starlette/httpx2 deprecation warning.
- Frontend validation passed: 11 Vitest files / 35 tests, ESLint, TypeScript, and the Vite production build.
- No database schema, textbook index format, mistake record, learning-event record, or RAG-trace migration was introduced.

## 2026-07-28 - Stable formula references in the chat composer

### Frontend

- Replaced the clipped textarea focus shadow beneath formula attachments with the existing outer composer focus border, and added a quiet `surface-subtle` background to separate the formula layer from the question text.
- Formula labels are now actionable: clicking `公式1`, `公式2`, and so on inserts that exact compact reference at the current question cursor or replaces the current selection.
- Formula reference numbers remain stable after deletion, so removing `公式1` does not silently rename an existing `公式2`. Newly attached formulas continue from the highest remaining reference number.
- Outgoing questions include an explicit reference registry mapping each compact label to its LaTeX expression, making phrases such as “比较公式1和公式2” deterministic for the answer generator.
- No backend API, database, textbook index, mistake record, learning event, or RAG trace was changed.

### Validation

- Frontend Vitest: 12 files / 38 tests passed, including cursor insertion, selection replacement, stable numbering after deletion, formula-only questions, and explicit reference serialization.
- Frontend ESLint, TypeScript checks, and the Vite production build passed.
- The existing MathLive chunk-size warning remains unchanged and does not block the build.

## 2026-07-29 - Cross-subject routing preflight correction

### Backend

- Fixed subject ranking so a parent subject and its matching child route reinforce the same classification instead of incorrectly competing for the minimum lead. The reported sensor-to-English-writing question now resolves to the English/Writing scope with a high-confidence suggestion.
- Subject routing now runs before the graph. When a confident cross-subject suggestion exists, the turn uses ordinary QA generation and does not retrieve from the currently selected, known-wrong textbook.
- Streaming and non-streaming chat reuse the same preflight suggestion, while the actionable suggestion card remains attached to the completed answer.
- The initial routing fix did not mutate Chroma. A follow-up integrity audit identified the reported `Nothing found on disk` entries as empty read-created collections rather than missing files from populated textbook indexes.

### Validation

- Added regression coverage for parent/child route scoring and for suppressing wrong-textbook retrieval when a cross-subject suggestion is active.
- Targeted routing and stream reliability tests: 11 passed.
- Full backend regression: 230 tests passed with one existing Starlette/httpx2 deprecation warning.

## 2026-07-29 - Chroma phantom-collection repair

### Cause and repair

- `get_chapter_store()` had used LangChain Chroma get-or-create semantics on the read path since commit `ebf058e1` (2026-05-31). Commit `21ea40b9` (2026-07-03) added the current book-scoped `bk...` names but did not delete existing index files. Querying planner-generated subsection names triggered the latent bug on 2026-07-29.
- The SQLite catalog contained eight unmapped collections with `count=0`; their HNSW directories never existed. All 507 mapped vector segments had matching directories, so no populated textbook index was corrupt.
- Created a byte-for-byte full backup at `data/vector_db.backup-20260729-empty-collections` before repair, then deleted only the eight verified empty collections. PDFs, OCR/MinerU chunks, lexical indexes, mistakes, and learning records were untouched.
- The read path now checks `get_collection()` before constructing the LangChain wrapper, preventing unknown chapter lookups from creating empty collections.

### Validation

- Chroma now reports 507 collections and zero registered vector segments with missing directories; unknown subsection queries keep the collection count unchanged at 507.
- Sensor long-book index: 12 collections / 1359 vector chunks / 1359 lexical chunks; sensor short-book index: 479 collections / 562 vector chunks / 562 lexical chunks.
- Real chapter retrieval returned results, and whole-book retrieval ranked Chapter 4 (force sensors) and Chapter 11 (signal processing) for the dynamic capacitive-sensor query.
- Added a regression test proving a missing chapter read cannot construct a Chroma collection. Full backend regression: 231 tests passed with one existing Starlette/httpx2 deprecation warning.

## 2026-07-30 - Electron startup recovery and titlebar feedback

### Desktop and frontend

- Replaced the non-customizable Windows Window Controls Overlay with isolated custom controls in both the React application and startup page. The BrowserWindow now uses `frame: false`; each interactive button owns an explicit `no-drag` hit region and standard click semantics, while window dragging remains on the non-overlapping left brand header. Minimize and maximize animate a full-button background and glyph geometry on hover, provide a compressed active state, preserve keyboard focus, and honor `prefers-reduced-motion`; close keeps its red danger state.
- Restored the main page header as an Electron drag region, including native double-click maximize and restore behavior. Interactive controls inside the header remain explicit `no-drag` regions.
- Kept the page-header drag region outside the 138px window-control hit area so it cannot suppress button hover/click feedback. The control backing now spans the full 64px header height and draws the same bottom border and translucent surface while the three animated buttons remain 42px high.
- Electron now waits for backend health even when a frontend development URL is configured, preventing the React application from opening against a backend that is still starting.
- Added a startup retry IPC flow and a visible “重新连接” action on the failure screen. If the backend process has exited, retry starts it again before waiting for health.
- Added a per-launch cache key when loading the application so a restarted desktop client cannot reuse stale titlebar/overlay assets from the previous renderer session.
- Removed the explanatory caption below “选择导入方式” and both option subtitles below “导入 PDF 教材” and “导入 MinerU 输出包”. Promoted the section heading to 18px semibold and the two option labels to 16px medium.
- No backend API, database, vector index, textbook data, mistake record, or learning record format changed.

### Validation

- Frontend ESLint passed; TypeScript and Vite production build passed.
- Frontend Vitest: 12 files / 38 tests passed. The first sandboxed run was blocked by Windows `spawn EPERM`; the approved unsandboxed rerun passed.
- Electron main/preload syntax checks and `git diff --check` passed.
- Windows Electron production-build validation at 125% display scaling confirmed visible full-button hover feedback for both minimize and maximize. A real maximize click changed the test window from 981×820 to 2048×1232 and synchronized the restore glyph. The 教材导入 page renders without the section caption or either option subtitle, and an isolated missing-backend simulation shows “重新连接”, Web fallback, and backend-log actions.
- Fresh Electron development-window validation confirmed that double-clicking the central page header changes the window from 1280×820 to 2048×1232 and a second double-click restores it to 1280×820. Visual inspection confirmed one continuous bottom border across the brand header, page header, and right-side window-control area.
- Follow-up Electron validation reproduced the overlapping drag-region regression, then confirmed the full-button hover background was visible again after separating the page-header and control hit areas; central-header double-click maximize remained functional.

## 2026-07-30 - Scoped font trial

### Frontend and packaging

- Added a self-hosted Latin Regular subset of JetBrains Mono and placed it before the existing Windows monospaced fallbacks for code, identifiers, and other explicitly monospaced content.
- Added the Unicode-split LXGW WenKai Screen webfont for learning suggestions and Markdown quotations only. Its stylesheet is injected only when a report or quotation surface mounts; navigation, controls, tables, metrics, normal answers, and the application shell continue to use the existing Windows system font stack.
- Added bundled-font provenance and license texts under `THIRD_PARTY_NOTICES/fonts`; the desktop backend build now carries that notice directory into the packaged application.
- No backend API, database, vector index, textbook data, mistake record, or learning record format changed.

### Validation

- Frontend ESLint passed; Vitest passed 12 files / 38 tests; TypeScript and the Vite production build passed.
- Chromium production-asset checks confirmed both `LXGW WenKai Screen` and `JetBrains Mono` load successfully, and a visual specimen confirmed distinct glyph rendering without changing the surrounding system-font UI.
- The production entry does not preload the LXGW stylesheet. The report surface injects the hashed `result-*.css` asset on mount.
- JetBrains Mono adds two Latin font assets totaling 47.5 KiB. LXGW WenKai Screen adds 241 Unicode-split WOFF2 assets totaling 12.53 MiB to the offline package, while runtime font downloads remain limited by `unicode-range`.
## 2026-07-30 - Practice workspace visual restructuring

### Frontend

- Rebuilt the practice workspace as one focused exercise surface instead of stacked full-width cards. Session controls, question context, answer entry, solution review, and mastery rating now form a clear top-to-bottom workflow with a bounded desktop reading width.
- Removed the chat-bubble treatment from exercise questions and explanations by adding a reusable document rendering variant to `ChatMessage`; normal conversation rendering remains unchanged.
- Kept answers and explanations collapsed by default. The expanded state uses a balanced two-column layout on desktop and falls back to one column on narrower viewports.
- No practice handlers, backend APIs, database schemas, exercise records, or review scheduling rules changed.

### Validation

- Frontend ESLint passed.
- Frontend Vitest passed 12 files / 38 tests.
- TypeScript and the Vite production build passed.
- Electron visual validation at 1280 x 820 confirmed both collapsed and expanded states fit without horizontal overflow and keep the primary practice actions visible.

## 2026-08-01 - Sensor chapter index rebuild and Chroma preflight repair

### Cause and data repair

- The planner benchmark repeatedly reported `Error creating hnsw segment reader: Nothing found on disk` for valid sensor chapters. A direct full-store audit could query all 507 collections, but the real chat order (`get_book_index_stats()` followed by chapter retrieval) reproduced the failure reliably.
- Created a complete recoverable backup at `data/vector_db.backup-20260801-230303-chapter-repair` before mutation.
- Rebuilt the sensor short book from its independent lexical source (479 chapters / 562 chunks) and the sensor long book (12 chapters / 1359 chunks).
- Replaced the legacy ASCII-parentheses full-text collection with the canonical chapter title. The old collection was removed only after all 59 `chunk_id` values and document texts matched the replacement exactly.
- The underlying failure was not missing persisted HNSW files after rebuild: calling `count()` across hundreds of chapter collections during the chat preflight invalidated subsequent Chroma HNSW readers. Book health now uses collection mappings plus the independent lexical chunk count instead of opening every HNSW segment.
- `ChapterVectorStore` now owns one persistent Chroma client and passes it to all LangChain Chroma wrappers, avoiding competing client lifecycles for the same persistent path.

### Validation

- Full vector audit: 507/507 collections completed a real embedding-vector query; zero mapped collections were missing, zero collections were unmapped, and no files under `data/vector_db` had the NTFS compressed attribute.
- The exact production order of book-health preflight followed by retrieval now returns the requested `第二节 等效电路与测量电路` chapter without an HNSW error.
- The full sensor teach retrieval includes both `第二节 等效电路与测量电路` and `第六章 压电式传感器` in the retrieved chapter set.
- Added client-lifecycle and safe-health-check regression coverage. Full backend suite: 233 tests passed with one existing Starlette/httpx2 deprecation warning.
- Machine-readable reports: `data/eval/vector_collection_health_20260801.json` and `data/eval/chapter_index_repair_final_20260801.json`.

## 2026-08-02 - Task-first frontend hierarchy cleanup

### Frontend

- Reworked the chat empty state into one focused starting surface: one due-review recommendation, four flat study intents, and a tertiary mistake-capture entry replace the previous dashboard-like card collection.
- Separated exercise configuration, continuous-session, single-question, submitted-solution, and mastery-rating states. The exercise question is hidden until practice starts, mastery controls appear only after solution review, and direct practice from the exercise bank remains an explicit single-question flow.
- Simplified the mistake-entry wizard so crop, recognition, and clearing controls appear only when relevant; reduced the upload surface and removed implementation-oriented OCR microcopy.
- Split textbook import into source selection and file/settings steps, moved MinerU quality controls under advanced options, and made missing prerequisites explicit next to the disabled primary action.
- Reordered the learning overview to show today's conclusion first, then recommended actions, then supporting analysis; recent questions and secondary review concepts are collapsed by default.
- Reduced settings width and navigation weight, replaced oversized exercise metric cards with a compact summary row, and removed explanatory or internal-status copy that did not help the next user decision.
- No backend API, database schema, vector index, textbook data, mistake record, or review-scheduling format changed.

### Validation

- Frontend ESLint passed.
- Frontend Vitest passed 12 files / 38 tests.
- TypeScript and the Vite production build passed; the existing MathLive chunk-size warning remains unchanged.
- In-app desktop-browser visual checks at 1280 x 720 covered chat, exercises, textbook import, mistake entry, and settings. The learning page layout was type/build verified because its local summary API remained unavailable during visual QA.
## 2026-08-03 - Lightweight interaction motion system

### Frontend

- Added a keyed route-stage entrance for page navigation, using a 200 ms opacity and 6 px vertical transform without retaining the previous route.
- Added shared entrance treatments for modal backdrops, normal and large dialogs, the compact sidebar drawer, popovers, and completion notices. Large surfaces avoid scale transforms; all motion uses only opacity and transform.
- Added a 90 ms tactile active state to shared primary/secondary buttons, sidebar navigation, sidebar controls, and scope-selector options.
- Motion runs only when `prefers-reduced-motion: no-preference`; no animation library, timer, scroll listener, or persistent `will-change` layer was added.
- No backend API, database schema, vector index, textbook data, mistake record, or learning record format changed.

### Validation and performance

- Frontend ESLint passed; Vitest passed 12 files / 38 tests; TypeScript and the Vite production build passed. The existing MathLive chunk-size warning remains unchanged.
- Compared with the preceding production build, entry CSS increased from 68.52 kB / 12.99 kB gzip to 70.57 kB / 13.36 kB gzip (+2.05 kB / +0.37 kB gzip). Entry JavaScript increased from 42.79 kB / 13.35 kB gzip to 43.01 kB / 13.41 kB gzip (+0.22 kB / +0.06 kB gzip).
- Fresh Electron validation at 1280 x 820 covered the first-run large dialog, 12 consecutive route changes across all six primary pages, and opening/closing the scope-selector popover.
- In an 18-second interaction sample, the four new Electron processes averaged 58.2% of one CPU core, versus 33.3% during an equal recovery-idle sample. The process group returned to the lower idle level after interaction rather than remaining elevated. The 250 ms sampling peak was 267.8% of one core during page loading/capture.
- Working set rose from 571.9 MB to a 614.0 MB peak while all lazy routes were visited, then stabilized around 586.0 MB; private memory stabilized around 285.6 MB. The retained increase is consistent with first-load route modules and page data, and no repeated growth was observed after interaction stopped.
- Runtime CPU figures include Windows Graphics Capture used by the UI validation tool, so they are suitable for relative interaction-versus-idle comparison, not as an end-user absolute idle benchmark.

## 2026-08-09 - Session Context and Planner routing专项优化

### Planner 与教材范围路由

- 为 Planner 增加内部可观测 telemetry：提示词构建、API 请求起止、首 token、响应解析、章节 fallback 与总耗时，以及 token usage、reasoning token、finish reason、retry count、模型名和 request id。Fast-path 与 General QA bypass 使用相同的有界 trace 结构，不记录提示词或回答正文。
- 在 Session Resolver 后加入保守的 deterministic 教材范围 gate。显式教材请求和已解析追问保留教材检索；明确学科错配、健康词法索引中缺失的特征英文词或定义锚点可退出当前教材模式；其余模糊问题继续继承已选教材。
- 扩展短且结构明确的 deterministic fast-path，覆盖简单比较、计算方法和简短“解释 X”；多约束比较、推导、证明和详细解释仍进入 Planner。
- 删除 fast-path 在正式 retrieve 前的向量章节预探测。章节定位由唯一的 retrieve 流程负责，避免同一问题做两次完整向量检索。

### Session Context

- 将追问解析迁移到 `backend/services/session_context.py`，以可重放的 `topic / entities / frame / constraints / intent / last_resolved_query` 状态替代旧的历史短语拼接。
- 支持稳定实体顺序下的“第一个”、比较 frame 的“前者/后者”、后续条件增量，以及“性质 → 怎么算 → 举例”等连续意图继承。派生状态不写入会话文件，旧会话无需迁移，也不会把一次误解析永久固化。
- 前端 retrieve 阶段根据 `use_textbook_context` 区分“检索教材上下文”和普通“准备回答”，避免 General QA 显示误导性的教材检索提示。
- 未修改数据库、会话文件、向量索引、教材数据、错题记录或学习记录格式。

### Validation

- 后端全量 pytest 通过：319 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript 与 Vite 生产构建通过；Vitest 13 files / 49 tests passed。沙箱内首次 Vitest 因 Windows `spawn EPERM` 失败，获批的沙箱外重跑通过。
- `git diff --check` 通过；Python `compileall` 因现有 `__pycache__` 目录写权限不足未作为验证依据，相关模块已由全量 pytest 导入覆盖。

## 2026-08-09 - 学科专属 General QA 与 ConceptMemory 路由

### 回答范围

- 将回答范围显式拆分为 `textbook_grounded`、`subject_general`、`global_general` 和运行时的 `subject_mismatch`，保留 `use_textbook_context` 作为是否执行教材检索的内部细节，不再用它同时表达知识边界。
- 自动模式优先使用当前教材；问题明显属于当前学科但教材没有对应内容时转为学科通用回答；明显跨出当前学科时停止生成并提示范围不匹配。用户可从该提示直接发起一次显式的跨学科通用回答，避免系统暗中扩大边界。
- 范围判断会检查当前学科下全部健康教材的词法概念锚点，避免仅因当前选中的短教材未收录某个学科内概念就误判为跨学科。显式跨学科模式始终拥有最高优先级。
- 对话界面显示“教材依据 / 学科通用 / 跨学科通用 / 范围待确认”来源标记；范围不匹配消息提供“跨学科通用回答”按钮，并保留原问题用于重新提交。

### ConceptMemory

- 教材回答继续按教材 KG 与检索概念归属；学科通用回答使用当前学科归属；跨学科通用回答进入通用归属，不再错误复用当前教材的知识图谱。
- 通用回答在严格的本地概念链接后，异步复用结构化 LLM 概念提取作为 fallback；提取提示词带回答范围和学科约束，既支持无教材概念，也保留显式提及、证据支持和去泛化门槛。
- `subject_mismatch` 不生成答案，也不写入 ConceptMemory。学习事件新增回答模式与范围原因，来源细分为教材、学科通用和跨学科通用。
- 未迁移或重建 ConceptMemory、教材索引、向量库、错题及复习数据。会话消息仅新增可选的回答模式与范围原因字段，旧会话保持兼容。

### Validation

- 后端全量 pytest 通过：329 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript 与 Vite 生产构建通过；Vitest 通过：13 files / 49 tests passed。沙箱内首次启动仍受 Windows `spawn EPERM` 限制，获批的沙箱外重跑通过。构建仅保留既有的 MathLive 大 chunk 提示。
- `git diff --check` 通过；真实路由检查确认传感器教材中的“QKV”进入 `subject_mismatch`，“压阻效应”保持 `textbook_grounded`，显式跨学科请求进入 `global_general`。

## 2026-08-09 - 复合问答与指代追问修复

### 根因与路由

- “压阻式传感器怎么算”此前被归入宽泛的 `application`，其检索角色优先例题和实例，导致回答列举压阻式加速度、压力传感器而没有给出计算链路。新增独立的 `calculation` 意图，公式、算法和推导证据优先，并要求生成器先说明计算对象是否唯一，再给公式、变量、适用条件和计算顺序。
- 显式“比较 / 推导 / 计算”任务现在可锁定本地确定性意图；Planner 仍负责复杂问题的章节定位，但不能因“并说明”等次要词把多维比较改判成事实背诵。
- 计算检索使用同一次向量与词法调用中的意图化查询，不增加第二轮向量预检或新的 LLM 调用，保留本轮优化后的生成速度收益。

### Session Context 与证据支持

- 比较 frame 支持“比较 A 和 B。”以及三项以上的“比较 A、B 和 C，并分别说明……”结构，并补全中文并列结构中省略的共享后缀，例如将“压阻式和压电式传感器”解析为两个完整实体。
- “前者 / 后者”从 comparison frame 按稳定顺序解析；“那后者呢”这类省略追问会继承上一问的谓词，而不是把原始指代词交给向量检索。由此避免误命中“静态磁头 / 动态磁头”。
- 复合问题的 Evidence Support Gate 改为逐个事实维度检查。灵敏度、频响、静态测量能力、误差来源、基本公式和近似条件不再被拼成一个不可能逐字命中的长短语；多个证据块可以共同覆盖各维度。
- 真实教材证据仍不足时不会自动混入模型知识。拒答文案给出缩小问题或改用学科通用回答的引导，前端同时提供显式“改用学科通用回答”按钮；拒答本身不写入 ConceptMemory。
- 会话消息仅新增可选的建议回答模式字段；未迁移数据库、向量库、教材索引、ConceptMemory、错题或复习数据。

### Validation

- 用传感器短书真实索引重放：复杂推导题与三类传感器多维比较均由 `insufficient` 转为 `supported`；计算题进入 `calculation`；“前者”解析为压阻式传感器，“那后者呢”解析为同一谓词下的压电式传感器。
- 后端全量 pytest 通过：340 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript、Vite 生产构建通过；Vitest 13 files / 49 tests passed。构建仅保留既有的 MathLive 大 chunk 提示。

## 2026-08-09 - 发布闸门与关键正确性收口

### 数据安全与桌面生命周期

- 将备份恢复正式定义为非破坏性的“合并恢复”：备份内的核心根目录会被替换，备份中未包含的其他核心数据会保留；恢复结果记录 `restore_mode` 与 `preserved_unlisted`，API 和设置页使用一致文案。派生向量库与 MinerU 产物仍按原策略失效，以避免旧索引和恢复数据不匹配。
- 打包后端改为显式 `uvicorn.Server`，提供受本地 API token 保护的优雅停机端点。Electron 退出时先请求取消 durable jobs、等待 Uvicorn 排空请求并退出，8 秒超时后才回退到强制终止；后端 lifespan 退出阶段释放向量库缓存引用。
- 首次引导升级隐私确认版本，明确 LLM 会接收问题、必要会话上下文和选中教材证据，Kimi OCR 会接收所选图片；“稍后再看”不再永久跳过提示。产品页同步删除“完全不上传云端、不依赖网络”的错误承诺。

### 发布合规

- 新增 `scripts/check_release_content.py`。正式包若包含样例教材、派生索引、图片或模型，必须逐文件声明来源、许可证、可再分发状态和 SHA-256；未声明、许可缺失或哈希不一致即阻止构建。样例 PDF 默认不再自动复制，历史错误的默认数据路径已修正。
- Windows release workflow 现在要求仓库存在 `LICENSE`、要求签名证书和密码，并在发布产物生成后验证安装器与主程序 Authenticode 签名。
- 当前本地 `desktop/sample_data` 仍包含未登记授权的《优化设计》PDF及派生文件，因此内容闸门按设计失败；未删除这些本地文件，也未伪造授权。补齐内容清单或从发布输入中移除后方可正式构建。

### RAG、会话与导入正确性

- teach/summarize 的同步与流式路径统一使用 Retrieval 产出的 EvidencePack；证据支持为 `insufficient/unavailable` 时直接走教材拒答，不再通过章节二次检索绕过门禁。教学提示词使用 E-id 引用协议，流式最终正文也执行 citation 清洗。
- SQLite 事件库成为会话权威存储，最近窗口 JSON 明确降级为可重建的兼容投影；JSON 写入失败不再让已提交消息或 split 操作向调用方误报失败。
- 同一 `conversation_id + turn_id + role` 重试改为幂等；断开的 SSE 会持久化 `partial` assistant 消息，重试完成后原位升级为 `complete`，避免重复 turn 和刷新后完全丢失已生成正文。
- KG 加载边界兼容当前 `content` 与旧 `text` chunk schema；`/books/import-local` 成功后将 PDF 从 staging 提升至正式教材目录，失败时执行索引、metadata、上传文件与正式 PDF 的补偿清理。
- 周报兼容错题复习和习题练习当前写入的 `date` 字段，修复本周复习数与练习数长期为零或偏低的问题。

### Validation

- 新增备份合并语义、会话幂等、partial completion、JSON 故障注入、split 投影故障、EvidencePack 拒答、KG schema、本地教材归档补偿、周报日期、内容授权闸门和优雅停机回归测试。
- 后端全量 pytest：403 passed；仅保留既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：15 files / 70 tests passed；ESLint、TypeScript 与 Vite production build 通过。构建仍保留既有 MathLive 801.47 kB 大 chunk 提示。
- `node --check desktop/main.cjs` 与变更 Python 文件 AST 解析通过；`git diff --check` 无空白错误。

## 2026-08-09 - 桌面运行链路可靠性收口

### 动态端口、单实例与故障恢复

- Electron 在未显式设置 `KAOYAN_BACKEND_URL` / `KAOYAN_BACKEND_PORT` 时，启动和恢复阶段会按当前绑定范围分配可用端口；实际 API base 随一次性桌面启动参数传给前端，远程采集地址、优雅停机、健康检查和导航白名单统一使用当前端口。显式端口/URL以及 `KAOYAN_SKIP_BACKEND=1` 仍保留原有开发覆盖语义。
- 主进程取得单实例锁；重复启动只恢复、显示并聚焦已有窗口，不再并行拉起第二套后端和数据目录访问者。
- 被主进程托管的后端意外退出后最多自动恢复 3 次，使用有界指数退避并在成功后刷新到新的动态端口。前端增加“启动中 / 恢复中 / 失败”状态条，恢复耗尽后提供手动重试和打开后端日志；切换局域网采集导致的计划内重启也会刷新 API base。
- 新增可独立运行的桌面 runtime helper 与 Node 单测；CI 新增 desktop job，使用 `npm ci` 后执行 helper 测试及 Electron 脚本语法检查，打包文件显式包含 runtime helper。

### 鉴权资源与依赖锁定

- 教材 PDF、章节重点静态 HTML及其本地图片不再以裸 `/api` URL 交给 `iframe`、`img` 或新窗口。前端先通过带 `X-Kaoyan-Token` 的请求取得内容，再使用有生命周期清理的 blob URL；静态 HTML 内的本地 API 图片同样会先鉴权并改写，外部 URL 被拒绝进入本地鉴权请求，避免 token 泄漏。
- PDF 页码 fragment 只在 blob URL 上拼接一次，修复原先重复 `#page` 导致的错误预览地址。应用内重点入口改为 SPA 内导航，避免 Electron 把相对入口当成外部浏览器链接。
- `requirements.txt` 改为兼容入口，统一转到复用精确发布依赖的 `requirements-dev.txt`；pytest 固定到 `9.0.3`。新增依赖锁检查脚本，CI 与桌面发布均执行 exact-pin 检查和 fresh-env `pip check`；前端/桌面继续由 lockfile + `npm ci` 约束。PaddleOCR、Marker、MinerU 等冲突较多的可选栈明确保持在主锁之外。

### Validation

- 后端全量 pytest：403 passed；仅保留既有 Starlette/httpx2 弃用警告。
- Desktop Node tests：2 passed；`main.cjs`、`preload.cjs`、`runtime.cjs` 语法检查通过。
- Frontend Vitest：15 files / 70 tests passed；ESLint、TypeScript 与 Vite production build 通过。构建仅保留既有 MathLive 801.47 kB 大 chunk 提示。
- Python dependency exact-pin 检查通过；`git diff --check` 通过。
- 当前既有 `venv310` 仍混装了未纳入主锁的 PaddleOCR、Marker、Surya 等可选栈，`pip check` 会报告其 Pillow、protobuf、PyYAML、numpy、openai、websockets 与 fsspec 冲突。按数据/环境安全约束，本次未擅自重装或清理该环境；fresh CI/发布环境会执行并要求 `pip check` 通过。
# 2026-08-14 - ONNX Runtime Phase 2 release feasibility

## Reachability 与 Torch-free runtime

- 完成全仓库 Torch/SentenceTransformers/Transformers/safetensors/huggingface_hub 依赖清单和 Electron → packaged Python → FastAPI warmup → Chroma/retrieval/reranker 的 production reachability 追踪。当前 Standard 唯一必需的 Torch blocker 是 `config.py` embedding；CrossEncoder 仅在有效 `RERANKER_MODEL_PATH` 下函数内惰性加载，默认 deterministic rerank，普通用户路径不需要。
- 建立独立 Python 3.10 Torch-free venv 与实验 Candidate entrypoint；未安装 torch、sentence-transformers、transformers、safetensors。backend import、FastAPI lifespan/health/warmup、512 维 query embedding、49 个真实 Chroma collections、教材/通用检索、5 本教材发现均通过。正式 `config.py` backend 和 release requirements 未切换。
- 100 个固定 query 直接查询既有 PyTorch BGE Chroma index，不 rebuild。Torch/ONNX Top-1/3/5/10 mean set overlap 为 `96.0% / 98.33% / 97.8% / 98.4%`；relevance recall 为 `56/78/88/89%` 与 `55/78/88/89%`。两边均复现同一既有 HNSW segment 缺盘，差异归因于 HNSW/tie/hybrid ordering；已有教材无需重新向量化。

## Windows package 与性能

- 构建真实 PyInstaller + Electron NSIS/ZIP/win-unpacked Baseline 和 Torch-free Candidate。Candidate backend 路径中 torch、sentence_transformers、transformers、safetensors 命中均为 0；packaged warmup、真实 retrieval 和 Electron 首次使用 UI smoke 通过。
- Baseline/Candidate installer 为 `401.83 / 285.54 MiB`，ZIP 为 `506.04 / 354.18 MiB`，win-unpacked 为 `1283.06 / 821.03 MiB`，backend 为 `963.59 / 501.55 MiB`。installed/backend 净减约 `462.03 MiB`，win-unpacked 减少 `36.01%`，installer/ZIP 分别减少 `28.94% / 30.01%`。
- 五次 frozen backend cold run：Torch/ONNX full ready median `10.21 / 4.03s`；first retrieval wall median `463.57 / 404.71ms`。同一 Phase 1 worker 分别冻结后，batch=1 median `6.76 / 2.95ms`；500-text ingestion `10.59 / 27.00 texts/s`，p95 peak RSS 约 `1034.66 / 1022.93 MiB`。
- 结构化 failure path 已覆盖模型缺失、模型损坏、ORT 导入失败、unsupported architecture 和 tokenizer mismatch；Standard 策略为明确错误、诊断日志和 repair 指引，不 silent fallback Torch。现有 HF repair 尚不能恢复自定义 ONNX graph，正式迁移前必须补齐 ONNX asset manifest/hash/download repair。

## 判定

- A. ONNX embedding production backend：`GO`（进入 Phase 3 迁移，不表示本阶段已经切换正式 backend）。
- B. Torch-free Texa Standard Release：`GO`；installed size 通过 400 MB 与 25% gate，未达到 600 MB STRONG PASS。
- C. Optional CrossEncoder：`MOVE TO OPTIONAL`；先从 Standard dependency 中移除，开发功能保留，有真实需求后再评估 Advanced Pack 或独立 ONNX migration。
- 完整证据、Top 20 size attribution、风险和 Phase 3 计划见 `benchmark_results/embedding_onnx_phase2/report.md` 与 `phase2.json`。

## 2026-08-14 - Frontend structural rebuild

### Shell 与学习工作区

- 将旧的单侧栏骨架替换为固定 `AppRail + LearningContextSidebar + Main Workspace + optional Inspector`。App Rail 只保留学习、复习、错题、练习、教材和设置一级导航；scope、新会话和 session history 全部进入独立学习上下文侧栏。
- 删除 `ChatHistorySidebar` 与 `ChatHomePanel`，移除中央 onboarding、推荐摘要请求和五个重复 quick actions。空会话只保留当前学习范围、`Ask Texa` 和输入提示。
- 学习页顶部不再重复 ScopeSelector，改为当前 session 标题与范围摘要；历史回答保持文档流，Composer 保持底部稳定位置，sources/concepts 继续通过可选 Inspector 渐进披露。
- 新增窄窗 overlay context 行为：正常桌面并列显示 rail/context/workspace，低于 1180px 时 context 以可关闭 overlay 打开，720px 级窗口保持主输入可用。

### Validation

- Frontend ESLint 通过；Vitest 18 files / 80 tests passed；TypeScript + Vite production build 通过，仅保留既有 MathLive 大 chunk 提示。
- Electron 实机验证通过：initial state、scope switching、existing session restore、new session、context collapse/reopen、783×702 窄窗与 2048×1232 宽窗均实际运行并截图。
- QA 请求进入 plan/retrieve/generate 流程，但当前运行环境缺少模型凭据，在线长回答、LaTeX 与新 source 生成被 `Missing credentials` 阻塞。按后端边界未修改 Python、API、RAG、模型配置或数据；记录为 `UX_BLOCKED_BY_BACKEND`。已有 history、Markdown/document rendering 与 Inspector contract 由实机会话和前端测试覆盖。

## 2026-08-15 - Shell、复习层级与教材检索角色定向修复

### Electron drag 与统一 header geometry

- 根因是整个 page/sidebar/workspace header 被声明为 `-webkit-app-region: drag`；折叠态的绝对定位展开按钮与 workspace header 重叠后，Electron 的 draggable hit-test 会先吞掉点击。现改为 header 内显式 `.window-drag-region` 空白 flex 区，父 header 不再整体可拖动，所有按钮、链接、selector、menu trigger 和原生交互元素统一 `no-drag`。
- Window Controls Overlay 继续使用 64px 高度；App Rail logo、Sidebar Title、Main Header 与原生窗口按钮共享同一 header token。原生控制区改为 header 内右侧安全 padding，不再用外部 margin 截断 header 边界。

### 复习页与教材库 UI

- 复习页重排为“今天要做什么 → 为什么这些内容优先 → 补充分析”。主要行动只使用一层 grouped rows；展开内容通过缩进和左侧 hairline 表达父子关系。高频概念、错题薄弱点与活动热图降为末尾 secondary analytics。
- 移除概念原因、活动分类和关联概念的装饰性 badge，改为普通辅助文本；顶部 scope/刷新/完善知识关联统一为 36px control geometry。Anti-slop 结果：同级 page/section cards `REMOVED`，嵌套 bordered surfaces 与 decorative badges `REDUCED`；菜单 shadow 和“当前教材”状态标记因浮层/真实状态语义 `JUSTIFIED`。
- 教材行按“名称与角色 / 归属与必要 metadata / 当前动作 / overflow”组织。主要、辅助、独立改为显式 role choice，并常驻说明“优先参考”或“补充、交叉验证和缺失内容”；重命名、隐藏移入支持 Escape/点击外部关闭的 contextual menu。

### 教材角色 retrieval policy

- 角色仍只存为教材级 `metadata.json`，没有复制正文或建立第二套索引。检索时按资料组解析教材，分别进行 BM25/向量召回，在 RRF、literal coverage、semantic role、selected-book 与可选 cross-encoder 信号之后施加统一 soft prior，再由 EvidencePack 进入生成器。
- 移除 rerank 内写死的 `core +0.035 / reference -0.006` 和 vector 阶段读取索引快照 priority 的分散逻辑。新增集中 policy：默认 primary `1.04`、supplementary `0.98`、standalone `1.0`，可通过 `TEXA_*_TEXTBOOK_MULTIPLIER` 环境变量配置；将两个 role multiplier 设为 `1.0` 即可回退。可选教材级 `rag_priority` 保留但被安全夹在 `0.90..1.10`，最终组合 prior 限制在 `0.85..1.15`。
- `relevance_score` 保留 prior 前原值，`textbook_role_multiplier` 与最终 `score` 分开记录。运行时教材 metadata 覆盖索引中的旧 `book_role/rag_priority` 快照，因此角色或资料组修改下一次请求立即生效；没有主要教材时，所选教材仍成为组内 primary resource 并正常检索。无需重新 OCR、embedding、BM25 或 Chroma indexing。

### Validation

- Frontend TypeScript + Vite production build、ESLint 通过；完整 Vitest：18 files / 83 tests passed。构建仅保留既有 MathLive 大 chunk 提示。
- 后端全量 pytest：475 passed；仅保留既有 Starlette/httpx2 弃用警告。教材 policy、resource group、hybrid rerank、EvidencePack、citation 与 evidence continuity 定向集合为 50 passed。
- Desktop `main.cjs`、`preload.cjs`、`runtime.cjs` 语法检查通过。
- Electron 实机重启到新资源后，展开态折叠按钮与折叠态展开按钮均实际点击成功；1280×720、720×720 与 1600×900 运行态截图覆盖层级、密度和多宽度布局。`git diff --check` 无空白错误。
# 2026-08-21 模型目录、连接测试与桌面窗口反馈

- 模型配置把固定输入改为“常用官方 model id + 自定义 model id”，补充 DeepSeek V4、Qwen 3.5–3.8、Gemini 3.6/3.7 与 OpenAI GPT-5.4/5.6 系列候选，同时保留既有默认与兼容别名，避免升级破坏当前配置。
- 新增不落盘的模型连接测试。测试直接使用表单中的 Provider、Endpoint、Credential 与 model id 发起最小调用，确保自定义模型名会进入实际请求；错误信息会过滤表单中的密钥。
- 教材库页移除标题下重复说明；Windows/Linux 桌面端恢复自绘最小化、最大化与关闭按钮，并为 hover、press、最大化状态增加短反馈动效，减少动态效果模式下关闭过渡。
- 验证：Python 全量测试 `489 passed`；前端 `83 passed`、ESLint 与生产构建通过；Electron 运行时 `3 passed`。浏览器实测覆盖常用型号列表、自定义 model id 输入与测试按钮启用、教材库标题区域。Electron 窗口成功启动，但 Windows 自动化截图授权超时，因此窗口动效以运行时测试和代码检查为准。

## 2026-08-21 教材库文字层级收口

- 教材库移除重复的分类、归档和检索机制说明，教材角色文案压缩为直接结果；常规标签、角色选择、输入与操作统一使用 14px 的 `type-control` / `type-body`，仅计数、状态和存储名保留 12px 辅助层级。
- 教材行在普通笔记本宽度改为单列，在宽屏恢复双列，避免归属和资料组控件被压缩。Anti-slop 结果：重复说明与 11px 文字 `REMOVED`，逐行机制解释 `REDUCED`，计数、当前状态与存储名 `JUSTIFIED`。
- 验证：前端 Vitest `19 files / 87 tests passed`，ESLint、TypeScript 与 Vite production build 通过；浏览器实测覆盖 1280×720 和 1600×900，两种宽度均无横向溢出，教材行标签、输入、下拉和角色按钮计算字号均为 14px。

## 2026-08-21 模型与教材归属滚动列表

- 新增模型与教材归属共用的 `ScrollableSelect`：浮层使用常驻原生纵向滚动槽，可滚轮滚动并拖动滑块；选项支持分组、当前项、14px Texa 控件字体和悬停阴影。
- 补齐方向键、Home/End、Enter、Escape、Tab、外部点击关闭、焦点返回和视口边界定位；教材归属沿用现有学科数据，但未修改学科树或全局 `ScopeSelector`。
- 验证：前端 Vitest `19 files / 87 tests passed`，ESLint、TypeScript 与 Vite production build 通过；1280×720 和 1600×900 浏览器实测无横向溢出，长教材归属列表滚动位置可变，运行日志无 error/warn。

## 2026-08-21 Texa 品牌标识接入

- Electron 窗口运行时图标与 Windows 打包图标统一改为透明底多尺寸 `texa.ico`，并设置与 `appId` 一致的 Windows App User Model ID；桌面打包文件清单显式包含品牌资源。
- App Rail 左上角由书本图标替换为纯图案 Texa 标识；启动加载页由书本插画替换为完整的 Texa 图文 Logo。两处均直接使用透明底 SVG，保留清晰缩放。
- 验证：前端 Vitest `19 files / 87 tests passed`、ESLint、TypeScript 与 Vite production build 通过；Electron runtime `3 passed`、主进程脚本检查通过；实际截图确认 App Rail 标识与启动页完整 Logo 的比例和清晰度正常。electron-builder 已正确读取新图标配置并进入 Windows 打包阶段，但下载其 Windows 辅助组件时连接 GitHub 超时，因此本机未生成新的完整 `win-unpacked` 产物。

## 2026-08-21 习题工作区工具栏尺寸统一

- 习题工作区的“练习 / 题库 / 导入”分段控件与刷新按钮统一采用复习区的 36px 工具栏高度、14px 控件文字和 12px 横向内边距，移除原先独立纵向 padding 造成的视觉放大。
- 验证：前端 ESLint、TypeScript 与 Vite production build 通过，UI contract 定向测试 `11 passed`；1280×720 与 1600×900 实测分段控件外框和刷新按钮均为 36px，宽屏无横向溢出。Anti-slop 结果：不一致的大尺寸控件 `REMOVED`，未新增表面、阴影、徽章或动画。

## 2026-08-21 深浅任务栏兼容图标

- Electron 窗口与 Windows 打包图标切换为独立的 `texa-taskbar.ico`：原 Texa 矢量轮廓和深灰/浅蓝配色保持不变，增加浅色圆角底板与细深色边界，避免深色任务栏吞掉主体。应用内透明 Logo 和启动页图文 Logo 不变；底板仅用于系统背景对比，属于小尺寸可辨识度处理。
- ICO 包含 16、20、24、32、40、48、64、96、128 与 256px 图层；1024px RGBA PNG 作为确定性源资产保留。深色、浅色背景模拟和 16–32px 像素检查均可辨识，且正负形仍与原 Logo 一致。Electron 本地窗口成功启动；Windows 自动化未获窗口读取授权，因此没有直接任务栏截图。Electron 脚本检查、runtime `3 passed`、前端 ESLint 与 UI contract `11 passed`。

## 2026-08-21 首次打开模型设置复用

- 首次打开引导移除旧 `ModelSettingsForm`，直接复用正式设置页的 `ModelSettingsManager`，统一模型方案、服务商、常用/自定义 model id、API Key、图片任务模式、连接设置与连接测试界面。
- 首次打开页保存模型时改用与正式设置页相同的 model profile 接口，并补齐方案切换和删除；教材解析服务仍作为首次配置中的独立可选项保留。
- 验证：前端 ESLint、TypeScript 与 Vite production build 通过，UI contract 定向测试 `12 passed`；1280px 实际页面对照确认首次打开页与正式设置页均渲染同一模型管理器，弹窗和页面无横向溢出。

## 2026-08-22 《误差理论与数据处理》索引重建与发布门槛

- 新增覆盖 7 章、20 个教材内问题和 2 个教材外问题的黄金检索集；评测对象由候选调试列表改为生成器实际接收的最终 EvidencePack。索引激活前按本书数据集校验 Recall@K 与要点覆盖率，未达到配置门槛时不切换 active version，并把结果写入索引 manifest。
- 从清洗后的章节 Markdown 重新切分《误差理论与数据处理》，未复用旧 511 个 middle chunks。新 schema 4 索引版本为 `8b28cb1f64215c1a`，共 1034 chunks、7 个章节 collection；公式块保持原子性，并补充 section path、section chunk index、equations、block type 与 review status 元数据。
- 混合检索在 BM25 top-20 前增加标题、完整主题短语、直接章节与列举结构加权；列举问题围绕语义列表标题扩展相邻项，避免章节标题命中挤掉连续列表。Evidence support gate 去除纠正话语噪声，并要求主题与问题焦点在同一证据项内成立。
- Resolver/ConversationContext 支持“这四个方法的公式”“第三个方法”等组引用与序数引用；Context Eval 增加《误差理论》方法组、用户纠正和序数追问案例。传感器旧金标中的逐字匹配改为同义短语组，保持教材事实要求不变。
- 验证：重建后《误差理论》最终 EvidencePack 黄金集 `22/22`，Recall@K `1.0`、point recall `1.0`、MRR `0.9091`；生产 Context Eval v3 检索层 `15/15` 严格通过。原 OCR 中少量可疑公式仅被保留并标记，本次未重新调用外部 MinerU，因此不把结构完整性等同于公式识别已人工校正。

## 2026-08-23 教材 Canonical Document IR 基础层

- 新增 `ingestion/document_ir.py`：定义与来源无关的 `CanonicalBook`、`DocumentBlock`、确定性校验报告和 schema version 1。该层记录章节路径、页码、bbox、公式、来源、OCR 置信度、审阅状态和可扩展属性，作为解析与 chunking 之间的稳定契约。
- Canonical IR 以 `data/progress/<book>/canonical_document.jsonl` 落盘，并同步写入 `ingestion_report.json`。即使校验失败也会保留诊断源文件，但报告会标记为不可用于后续 splitter/index pipeline；本次未修改既有导入器或已激活教材索引。
- 体检扩展为可修复告警与阻断错误：检查标题层级跳跃/循环、公式分隔符、表格标题/表头/行、源页码范围、OCR 短文本/乱码/空正文页。公式分隔符异常会保留原文并追加 `needs_formula_review`；单页和单块质量问题只告警，只有 IR 合同损坏或没有可索引正文才阻断后续切分。
- 验证：新增 IR 的 JSONL round-trip、无效来源诊断、书级 provenance 与完整入库体检测试，`5 passed`；后续适配 PDF、MinerU、OCR 与 Word 时必须先输出该契约。

## 2026-08-23 Canonical Document IR 来源适配器

- 新增 `ingestion/document_adapters.py`：`PdfTextAdapter` 接收现有 `PDFParser` 章节输出；`MinerUAdapter` 支持 content-list、middle JSON 与 Markdown；`OcrAdapter` 接收页面版面/OCR blocks；`DocxAdapter` 通过受资源限制的 Office XML 读取标题、段落、表格与基础 OMML 公式文本。全部返回 `CanonicalBook`，并保留页码、bbox、OCR 置信度、表格结构、公式和来源属性。
- PDF/MinerU 正式教材导入结果现在携带 CanonicalBook；API 成功导入后将其落盘到教材 progress 目录，并在任务结果与教材 metadata 中写入 IR 体检状态。当前仍以旧 chapter/chunk 管线建立生产索引，IR 报告仅用于诊断，不因新适配器的 warning 阻断既有导入；后续完成 block splitter 后再把它升级为唯一入口。
- 验证：四种适配器、IR 体检、MinerU 外部导入与导入可靠性定向回归 `21 passed`。

## 2026-08-23 Canonical IR 唯一索引入口与生产检索激活事务

- 正式 PDF、MinerU/API、MinerU CLI、外部 MinerU 输出和教材重建统一先生成或加载 `CanonicalBook`，通过确定性 IR 校验并落盘后，再由 `ChapterSplitter.split_canonical_book()` 生成检索 chunks。旧 `chapters` 调用仅保留为兼容适配边界，内部会先转换成 Canonical IR，不再进入独立的 chapter-string 切块分支；既有教材首次重建时会自动补齐 IR，已有 IR 则优先复用以保留来源结构。
- 索引激活门槛由 staged lexical BM25 升级为完整生产混合检索：候选 Chroma collections、候选 lexical rows 和邻接扩展以只读依赖注入方式进入现有 `retrieve_node`，继续经过线上 KG/向量/BM25 融合、rerank、evidence support gate 与最终 EvidencePack。验收期间不替换 active map、不覆盖线上 lexical 文件，失败时删除候选 collections 并保持旧索引可用。
- 版本发布现在保留 active 版本和最近两个历史版本。历史 Chroma collections 在 map 中标记 `active=false`，不会被章节/aggregate 检索、预加载或健康统计选中；每个版本同时保存独立 lexical 快照，manifest 记录版本、collections、快照路径、激活时间和 chunk 数。超过保留上限的旧资产在新 manifest 原子切换成功后清理。
- 验证：后端全量回归 `518 passed`（仅 1 条既有 Starlette/httpx2 弃用警告）；使用《误差理论与数据处理》现有真实 Chroma/lexical 资产通过新 staged 生产验收入口实跑 `22/22`，Recall@K `1.0`、point recall `1.0`、MRR `0.9091`。本次只读实跑未重建或切换现有教材索引。

## 2026-08-23 自动结构探针与四类专项发布门槛

- 新增 `ingestion/acceptance_probes.py`：从 Canonical IR 确定性识别公式、编号/项目列表、例题和结构化/Markdown 表格，生成有界且稳定的结构验收探针。每条探针保留来源 block、章节路径、页码、review status 和 `human_approved=false`，明确只验证解析、切块、索引、检索与 EvidencePack 是否保留来源结构，不把自动结果冒充 OCR 正确性或人工语义金标。
- 正式导入和教材重建在 IR 落盘后同步写入 `acceptance_probes.generated.jsonl` 与 inventory report；探针按类型跨章节取样，每类最多 8 条。重复结构只计一次，避免重复公式/列表把最低覆盖样本数虚高。
- staged 生产检索发布门槛增加 `formula/list/example/table` 四个独立 gate。教材存在该类结构时要求最多 3 条样本覆盖，Recall@K 与 point recall 均为 `1.0`；不存在时显式返回 `not_applicable`。任何适用专项在样本覆盖或质量上失败都会拒绝激活并保留旧版本，manifest 的 `release_quality.specialty_gates` 保存逐类 inventory、样本数、阈值、Recall、point recall 和 MRR。
- 验证：探针确定性、四类识别、持久化、四类探针通过真实 staged lexical/生产 EvidencePack 路径、专项失败阻止激活及旧版本保护测试通过；后端全量回归 `522 passed`（仅 1 条既有 Starlette/httpx2 弃用警告）。《误差理论与数据处理》当前真实 active 资产只读回归仍为 `22/22`、Recall@K `1.0`、point recall `1.0`、MRR `0.9091`；其中 3 条既有公式黄金用例通过公式专项门槛，其他三类因当前版本尚无 IR inventory 而如实标记 `not_applicable`，本次未重建或切换现有教材索引。

## 2026-08-24 《误差理论与数据处理》Canonical IR 正式重建

- 以已落盘 Canonical Document IR 重新生成 7 个章节、2557 个检索块并激活 schema 5 索引 `2ce6661f40535ee4`；旧版本 `8b28cb1f64215c1a` 的 8 个 Chroma collections 与 lexical 快照作为可回滚历史版本保留。失败候选均在拒绝激活后清理，没有孤立 collection 或半切换状态。
- PDF 章节适配不再把整章压成单段：内部 Markdown 标题、段落、公式和例题按 IR block 保存，同时把章节正文中的一级标题限制为章内层级，避免把“小节”误识别成额外章节。本次 inventory 为公式 1033、列表 23、例题 79、表格 0；表格门槛按真实来源标记 `not_applicable`。
- 公式检索以精确命中的公式 block 为锚点，优先保留前后 IR 邻接说明，并在 EvidencePack 候选文本中携带公式小节标题。章节级 Chroma HNSW 暂时不可读时，检索会退回同一本书 aggregate collection 并保持章节 metadata 过滤，不扩大教材范围。
- 激活事务运行 46 个生产混合检索与最终 EvidencePack 用例，Recall@K `1.0`、point recall `1.0`；公式 11、列表 8、例题 8 个专项用例均为 `1.0`。激活后的固定人工回归为 `22/22`，Recall@K `1.0`、point recall `1.0`、MRR `0.9091`。后端全量回归 `524 passed`，仅保留 1 条既有 Starlette/httpx2 弃用警告。
- 修正重建脚本写入教材 metadata 时硬编码旧 schema 4 的问题，改为采用激活后健康检查返回的实际 schema；当前教材 metadata、manifest 与 API 统计统一为 schema 5。

## 2026-08-24 受控学习工具收敛到主聊天

- Tool Registry 增加结果 schema、capability、风险、超时、版本和 provenance 契约；`ToolResult` 明确区分数据、证据、校验、警告与待确认操作。新增 `docs/tool-calling-contract.md`，规定主聊天只有一条回答路径、只读自动执行、写操作保持提案，以及工具成功不等同于答案正确。
- 前端移除基于关键词切换 `/agent/read-only` 的独立回答分支。主聊天现在由 `backend/services/tool_orchestration.py` 在进入 graph 前选择并执行最多 6 个相关只读工具，把有界 Tool Context Pack 交给原有 planner/retrieval/generator；SSE 继续输出真实活动，工具失败会保留原回答降级路径。
- `search_textbook` 不再直接返回简化向量检索结果，改为复用生产 `retrieve_node`、evidence support gate 与最终 EvidencePack。学习进度、复习队列等本地状态工具成功时会跳过无关教材检索，但不会放宽教材事实的 EvidencePack 边界。
- 新增基于 SymPy 1.14 的受限数学工具：只接受有界 AST 表达式，支持数值计算、化简、求导、积分和一元方程；禁止任意 Python、导入、属性访问与代码执行。可验证结果会自动调用等价、导数、原函数、定积分或代入校验，警告和失败状态必须进入回答上下文。
- 已被受限数学路由可靠识别的闭合表达式不再交给教材向量命中猜测学科，避免纯算式被误判为其他专业课并在计算前触发跨学科确认；不符合受限语法的问题仍保留原学科路由边界。
- 新增 40 条考研学习场景离线对照集和 `evaluation/tool_calling_eval.py`。当前 route accuracy、no-tool precision、数学执行成功率与验证通过率均为 `1.0`；无工具策略的路由准确率为 `0.35`，受控路由提升 `0.65`。该结果只代表离线路由/工具合同，不表述为线上模型答案准确率。
- 验证：后端全量 `533 passed`（1 条既有 Starlette/httpx2 弃用警告）；前端 `19 files / 90 tests passed`、ESLint 与生产构建通过。1280×720 和 1600×900 实际页面确认答案保持 Learning Canvas 文档流，工具步骤在生成时可见、完成后默认折叠，展开后显示计算与校验，不再进入独立 Agent 卡片。Anti-slop：独立工具回答卡 `REMOVED`，处理记录技术细节 `REDUCED`，真实失败/校验状态 `JUSTIFIED`。
## 2026-08-24 - 工具接入后的教材 RAG 与生成消息边界修复

- 先将《误差理论与数据处理》临时回滚到保留的 schema 4 版本 `8b28cb1f64215c1a`，确认回滚事务可恢复 active map、词法索引与 manifest；修复后再激活 schema 5 版本 `2ce6661f40535ee4`，旧版本与现有数据均保留。
- schema 5 列举检索改为选择语义列表标题，并把标题、成员说明及对应公式按原始顺序组成证据组；formula 追问也复用同一列举路径，避免“系统误差的前四种方法”压过“标准差的四种计算方法”。
- Evidence support gate 增加“关系/联系/区别”、数量词和具体公式的语义支持判断；跨对象关系必须有同一证据明确表达关系，不能只因分别命中两个对象而判定充分。
- Resolver 对“再查查”“具体公式呢”“真的没有吗”等追问继承上一轮 resolved query，并显式触发重新检索，不建立无关新 topic。
- 线上回答生成不再把全部内容作为单个字符串调用模型：稳定约束使用 `SystemMessage`，问题、ConversationContextPack、EvidencePack 与实际工具结果使用 `HumanMessage`；没有成功工具结果时不注入空 Tool Context。同步与 SSE 流式路径使用同一消息合同。
- 验证：schema 5 最终 EvidencePack 人工黄金集 `22/22`，Recall@K `1.0`、point recall `1.0`、MRR `0.9091`；三个复现问法均为 `supported`。相关定向回归 50 passed，消息/工具/SSE 回归 33 passed。
- 同一 EvidencePack、同一 System/Human 消息在线对照中，本地检索约 `2.963s`；DeepSeek V4 Flash 为 `73.830s`、6556 completion tokens（其中 reasoning 5928），V4 Pro 为 `51.271s`、3216 completion tokens（其中 reasoning 2735）。两者均未误报“教材无依据”，引用 ID 均合法；Flash 输出更长且使用 3 个 Markdown 标题。共同上限为 8192；2200 的预跑会被 reasoning tokens 占满，不可作为质量对照。

## 2026-08-25 schema 5 关系题教学完整性修复

- 修复 schema 5 原子公式块在“联系 / 关系 / 区别 / 比较”类问题中被普通词面 rerank 丢弃的问题。检索现在只在主要教材内，把高相关正文与同章、同小节、距离不超过 2 个 IR block 且存在明确公式引导语的公式重新组成教学单元；辅助教材不会用局部邻接块挤占主要教材 EvidencePack。
- 关系题的正文锚点与公式按“解释 → 公式”顺序进入 rerank，避免 EvidencePack 的单章数量上限留下公式却丢掉符号解释。comparison 语义角色优先级补入 formula / derivation，但不放宽教材事实边界，也不从模型记忆补公式。
- 生成合同升级为 `generator-teaching-units-v1-2026-08-25`：关系题须按概念、数学联系、符号解释、直观含义和关键区别组织；所选证据含公式时必须实际展示并解释，禁止退化为“教材要点”摘录。
- 本地复现“标准差和随机误差之间的关系”时，最终 EvidencePack 保持 `supported`，并包含单次测量标准差公式 `σ = sqrt(Σδᵢ²/n)` 及其同小节解释。未调用付费模型做线上生成评测。

## 2026-08-25 图片任务模型配置语义修正

- 图片处理方式由“识图后交给推理模型 / 识图模型直接解答”改为“识图 / 推理分离 / 集成回复”。分离模式保留识图与推理两套配置；集成模式只展示一套同时支持文本与视觉的模型配置。
- 保留已有 `split/native` 环境值和 profile 字段以兼容旧方案。保存集成模式时，后端以集成模型同步推理与视觉兼容角色，普通问答、图片解析和图片回复不再需要两个独立模型选项。profile 仍不保存密钥。
- 验证：模型配置、连接、视觉桥接与错题图片 API 定向回归 `20 passed`；前端 TypeScript/Vite build 与 ESLint 通过。1280×800 和 1600×1000 实际界面确认集成模式仅一个“集成模型”分组，旧文案不可见，控制台无错误。

## 2026-08-25 Qwen 3.7 Plus / DeepSeek V4 Pro 受控对照实验基础设施

- 只读审查主聊天、Teach、Planner、Resolver、Evidence gate、工具和视觉路径的实际 Prompt/调用链；确认 Legacy Teaching Prompt 同时叠加证据、工具、引用、格式、教学流程和 intent 规则，且 Teach 与 generator 存在重复约束。
- 新增可回滚 `minimal-teaching-v1-2026-08-25`：仅在 `TEXA_TEACHING_PROMPT_MODE=minimal` 时启用用户指定的统一中文系统消息，保留相同 ConversationContextPack、EvidencePack、工具结果和必要引用协议；默认继续使用 Legacy 分支，未增加模型专属 Prompt 或改写 Planner routing。
- 新增独立 dry-run/online benchmark 脚本与 31 个固定 case（A=4、B=5、C=2、D=3、E=4、F=1、G=12），冻结消息、真实检索证据、工具结果和 SHA-256；线上运行必须同时具备两模型凭据并显式确认付费调用。
- 当前环境缺少 Qwen/DashScope 凭据，因而没有进行任何付费模型调用，也未生成或臆造模型胜负、token、延迟与成本结论。审查与方法报告保存在 `docs/benchmarks/qwen37-vs-deepseek-v4pro-20260825.md`。
- 验证：Minimal/Legacy prompt 切换、generator、follow-up 与工具编排定向回归 `48 passed`；离线夹具构建成功。Legacy generator/Teach 源码完整快照保存在 `benchmark_results/prompt_backups/teaching_prompt_legacy_20260825.json`。

## 2026-08-25 Qwen 3.7 Plus 集成视觉能力修正

- 修正模型能力目录把 `qwen3.7-plus` 误标为仅文本推理的问题；按官方 Image/Text/Video 输入能力补充 `vision` capability。集成回复仍复用现有单模型配置、OpenAI-compatible 图片消息和角色校验，没有新增模型专属视觉流程。
- 增加配置合同回归：模型必须同时暴露 text/vision 能力，native 模式保存时必须将同一 `qwen3.7-plus` 同步到 reasoning 与 vision 角色。该修复同时恢复设置页常用型号筛选及连接测试前的能力校验。
- 验证：模型配置、系统设置与视觉角色定向回归 `26 passed`；重启本地后端后，实时 `/api/system/settings` 已返回 `qwen3.7-plus` 的 `text` 与 `vision` 能力。

## 2026-08-25 Qwen 3.7 Plus / DeepSeek V4 Pro 在线受控对照结果

- 在相同 Minimal Teaching Prompt、冻结生产 EvidencePack / Context Pack / 工具结果、`temperature=0.1`、请求 `max_tokens=4096` 下完成 25 个文本 case × 2 模型 × 3 次，共 150 条文本结果；另完成 Qwen 原生视觉与 Kimi K2.5 VisualProblemIR → DeepSeek 各 3 次。原始响应、token、reasoning、TTFT、总延迟、成本估算与视觉阶段 trace 均已落盘。
- 普通教材 RAG 必需事实点召回为 Qwen `96.3%`、DeepSeek `92.6%`；12 轮 session 的模型阶段中位延迟为 Qwen `22.372s`、DeepSeek `42.290s`。Qwen 75 条文本无空答；DeepSeek 有 3 次长会话空答、5 次 length finish，空答均因 4096 token 全被 high-reasoning 消耗。
- Qwen 原生视觉 3 次均完成，但热电偶分度表题三次都把约 `492.4–492.5℃` 算成约 `490℃`。Kimi 三次均正确生成结构化题图 IR，后续 DeepSeek 三次均在 4096 reasoning token 处截断而无正文；未为改善任一模型临时调 prompt、reasoning effort 或输出上限。
- benchmark 续跑合并键补入 `group`，避免 A/B 中同名 case 被去重；从 append-only JSONL 无付费重建出完整 150 条记录。新增确定性分析脚本与聚合 JSON。最终报告位于 `docs/benchmarks/qwen37-vs-deepseek-v4pro-20260825-final.md`，建议 Qwen 作为默认文本 reasoning 小流量试运行、DeepSeek 保留回退，精密视觉题继续要求可验证表格/计算证据。

## 2026-08-25 Qwen Teaching Prompt 三 preset 对照

- 新增 `refined-teaching-v1-2026-08-25`，保留教材/工具事实边界、引用、证据不足、例题真实性、LaTeX 和克制格式合同，删除 Legacy 中重复的 intent 流程、固定教学步骤和中英混排长规则。Legacy 仍为默认并可直接回滚；`minimal`、`refined` 以及 `fine-tune` 兼容别名均可显式切换。
- Generator 与 Teach 子图统一支持三套 preset；Compact 路径继续使用相同的有界 ConversationContextPack、EvidencePack 和工具结果。修正 Teach 子图在 Minimal/Refined 下仍记录 Legacy prompt 长度的问题，context telemetry 现在保存实际 preset、system/human 字符数和 prompt version。
- 仅使用 Qwen 3.7 Plus，在 `temperature=0.1`、thinking 开启、`max_tokens=4096` 下对 A/B/G 的 18 个真实模型 case 各重复 3 次。Minimal 54 条经 message SHA-256 全量匹配后复用；Legacy 与 Refined 新增 108 次调用，零错误，原始回答和 telemetry 全部落盘。
- Refined 相比 Legacy 的总延迟中位由 `37.012s` 降至 `20.794s`，reasoning token 降低 `50.5%`，正文字符中位由 `643` 降至 `301.5`，按北京原价估算由 `¥1.2501` 降至 `¥0.6900`。逐题复核未发现 A/B 教材事实或引用的实质退化；G 组错误 context 上的无关扩写明显减少。
- 验证：Teaching Prompt / generator 定向回归 `18 passed`；benchmark 三套均为 `54/54` 成功、无无效引用。最终报告位于 `docs/benchmarks/qwen37-prompt-presets-abg-20260825-final.md`，完整原文位于 `benchmark_results/qwen37_prompt_presets_abg_raw_20260825.md`。

## 2026-08-25 Refined Teaching Prompt 与 Qwen 3.7 Plus 转为默认

- `TEXA_TEACHING_PROMPT_MODE` 未配置时由 Legacy 改为 `refined-teaching-v1-2026-08-25`；`legacy` 和 `minimal` 仍可显式选择，保留一键回滚与 benchmark control。
- 未配置模型角色时，reasoning 与 vision provider 均默认解析为 Qwen，默认型号为 `qwen3.7-plus`；Qwen 3.7 Plus 的正式 ModelSpec 启用 `enable_thinking=true`，与受控实验条件保持一致。显式保存的用户 profile、DeepSeek legacy 环境变量和自定义 provider 继续优先于默认值。
- `.env.example` 改为 Qwen 3.7 Plus 双角色示例。多模态模式的未配置默认仍为 `split`，避免把既有 reasoning-only / 分离式配置静默解释成集成模式；当前本机已保存的 `native` Qwen profile 不受影响。
- 运行态解析确认：Teaching preset 为 `refined`，active reasoning 为 `qwen/qwen3.7-plus` 且 thinking 开启；空环境也解析为相同默认。模型配置、Prompt 切换与缓存定向回归 `25 passed`。

## 2026-08-25 学习问答 Harness 状态门槛

- 新增持久化 `LearningTask`：普通问答与图片题统一记录 goal、required inputs/outputs、artifacts、checkpoint 和 verification。图片 VPIR 增加结构化 `required_inputs`；缺少会影响结论的附表、附录、另一页或模糊区域时，在调用推理模型前进入 `waiting_for_input`。用户可补充新材料后恢复原任务，或选择只讲方法；原图和原 VPIR 不重复解析，未核验数值必须显式标注。
- 最终答案增加确定性后置验证：检查分项覆盖、本轮引用 ID、数值是否由数学工具或输入证据支持。验证未通过不会静默当作完整答案；任务进入 `degraded`，并在正文披露未满足/未核验项。
- 工具编排从“任一工具成功”改为逐工具 `required_outputs` 门槛。三个写入提案使用持久化 pending action、白名单执行、action id 幂等确认和拒绝终态；主聊天直接展示确认区。即使后续推理模型连接失败，已经形成的操作提案仍会保留，处理后同步刷新会话中的任务投影。
- 学习状态不再因“已生成回答”直接推进：未验证回答只记录概念接触；章节完成仅在 answer verification 通过后更新，掌握度和间隔复习仍要求显式用户评分或实际作答结果。
- 验证：后端全量回归 `565 passed`（仅 1 条既有 Starlette/httpx2 弃用警告）；前端 `19 files / 91 tests passed`、ESLint 与 TypeScript/Vite 生产构建通过。实际 Learning Canvas 在推理服务不可用时仍显示“确认后才会写入学习记录”，取消后稳定显示“已取消”，没有新增任务中心或独立 Agent 页面；冒烟测试产生的 3 条会话、task、action 与 trace 记录已精确清理。

## 2026-08-25 学习问答 Harness 生命周期与答案契约

- Context Eval 升级为 schema 4，新增不调用模型的 LearningTask 生命周期层，覆盖阻断输入、补充后恢复、中断检查点、method-only 降级和验收失败。报告拆分 `offline_passed` 与 `production_passed`；未显式运行在线 Answer Eval 时，顶层生产发布门槛不再可能通过。
- 普通问答支持停止后的同任务恢复。中断时保存原 task/turn、partial、最近阶段和检索后的证据状态；恢复使用原 turn，并从检索检查点重新生成完整答案。同 turn 的 complete 投影覆盖 partial，不重复写入用户问题。前端只在原答案下方显示“继续本次解答”。
- required outputs 增加公式与目标单位合同；后置验证检查完整 LaTeX 公式、最终结论单位，以及引用附近的结论是否与对应证据存在语义重合。无法确定性证明的数值仍保持 `unverified/degraded`，不提升为精确答案。
- 动态工具循环没有扩展为开放式 Agent Loop。只保留由数学工具显式 `verification_request` 触发的最多一轮校验补偿，并在 execution trace 记录 follow-up 轮次和策略；其他缺材料继续进入 required inputs。
- 验证：后端全量 `569 passed`（1 条既有 Starlette/httpx2 弃用警告）；前端 `19 files / 91 tests passed`、ESLint 与 TypeScript/Vite 生产构建通过。前端测试首次受 Windows 沙箱 `spawn EPERM` 限制，授权后原命令通过。
- 重生成的 schema 4 离线报告如实为：生命周期 `5/5`，生产检索 `14/15`，Answer `0`；因此 `offline_passed=false`、`production_passed=false`。当前失败项是电容式传感器优点 case 未覆盖“温度稳定性较好”，未用生命周期改造掩盖既有检索回归。

## 2026-08-25 枚举题小节标题证据修复

- 定位 `prod_sensor_capacitive_advantages`：目标 chunk 已存在于索引、融合排序和最终候选，缺失发生在 EvidencePack 文本投影。该条正文只解释稳定性原因，“温度稳定性好”位于 `1. 温度稳定性好` 小节标题；枚举题此前只为显式 list group 补标题，导致模型与 Eval 看不到条目名称。
- 枚举型 factual recall 现在会保留真正编号条目的小节标题；编号判断排除 `11.1.4` 这类章节号，避免无关章节被误当作第 11 条枚举项。未修改索引、数据集期望或 EvidencePack 字符预算。
- 验证：定向检索 case 通过、缺失证据点为空；真实生产检索 Eval 恢复 `15/15`，生命周期 `5/5`，`offline_passed=true`。未运行付费 Answer Eval，因此 `production_passed=false` 保持正确。后端全量 `571 passed`（1 条既有 Starlette/httpx2 弃用警告）。

## 2026-08-25 学习任务停止竞态与恢复界面终态

- 普通问答停止改为显式中断确认：前端取消 SSE 后先进入不可恢复的 `stopping` 本地状态，后端完成幂等 checkpoint 并返回 `interrupted` 后才显示“继续本次解答”，避免立即继续命中 `learning task is not resumable: running`。
- 每次生成拥有独立 `active_run_id`。一旦停止已确认或新恢复轮次取得任务所有权，旧 SSE 后续到达的 checkpoint、完成或异常都不能覆盖当前任务；补充并发回归覆盖“旧模型调用稍后失败”仍保持 `interrupted`。
- 普通问答和图片题恢复开始时立即把任务投影切为 `running`，补充材料选项不再在新一轮流式输出期间残留。`done`、SSE `error` 和传输错误都会收敛恢复 activity，状态条不再永久显示旋转中的“从检查点恢复”。
- 验证覆盖中断接口幂等、partial/checkpoint/会话投影保留，以及恢复 activity 的成功和失败终态。本地 Learning Canvas 冒烟验证停止确认无竞态、恢复操作即时收起；隔离后端无法连接外部推理模型，因此真实成功生成由状态投影测试覆盖，失败路径在界面中确认停止旋转并显示明确终态。
- 最终回归：后端 `573 passed`（1 条既有 Starlette/httpx2 弃用警告）；前端 `19 files / 93 tests passed`，ESLint 与 TypeScript/Vite 生产构建通过。冒烟测试产生的 3 条会话、4 个 task 及对应 event/trace 已精确清理。
