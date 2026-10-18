# Sol Implementation Handoff — D-01

2026-10-17 · **设计已交付，尚待用户批准S1/S2；没有启动实现或委派Sol。**

三份交付：[Candidate Contract](candidate-contract-specification.md) · [Projection & Review](projection-review-design.md) · 本文件（任务、冻结验收及决策摘要）。

## 1. 简短决策摘要

| 问题 | 本轮决定 |
|---|---|
| 要解决什么 | 完整教材例题被直接作为独立题干；块/资产身份在候选阶段丢失；内容风险与元数据混杂；批量入库被误当人工核实 |
| 新增能力 | IR来源可追溯的题干/答案/解析提案；required/reference/uncertain资源关系；内容状态与显式确认分离；只对异常题定向校对；v1教材候选写库前门槛 |
| 不解决什么 | OCR/原PDF语义正确性、自动解题、所有复杂例题全自动拆分、全库质量认证、F3正式图片读取、去重策略缺陷、旧入口全面强制校对 |
| 最小字段增量 | 候选可选projection/issues/review；extract可选canonical_hash/source_blocks；分析/提交可选candidate_contract_version及版本回显；提交项可选candidate_context；既有批次JSON可选candidate_receipts |
| 是否需要数据库迁移 | **不需要SQL迁移**。不新增表/列、不改旧记录；S2只给新导入批次JSON增加最小回执。JSON增量仍是明确的持久化合同变更，不能称“零存储变化” |
| 是否修改既有学习/题库合同 | LearningUnit、IR、Runtime、ExerciseRecord与练习状态语义不变；扩展候选DTO和批次回执，新增v1教材导入准入。旧入口行为保留但不享有新保证 |
| 对108条的预期 | 仍以108个原source unit为差分锚点，不靠删除问题题改善数字；94条无源答案保持空answer/explanation；14附解例题分离或明确待校对；92条原可用题保全；16重复仍正确。不能预先承诺修复16/16或自动入库108条 |
| 哪些仍需人工 | 无标记/同块解、跨节终点、前例条件、图归属/组合裁图、源公式碎片和数值争议；必要图片未交付者保留候选 |
| 用户需要确认的取舍 | 确认本设计后才实施；特别是“v1未解决题不入库”“旧客户端继续legacy行为”“最小回执写已有批次JSON”以及接受F3未完成带来的暂缓。它们不是生产启用/数据迁移授权 |

用户本轮明确要求“完成后等待确认，再交给Sol实施”。本轮只有文档写入与静态检查，没有源码修改、模型/OCR调用、数据库写入、历史重导、索引变更、提交或推送。需要突破保护边界的后续工作必须单独说明理由、影响和替代方案。

## 2. 实施证据与限制

- 当前主目录分支 `Texa_MacOS`、HEAD `c0673fc75d938bce25304a08aac8c70a70c11f18`；Python环境 `venv310` 3.10.21。当前已有其他任务未提交UI文件及patch_notes，不能重置/覆盖。
- 原因入口：`memory/textbook_exercise_importer.py:91–93,688–700`；完整材料定义：`ingestion/document_workflows.py:87–131`；IR来源：`ingestion/document_ir.py:129–217`。
- 候选/DTO已有正文槽：`memory/exercise_importer.py:29–49`、`backend/schemas.py:291–311`、`frontend/src/types/index.ts:341–362`。
- 原UI已有编辑、对照、拆并：`frontend/src/features/exercises/components/CandidateReviewWorkspace.tsx`、`hooks/candidateOperations.ts`、`hooks/useExerciseImportCandidates.ts`。不得复制第二套状态机进ExercisesPage。
- 写入入口只过滤空题干：`backend/api/exercises.py:453–461`；已有原子批次：`memory/exercise_bank.py:280–341`；未知提交恢复：`frontend/src/pages/ExercisesPage.tsx:373–397`。
- `question_fingerprint` lower并去空白（`memory/exercise_bank.py:61–63`），本轮不能改。投影显示包装可能改变指纹，必须差分验证原16条，不得用修改算法掩盖。
- 正式图读取缺口是[F3独立待办](../../qa/r1-r2-post-approval/F3-exercise-images.md)，既有教材图端点不自动变成exercise附件合同。
- [R1/R2批准记录](../exercises-production-r1-r2/astra-review-2026-10-17.md)只保护现有构图，新增状态仍需局部Electron验收。本轮查看的是已有1280来源对照截图，不是新合同实现。

