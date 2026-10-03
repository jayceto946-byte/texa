# Session → Note P0 实施与验收记录

2026-10-02。依据 `session-note-p0-sol-handoff.md` 实施。状态：核心工程、macOS Electron 三尺寸与故障恢复、macOS 发布候选包读写及 DMG/ZIP 检查已完成；真实模型检查见本轮独立报告，Windows 与人工语义签审仍待完成，不能标为 P0 全部验收通过。

## 已落地行为

- 主会话顶部和历史会话行提供“整理为笔记”。预检读取权威消息表，按完整 turn 选择，支持独立分页的范围选择器、已完成轮次、已有笔记/草稿、来源警告与预算。生成不增加聊天 turn、不结束会话。
- `/notes` 管理已保存、草稿、归档；筛选与游标保留在 URL，列表不返回正文。教材与版本化章节筛选选项来自全部对应状态笔记的元数据，不受当前分页限制；选项读取失败不阻断正文列表。
- `/notes/drafts/:id` 展示后台进度、取消确认、失败/中断/取消后的同快照重试或手动整理。已有内容可在模型离线时编辑。编辑采用块模型，复用 Markdown、KaTeX、数学输入与来源面板；不建立新的回答生成入口。
- 编辑约 800ms 后串行自动保存草稿，以 draft revision 做 CAS，陈旧响应不覆盖新文字。正式保存先 flush，绑定操作回执与当前警告 acknowledgement；保存前不进入正式笔记列表。冲突保留当前文字，可复制、重试或重新读取。
- 正式 Note 独立 ID、不可变 revision、归档/恢复及历史版本只读。版本引用保存的来源快照；原会话/教材缺失仍能阅读。人工修改降级对齐，新增块标为 user_added，重新排序不冒充重新验证。
- 来源 Inspector 展示生成时原文、角色、回答状态、教材片段/unknown 和当前来源位置；用 message ID 定点跳回聊天并可前后分页。移动仅沿已记录 split 链解析。不同回答的 E1 有独立命名空间。
- 笔记动态路由共用一个缓存槽；生成轮询仅在可见且活跃时继续。最多保留一份失败自动保存编辑器及 20 个阅读位置。离开链接先 flush；刷新、关闭窗口、退出、更新安装、后端重启前保护未保存草稿，关闭握手有超时及 nonce/sender 校验。

## 存储、任务与依赖边界

`PROGRESS_PATH/session_notes.db` 新增 schema 1，登记到 storage manifest。六张表为 session_notes、note_revisions、note_drafts、note_source_snapshots、note_relations、note_operations。首次打开 Notes 服务时创建独立库；不迁移原会话、错题、Goal 或教材库。高于当前版本的数据库拒绝写入。正式保存的 Note、revision、关系、草稿发布和幂等回执在单事务中提交。

完整选区从 SQLite 同一读取事务分页冻结，不依赖 40 条兼容 JSON 或 5000 条 load_full_history。来源包上限 8 MiB；可编辑文档上限 512 KiB、300 块，超限拒绝，不截断保存。来源保留消息 hash、watermark、旧教材版本/片段及排除清单，识别到的凭证、本地用户路径和 thinking 经过过滤。

生成复用现有模型角色/工厂与 JobManager：最多 8 次抽取 + 1 次组织、单次最多 90 秒、总计最多 600 秒、零自动重试，实际输入/输出按保守预算检查。候选先写 Notes 库，再以 Job complete CAS 裁决取消竞争，最后匹配 hash 发布为 editable。重启只补发布已完成候选，其余转为中断；不自动重跑模型。后台错误只记录稳定代码。可选 RuntimeEvent 写失败不改变已提交的保存回执。

教材章节按 book_id + Canonical hash + heading block 锚定；无精确锚点时保留 legacy/unresolved，不按序号、同名标题重绑。用户新增分类仅允许服务端解析出的当前锚点，分类不升级为事实证据。

标准备份包含新库、来源、草稿和历史版本，复用 SQLite backup API；恢复前只读校验 schema 与引用完整性。旧备份没有 Notes 库是有效情况。备份可能截获跨库发布中间态，由启动 reconciliation 处理。回退旧应用时应保留完整数据备份及新 Notes 库，不尝试把 schema 1 降级写入。

Notes 列表/阅读/编辑不构建模型客户端、向量库或 KG；不自动写 ConceptMemory、Goal、错题、掌握度、学习完成事件或 SM-2。不改 Resolver、EvidencePack 或索引格式。未增加依赖。打包后端已有 backend/memory/utils 子模块收集路径覆盖新增模块；desktop 新握手模块显式列入打包文件。

## 验证证据与限制