## 3. S1 — Candidate Projection

交付目标：在显式v1分析路径返回可追溯候选提案；明确解块分离、来源/资产保留和不确定性表达可验证。**S1单独完成不代表新版候选可以安全投入正式导入**；新UI的默认v1请求须与S2一起交付。

### 修改模块与最小字段

| 模块 | 具体工作 |
|---|---|
| `memory/textbook_exercise_importer.py` | 同次Canonical读取给投影器传块与版本；保留原units.text；纯函数投影/串行化/来源覆盖检查；有界邻接归并R16/R19，不改全局learning_units |
| `memory/exercise_importer.py::ExerciseCandidate` | 增加可选projection/issues/review；原有三个正文槽复用；元数据分析用投影后题干；关闭新增自动LLM路径 |
| `backend/schemas.py` | CandidateOut三个可选字段；分析请求版本与响应回显；有限嵌套DTO校验，不增加数据库模型 |
| `backend/api/exercises.py` | 只传版本、映射结果和异常，保留legacy分析；可选旧LLM修复不得丢弃/伪造新来源与确认 |
| `frontend/src/types/index.ts` | 同步可选类型；S1不切换正式UI默认请求、不修改R1/R2布局 |
| `tests/test_textbook_exercise_importer.py` + 本域新测试文件 | 合成IR投影、来源覆盖、顺序/页/bbox、公式/表格、无解负例、legacy兼容 |

默认 `use_llm=false`。若v1收到 `use_llm=true`，本交付明确返回“此合同暂不支持模型辅助修复，请关闭后重试”，不默默掉到会遗失投影的 `refine_low_confidence_candidates`，也不新增付费调用；legacy显式模型流程保留原行为但不在本次测试中调用。

### 正常、失败和兼容

- 普通习题整题保留、无源解不填答案；独立解块进入explanation，明确答案块才进入answer。全部块可回查，源无变更。
- 同块混解/无marker/跨节/前例/资源归属不清→unresolved及具体issues；保留完整材料，不输出伪完整题干。
- active manifest与Canonical不符仍按现有行为报错；缺块/超预算/缺来源不给v1 ready，不偷换fallback来源。
- 旧分析无version，DTO新增默认null，不强制旧文件/手工流程提供IR。不将“旧字段存在但缺新合同”认作结构通过。
- 方程显示修复局限候选序列化；**已经可正确显示的正文尽量逐字保持**，特别是原16个重复。只有明确块级显示缺失/错误才增加必要display包装，不统一改写所有公式。必须同时满足源token保真、块显示语义与重复验收；若三者冲突，停在候选校对并报告具体冲突，不能改fingerprint或在全局renderer打补丁。

### S1自动化与真实差分

1. 现有workflow测试保持“LearningUnit含完整解”断言；另测candidate独立投影，不能删旧断言让测试变绿。
2. 覆盖R01–R19对应结构输入，附加source mapping、空图块、公式display与table空列断言。严格分离测试与安全降级测试分别报告。
3. 校验重复调用相同IR输出相同投影/issue键（排除UUID），hash与Unicode span稳定；metadata分析不再吃完整解。
4. 隔离同源108差分按第5节执行；所有基线输入和真实库保持hash不变。不拿新IR适配器重跑后得到的更好来源替代本基线。

### S1完成标准 / 回滚

v1分析有具体提案，来源覆盖、94无虚构答案、92无退化、14分离或定向校对、五边界逐项有处置、16重复不退化；保护模块无变化。遗留FAIL按测试账本公开。S1不能以只加警告而完全没有C001式明确块分离能力交付。

回滚仅撤销本交付新增v1分支/DTO支持或保持UI不请求v1；旧分析继续运行，不变更IR/索引/题库。工作分支成果审查后整合Texa_MacOS，不能切到另一工作区运行并称已交付。

## 4. S2 — Content Validation & Review

交付目标：在现有R1/R2校对工作区使用新合同，正常题批量采用、异常题定向修正，服务端v1准入与持久化最小回执一致。

### 修改模块与最小字段

| 模块 | 具体工作 |
|---|---|
| `backend/services/exercise_candidate_review.py`（建议新增本域服务） | 不依赖FastAPI DTO；复核IR身份、来源/正文/依赖、人工确认hash与问题解决条件；计算可提交项。不是Runtime/Agent |
| `backend/schemas.py` | BatchAdd版本、ExerciseAddRequest可选candidate_context；批次返回可选candidate_receipts；version显式校验 |
| `backend/api/exercises.py` | 新增`/candidates/batch-add`协议入口，复用原bank事务；v1写入前调领域服务；旧batch-add/单题add携带v1 context时拒绝；409/422定位候选；普通旧请求仍legacy |
| `memory/exercise_bank.py` | 仅add_batch接收服务端准备的最小回执，保存/跳过重复的实际ID决定回执归属；与原题目/批次同事务。不得改fingerprint、练习状态机、旧记录 |
| `frontend/src/features/exercises/hooks/candidateOperations.ts` | typed问题分类/筛选、来源保全拆并、内容修改使确认失效、合法提交集合纯函数 |
| `.../hooks/useExerciseImportCandidates.ts` | 一起持有只读source registry；按确认回执移除已提交项，保留未解决项；React updater无副作用 |
| `.../components/CandidateReviewWorkspace.tsx` | 原区域内分组显示风险、定位本题原文、建议答案/解析、当前题确认、提交子集数量；保留原构图 |
| `frontend/src/pages/ExercisesPage.tsx` | 页面装配：显式请求v1/核对回显；向新协议路由传candidate_context；已解决项提交，未知回执保持锁定；既有批次核对显示来源回执 |
| 本域CSS/TS类型/测试 | 只为新增状态调整本域；不改AppRail、MainLayout、ApprovedWorkspace、StudyDesk或全局markdown |

### 正常、失败和兼容

- `ready + review=null`普通题可提交，回执system_proposed；用户主动确认当前版本才user_confirmed。不存在“全选→全部人工已核对”的转换。
- 结构待核对题留候选，未解决required图不能通过一次确认越过；只有参考资料缺失/元数据问题不阻断。
- v1服务器重验，不信任前端issues数组；非法/过期hash/源版本变更拒绝整次选定提交集合，零部分写入。重验依赖只在教材分支加载。
- 并发修改发生于确认之后即清空review；编辑期间提交锁定，过期服务响应不得覆盖新编辑。请求内容冻结后直到回执解析结束，维持同批次/同书身份。
- 保留旧batch count/skipped/batch_id协议，未提交者不计入selected submitted count；更新UI回执完整性检查以本次实际提交集合为分母。
- 新旧客户端组合按Contract §5.3；新客户端发现旧后端不回显版本即不做新合同导入，分析后服务端降版时新提交路由也必须404而非回落到legacy，不用客户端单方面标签冒充后端门槛。
- 回执持久化失败与题目写入一起回滚；不先写题再补回执。后续读回执对正文hash失配只显示历史导入事实，不对当前内容宣称已核对。

### S2自动化与Electron验收