- Python 使用 `venv310/bin/python`，3.10.21。Notes 领域、API、版本/CAS、取消、恢复、故障注入、备份及历史/来源/Job/迁移回归共 109 项通过（86 项 Notes/存储/Job/备份/来源回归 + 23 项会话引用回归）。
- 冻结来源覆盖 20/40/80 轮及 5200 条消息；另覆盖两条 E1、消息变动/移动/缺失、IR 换版与章节重排、事务回滚、候选写入/完成/发布故障、坏 JSON/引用、超预算、警告确认与备份恢复。
- 前端 Vitest 29 文件/134 项、TypeScript、全量 ESLint、Vite 构建通过；新增自动保存和安全数学/表格/HTML/链接/外部媒体渲染回归。构建仍有既有 Markdown 动态导入和大 chunk 警告。
- Desktop 14 项测试通过，含 4 项关闭握手与 3 项跨端口首次配置完成标志测试。端口测试需本机 loopback 权限；没有更改依赖或开放外部端口。
- Python compileall、desktop 语法及 diff 空白检查通过。
- 实际 macOS Electron：隔离数据目录内完成预检、模型替身生成、自动保存、警告未确认阻止正式保存、独立笔记、第二份同来源笔记、版本 1→4、历史版本只读、归档/恢复、来源 Inspector、超过近期 40 条窗口的旧消息定点跳转、后续分页和返回笔记。1280×820、1024×768、760×820 均实看长中文/长标题、公式、矩阵、GFM 表格；后两个尺寸检查 Inspector，760px 检查抽屉与编辑。空列表、生成进度、生成失败/手动整理、取消终态、失败保存与禁用状态已实看；没有宣称每种状态在每个尺寸都覆盖。
- 故障恢复：草稿写入故障阻止 Cmd+Q，当前标题仍保留；解除故障后重试成功，退出/重启可继续编辑并保存版本 4。在确认 Job 为 running 后崩溃隔离后端，恢复为 interrupted，活跃任务数为 0，来源保留且不会自动重跑。恢复会回到学习页，可从草稿列表继续。新动态端口不再重复首次引导。
- 发布候选包：macOS arm64 的真实打包后端正常启动；离线列表、阅读、数学/表格、编辑自动保存及版本 5 提交通过。ASAR 六个桌面模块与源码逐字节一致。DMG checksum VALID，ZIP 全文件 CRC 检查通过，ZIP 内 ASAR hash 与实测应用一致。沿用项目 identity=null，候选未签名/公证、未发布，未安装到 Applications、未测试升级器。Windows 没有可用主机，未实测。
- 12 份六类代表性会话位于 `tests/fixtures/session_notes/representative-v1.json`，均明确为 synthetic/offline、human_review=not_run。相关测试只验证快照、来源合法和警告，fake model 不证明内容组织质量。尚需人工逐份审阅条件、公式、推导、纠正和未决问题的保留，以及指代补全和无新增事实。
- 用户已明确授权最多 12 次真实模型调用、零自动重试、仅 12 份合成文本出境。独立结果保存在 `artifacts/session-note-p0-acceptance/real-model-2026-10-02/`；其合同检查和代理审阅不替代人工签审。没有迁移真实学习数据，凭证仅在进程内读取，不写入报告。

## 本轮验收中修正的问题

- 历史来源跳转增加安全校验过的“返回笔记”入口，保留历史 revision；外部地址和路径穿越不能作为返回目标。
- 警告未确认只显示确认提示，不再冒充版本冲突；保存故障保留复制/重读动作，提示当前文字仍保留。修改内容清除过时的一般错误。
- 预检返回的选择保留 scope 排除轮次，使再次捕获产生相同的排除清单与 fingerprint，避免误报“来源已变化”。新增含被排除轮次的申请回归。
- 首次配置完成标志在桌面用户目录原子保存为 `setup-complete.json` 的 `{version:3,complete:true}`，不含凭证。旧端口上的 localStorage 标志可迁入；后端仍验证回答模型与所需凭证配置，IPC 只接受主窗口 sender。模块已列入正式打包清单。
- 取消/中断与候选发布失败显示中文状态和恢复动作，不直接显示 JobManager 的英文消息或内部恢复码。

## 剩余验收

Windows 实机、人工逐份审阅 12 份真实模型输出及签审仍待完成。六类合成输入和 review_checks 保留原有 human_review=not_run；不能把本轮 fake model、合同通过、代理审阅或真实模型一次抽样写成人工审阅或整体模型准确率。

macOS 候选包另已保留在 `artifacts/session-note-p0-acceptance/release-macos-arm64/`，实际测试应用位于 `/private/tmp/texa-note-p0-check/release/electron/`。构建使用 venv310 与现有依赖；本机缺 npm，仅在临时目录取用官方 npm 10.9.3 构建工具，无项目依赖重装。候选先使用临时复制的正式构建配置，后刷新文件清单并确认新增模块已打入 ASAR；正式仓库打包配置完整。验收数据均在隔离目录，未覆盖已有发行包或用户学习库。

产物 SHA-256：

- ZIP：`dd7d291e39556bf5059f7e0def7c2a93d2d7cdfae0a924302d5abe01d5f6282b`
- DMG：`9b80e98df7e3c38510f30112f938574a983dda78d6d7dff041bc9913cde35f7e`
- ASAR：`9156e4b36bd3757d6e201c8d38db3dc129697b2808a7855b9b9056d85fddabbd`

本次真实模型 12/12 次调用、零重试，结构/引用合同 12/12 通过；代理逐份审阅 10 份未发现目标项缺失、1 份需裁决、1 份新增来源外“两列”性质。人工签审保持 not_run，模型质量门槛仍未放行。详见 `session-note-p0-acceptance-report.md`。

2026-10-03 按用户限定的两项处理将生成 prompt 升至 `session-note-structure-v2`：明确允许内容重组/等价表达，禁止新增未讨论知识或计算检验步骤；纠错区分用户明确确认与助手推测，并要求引用确认消息。抽取与合并使用同一规则。现有 Notes 42 项离线回归通过；未新增真实调用，v2 语义改善尚未实测。已有笔记、v1 输出与验收结论保留；此前 DMG/ZIP 仍是 v1 候选，未重新打包。