| 层 | 必须覆盖 |
|---|---|
| 领域服务 | 问题分类与多问题并存；确定性/人工路径；空答案/标签不阻断；缺图不能确认绕过；合法span/未知块/换版/用户改写；正文与projection哈希不可混淆 |
| API/存储（临时DB） | v1缺context/伪造ready/删issues/过期review/未知版本/跨书span拒绝；新后端legacy请求仍通；旧后端新协议路由404不写入；失败零写入；正常批量+真实精确duplicate skip；回执与数据原子提交/回滚；不影响既有单题/练习入口 |
| 前端纯逻辑 | 所有内容编辑清确认，metadata改动不清；split/merge不继承确认/不丢源解；集合统计交集独立；提交子集后待核对仍保留；review生成只来自明确点击 |
| 组件交互 | 分离题干/解析可对照、风险定位、修正后确认、图缺失阻断、空答案普通题零额外步骤；键盘/焦点；不把needs_review改成verified |
| 提交恢复 | 完整回执仅移除已保存/duplicate skipped；回执不全、请求超时、连接断开保留当前候选；现有核对入口可追溯该批次，不自动重发 |
| 实际macOS Electron | 1280×820 / 1024×768 / 760×820，正常题、C001式分离、C031式缺图、C096式混解、长式/表格、混合选择、旧合同提示、未知提交；真实108隔离副本可定位原来源，必要内容无裁切 |

前端使用项目现有测试/lint/build命令；Python必须venv310 3.10。源码检查不是Electron运行结果；记录实际平台、数据源、版本与未测项。无付费模型、OCR、Windows实测或安装包更新测试时明确NOT TESTED，不能借R1/R2历史批准签核新状态。

### S2完成标准 / 回滚

S1全部门槛保持，新合同身份/确认/服务端准入及最小回执一致，普通题没有额外逐题负担，16个问题候选不会静默成为可靠独立练习；矩阵每项有结果与已知限制。批准的是局部设计，工程通过不能自动称新的Astra DESIGN APPROVED。

回滚前先处理当前未提交候选：保留页面内容/提供手动复制，不自动转换为legacy后提交。关闭新v1入口只影响新分析；既有新批次JSON旧代码能忽略额外字段，已导入Exercise仍走原合同。只用原batch rollback入口回滚用户明确指定批次，不删除全部新题、不改源IR/索引/旧题。旧程序修改批次必须保留未知JSON键；若其会重建并丢弃candidate_receipts，则暂停降版该写路径并报告，不能声称无损回滚。

## 5. 冻结基准与分层验收

### 5.1 冻结身份

来源：[dataset-manifest.json](../../qa/question-extraction-quality-2026-10-17/dataset-manifest.json)、[candidate-audit.jsonl](../../qa/question-extraction-quality-2026-10-17/candidate-audit.jsonl)、[summary.json](../../qa/question-extraction-quality-2026-10-17/summary.json)、[regression-cases.json](../../qa/question-extraction-quality-2026-10-17/regression-cases.json)、[contract-probe-results.json](../../qa/question-extraction-quality-2026-10-17/contract-probe-results.json)。不得修改这些原基线及旧runner来伪装修复。

| 输入身份 | 冻结值 |
|---|---|
| dataset | TEXA-D01-01；108候选；agent source reviewed=108；human reviewed=0 |
| Canonical文件SHA256 | `5bcef61474112840c4513441ba13f81e05d535c1599819a86f7fa30ebd305b2e` |
| Canonical逻辑SHA256 | `89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3` |
| 来源题库逻辑SHA256 | `80ab5d5f62de49b36b331a39001e15ebfbc71c157932f30747daf6692f0411a3` |
| 候选集合hash（排除随机ID） | `bd8e06d3aef90488cf4ab10a12d987a950fd72dbc49e4f0b03057eeabaf41377` |
| 请求 | chapter空、pages null、source_mode=exercise_sections、limit=200、subject空、use_llm=false |
| 旧适配版本 | mineru-structured-content-v1；不得用现源码v3重适配后替换基准 |
| synthetic与probe文件SHA256 | regression：`9908a6405f8af397a976c1f62c4128229ae9152c1768779326ca29d94d9b4570`；probes：`a353e17fd02fb814319ddbcf3018fb26e2c9f5b00da80dc63742842196db7cd8` |

其余来源包/脚本身份沿用原manifest与verification，不新拷贝教材原文。

差分按 `canonical_hash + 原unit_id + 原unit文字hash` 对齐，不按candidate随机UUID或列表序号。拆分/合并要列原unit→新候选一对多/多对一映射；不得丢候选、靠少输出降低错误率。默认预期108个原单元均有去向，复杂题仍可保留单个unresolved候选。

### 5.2 真实108最小矩阵（交集不能相加）

| Gate | 集合 / 分母 | 验收合同 | 证据 |
|---|---|---|---|
| G01合法候选与可用保全 | 全108；原结构可用92 | 108来源均有映射；92不得新增截断、缺条件、误拆或元数据导致的人工阻断 | 逐题正文差分/源角色覆盖，不能只看总数 |
| G02无源答案 | 94个kind=exercise | 未人工编辑时answer和explanation都保持空，不生成补全；普通题可批量 | 逐项空值+无模型调用 |
| G03带解例题 | C001–006、C091–098（14） | 明确部分实际分离且源可追溯；其余具体content风险+不可直接入库；未知不能算分离成功 | 分列auto-separated / user-confirmed / unresolved，三者总数14 |
| G04边界 | C033、C091、C092、C093、C096（5） | 每项单独关闭或显式保留待校对，绝不被整体均分抵消 | 下面逐项表 |
| G05必要输入 | C031、C092–098（8） | 未embedded必需输入仍待补充，图不能靠路径/图题假完成 | 依赖kind/requirement/identity/分离后仍缺什么 |
| G06资源关系 | C031、C091–098（9） | 源图存在≠题库图可读取；已知归属冲突不静默绑定；reference/required分开 | block IDs/图号/asset IDs/组合关系；C066为负例 |
| G07数学表示 | C091/C093/C094/C096（4）；42个源公式块 | 源token和角色去向保全；9个tag错误逐项修复或明确未解决；6个未识别节点逐项恢复/说明源缺损，不允许删除隐藏 | math AST/KaTeX + 实际Electron显示；源语义另表 |
| G08表与跨页 | C003/C004/C020/C021等 | 已有表、空列、行/列位置、公式与子问不丢；C020跨页完整 | 结构值、角色映射、渲染截图 |
| G09真实重复 | C007–022（16） | 全16仍指向原库对应记录、默认skip；不减少源信息、不产生新的误合并 | 逐项duplicate_of映射与隔离batch结果 |
| G10提示分类 | 全108；旧W93/K92/D16 | typed metadata/content能独立表达，89个仅有旧警告但结构可用者不被当坏题；12个旧无警告缺陷显式呈现 | 候选级集合与交集；不要求新warning总数机械等于93 |
| G11确认可信度 | 全108 | 初始review全部null；自动投影/点击全选/批量导入不生成user_confirmed；改正文hash失效 | 初始DTO、UI事件、服务端回执断言 |
| G12保护边界 | 所有源数据与旧合同 | IR/题库源副本hash不变；不触碰已发布索引/Provider/Runtime；0额外模型/OCR调用 | 前后hash、修改文件清单、调用拦截日志 |

**五项边界逐条关闭条件**：

| ID | 已确认问题 | 可接受的最小交付 | 不能称关闭的情况 |
|---|---|---|---|
| C033 | 图3.60误属于本题 | 图块保留context/关系线索，当前题干不把它当required；若归属未确认则boundary_uncertain | 删掉图和来源，或声称同时修好C031 |
| C091 | 另一实例及电流小节混入 | 明确边界则旁文移context；否则精确定位unassigned/待校对 | 把后续整段移入explanation就算正确 |
| C092 | “误差分析”小节混入 | 单独确认解答终点；图11.5依赖独立处理 | 只移除标题却保留正文，或图缺失仍ready |
| C093 | “顶点平衡”小节与图混入 | 分清题内/旁文与图11.1依赖；无法确定保留具体风险 | 删除后续公式后表示“无数学错误” |
| C096 | 同块解、前例依赖、后节与图混入 | 当前块人工分界、前例条件完整、旁文有去向；未完成任一项继续待校对 | 只按“解”字截题、一次确认清除所有缺口 |

“显式保留待校对”是合同安全行为通过，**不是该题已修复**。报告同时列出内容修复状态和安全处置状态，不能将5/5安全处置写作5/5内容修复。

### 5.3 原24项探针逐项处置

原结果仍为12 PASS / 12 FAIL，以下是**实施目标**。原runner不认识projection.dependencies，并以裸字符串比较公式；不得以修改旧期待值掩盖结果。新增v1测试入口接入本合同，输出独立报告：严格内容达成、可接受待校对、范围外未修复。需要兼容层时只做字段读取/显示包装映射，保留原字符串和原结果供比较。

| ID | 原结果 | S1/S2目标与断言 |
|---|---|---|
| R01 | PASS | 普通无答案题题干完整、答案解析空、无新增结构门槛 |
| R02 | FAIL | 实际按整块分离；过程进入explanation，原probe的answer-or-explanation仍有同源解；全角色映射 |
| R03 | PASS | 求解/解集是题干，零误拆 |
| R04 | PASS | 请求证明/通解/特解仍是题干，零答案捏造 |
| R05 | FAIL | 明确下一节才能精确排除；证据不足必须boundary_uncertain+不可入库，原严格分离目标仍记未达成 |
| R06 | PASS | 两题与子问分组正确，编号/子问不丢 |
| R07 | PASS | 跨物理页条件完整，不能按页强制切 |
| R08 | PASS | 长式token完整；另验块级display，允许显示包装差分但原字串报告保留 |
| R09 | PASS | matrix整体，行列/换行不丢；独立渲染门槛 |
| R10 | PASS | cases整体，条件不丢；独立渲染门槛 |
| R11 | FAIL | 必需figure与toy-figure-A身份进入dependency；来源已定位但没有F3不能宣称可练习；不将“身份保留”混成“图片交付” |
| R12 | FAIL | 同块解默认unresolved；人工明确分界后精确span与当前hash确认；自动严格分离FAIL可保留，不改成无条件PASS |
| R13 | FAIL | 独立解答块真实分离，源标记/文字保留于解析 |
| R14 | FAIL | 独立证明块真实分离，与R04负例同时通过 |
| R15 | FAIL | 明确答案块进入answer，不能只删标记 |
| R16 | FAIL | 候选有界邻接恢复“证”块，或源边界不明保留校对；不得修改全局学习单元边界来绕过 |
| R17 | PASS | 合法数字括号子问保留，与R05同时验证 |
| R18 | PASS | 缺结构残片不变成凭空发明的新题；无候选可保留原文提示 |
| R19 | FAIL | formula block的小数不作为题号；候选局部归并且保留原unit映射，全局learning_units不变 |
| D01 | PASS | 相同题干不同source按既有策略仍相同，不改策略 |
| D02 | PASS | 数值不同题不误合并 |
| D03 | FAIL | LaTeX大小写lower碰撞，范围外：继续公开FAIL，另案去重策略评审 |
| D04 | FAIL | 不同题号相同题未匹配，范围外：继续公开FAIL，不在本轮去题号 |
| A01 | FAIL | 原未版本化手工add路径保持兼容，仍为已知FAIL；另增A01-v1：未分离教材候选不能写库，普通v1题可写库 |

D03/D04与“不得改重复策略”直接冲突，A01旧手工入口与“不得意外阻断全部旧版导入”冲突；本提案选择明确保留已知缺口。用户若要求原24项全绿，须先另案批准扩大范围；Sol不得静默修改断言/计数。R05/R12可接受安全降级是本次用户明确允许的复杂题待校对方向，但原严格目标不能因此改成“已完成自动分离”。

**新增合同测试不是旧探针的替代品**：至少新增V01源角色全覆盖、V02图身份≠访问能力、V03同块编辑span、V04多风险并存、V05无答案无标签可导入、V06确认失效、V07批量选择不确认、V08拆并保全/失效、V09版本/块伪造拒绝、V10新旧客户端组合、V11回执原子性/未知提交、V12必要图片不可泛化确认、V13正式正文改动后回执仅为历史。每项同时有正例/负例；不把108审计ID硬编码进生产判定。

### 5.4 真人裁决清单：先登记，未裁决者保留pending

108条均是审计代理对保留OCR/IR的核对，0条真人金标；原PDF不可用，原PDF/OCR语义保真108/108 UNKNOWN。下面争议只冻结“存在待核对事项”，不冻结猜测的正确答案或自动修复文本。

| 人工队列 | 待裁决问题 / 所需证据 | 未裁决时允许工程冻结的部分 |
|---|---|---|
| H01 C004 | 源表值与解数值是否自洽；原PDF或领域专家；已有裁图与OCR表值一致 | 表格结构/所有数值原样保留、解不能混题；不自动改数字 |
| H02 C061 | 数值量级是否为原书/识别问题；需原PDF/专家 | 源题干逐字保全，结构本来可用，不因本审计数值疑问硬阻断92集合 |
| H03 C094 | 同基线公式碎片如何组成完整式、解答从哪里开始；需源页面/公式专家 | 块ID、源token不丢；无法确认即待校对，不拼接臆造 |
| H04 C095–098，图11.8/11.9 | 组合裁图是否完整、对应关系与共享参数；原页+图像内容 | 保留原图身份和冲突、不得错误声称可读取练习图 |
| H05 C091 | 已观察到的括号/符号差异具体如何修；原公式与领域判断 | 不擅自修符号；display问题与源真值分开 |
| H06 C031/C033及四个跨节例题 | 确认代理归属/边界判断可否提升为人工裁决 | 已有来源位置/缺口可作结构工程回归；精确新分界仍需证据或人工 |

裁决结果另存新的本地审阅记录：case_id、decision（confirmed/rejected/pending）、所见来源版本、裁决者类型human、具体范围、时间和理由；不得改旧ledger的human_review_status冒充早已完成。这里是测试审阅材料，不增加生产字段或通用审批系统。真人未裁决不阻止编码确定性部分，但不允许提升相关语义正确性结论或给争议项造金标。

### 5.5 差异报告要求

每条保存：audit_id、源unit/hash、前后question/answer/explanation hash与长度、角色块清单、公式/表/图身份与去向、typed issues、review是否为空、可入库判断、duplicate对应记录、变更类别和结论。私有正文差分只留ignored artifacts；Git只保存脱敏hash/ID/数量/理由。

报告至少分五栏：结构不回归、自动分离效果、安全降级、人工未决、源语义未知；各自列分母与ID。92、94、14、5、8、9、4、16是不同有交集的集合，不相加、不做一个总体准确率。引用旧25 PASS只能说明旧合同，不能冒充新合同或真实模型正确率。

## 6. 工程顺序与权限

1. 用户确认三份设计及兼容取舍后，Sol先核对当前分支/未提交内容和冻结输入身份；不重做同类质量审计。
2. 实施S1纯投影和可选协议，以离线合成与同源隔离数据验证；先交来源映射和逐候选差分。
3. S1审查通过后实施S2。准入服务与UI同时联调，正式默认入口切v1前完成新旧兼容/回执测试。
4. 实际Electron验收与108差异报告完成后，审查集成至Texa_MacOS；修改原因、JSON回执影响、真实验证及未测项写patch_notes。
5. 凡需F3、改fingerprint、源IR修复/重适配、索引激活、数据库schema迁移、历史修题、扩大Runtime/Provider或R1/R2主构图，停止相应扩展并提交独立理由/替代方案。

Sol可自行决定私有函数拆分、测试组织、命名、DTO实现方式与本域排版微调，不必为普通可逆实现反复确认；不得新增无消费者的字段、扩大领域合同、用一串regex代替块投影或改探针使数字变好。

## 7. 本轮完成记录

本轮已完成源码/现有审计证据核对、三份设计、具体JSON示例、局部交互合同、逐项验收矩阵与S1/S2计划。没有实现新协议、没有新结构测试PASS或新的108提取结果。文档静态验证与冻结资产一致性检查结果见本轮patch_notes；生产/模型/OCR/Electron新状态均未运行。**在这里停止，等待用户确认后再交Sol实施。**
