# Candidate Contract Specification — D-01

2026-10-17 · 设计提案，待用户确认后交 Sol 实施。**本文件不是已实现的 API / 数据模型。**

配套：[投影与校对](projection-review-design.md) · [实施、验收与决策摘要](sol-implementation-handoff.md)。

## 1. 决定与证据

在现有 ExerciseCandidate 上增加可选合同，以 Canonical IR 提供来源、以现有三个正文槽承载投影，不创建第二套题目领域模型。完整材料继续属于 LearningUnit；候选的 `question_text` 才是练习题干提案。

| 决定 | 当前证据 | 设计后果 |
|---|---|---|
| 不改变完整学习材料 | `ingestion/document_workflows.py:87–101`；`tests/test_textbook_workflow_repairs.py::test_bracket_example_and_subquestions_stay_whole_without_following_topic` 明确要求解和公式留在 unit 内 | 原 IR、LearningUnit.text、RAG/阅读完全不动 |
| 补候选投影，而非重新解析 | `memory/textbook_exercise_importer.py:91–93` 尚保留 source_block_ids；`:688–700` 直接分析 unit.text | 在教材候选适配处保留只读块引用并投影 |
| 复用答案与解析槽 | `memory/exercise_importer.py:29–49`、`backend/schemas.py:291–311` 已有 question_text / answer / explanation | 不增加 stem、solution 等第二套正文权威 |
| 块身份足够，不造全局溯源框架 | `ingestion/document_ir.py:129–180,210–217` 有 block_id、类型、页、bbox、表、equations、attributes、逻辑指纹 | 使用 book + canonical_hash + block_id；块坐标不变 |
| 校对与导入分开 | `CandidateReviewWorkspace.tsx:82` 已明确选中不等于校对；`ExercisesPage.tsx:33–48,373–390` 只有整批确认 | needs_review、选中、入库成功均不能变成人工核实证据 |
| 风险按内容分类 | `exercise_importer.py:288–299` 混用结构提示与空知识点；D-01 的 93 条警告漏掉12条无警告缺陷 | 新 UI 消费 typed issues；旧 validation_issues 兼容保留 |
| 不迁移题库 | `memory/exercise_bank.py:307–339` 已在同一事务写题目及 batch JSON | 最小来源回执附加到已有批次 JSON，不增加 SQL 表/列，不扩展 ExerciseRecord |

证据路径均相对仓库；精确基线为 `Texa_MacOS` / `c0673fc75d938bce25304a08aac8c70a70c11f18`，保留当前其他任务的未提交 UI 改动。D-01 数据与判断引用[既有审计](../../qa/question-extraction-quality-2026-10-17/QUESTION-EXTRACTION-QUALITY-AUDIT.md)，不重新审计108条。

## 2. 数据布局：只增加三个候选字段

候选新增可选 `projection`、`issues`、`review`。状态与准入由它们推导，不再存 `ready`、`verified`、`is_complete` 等重复布尔值。所有 v1 新候选必须显式带 projection 和 issues；缺失字段属于 legacy，不默认完整。

```text
分析响应（沿用 data + extract）
├─ data[]: 现有 ExerciseCandidate
│  ├─ question_text / answer / explanation   唯一可编辑正文
│  ├─ source / needs_review / validation_issues / confidence ... 保持兼容
│  ├─ projection?                          来源与投影关系
│  ├─ issues?                              内容 / 元数据问题
│  └─ review?                              本次明确校对确认；默认 null
└─ extract: 现有提取结果
   ├─ units[]: 原 unit_id / kind / text / source_block_ids / 页范围等
   ├─ canonical_hash?                      本次读取的 IR 逻辑版本
   └─ source_blocks?                       本批次去重后的安全块快照
```

`extract.units[].text` 仍是完整材料；不复制到每个候选，也不从被用户改写的 question_text 反推原文。前端 hook 同时持有候选与该批次只读来源注册表。原有 `extract.text` 继续提供批次全文。

### 2.1 Projection v1（示意类型，不在本轮生成正式类）

```ts
projection?: {
  version: 1;
  canonical_hash: string;      // 64位逻辑SHA256，与 extract 相同
  unit_ids: string[];          // 原始 LearningUnit.unit_id；拆分可共享，合并可多个
  scope: { chapter: string; page_start: number | null; page_end: number | null; source_mode: string };
  method: 'whole_unit' | 'block_boundary' | 'unresolved' | 'user_edited';
  parts: {
    question: SourceSpan[];
    answer: SourceSpan[];
    explanation: SourceSpan[];
    context: SourceSpan[];     // 已排除的旁文、资源线索，仍可对照
    unassigned: SourceSpan[];  // 无法确定角色，绝不悄悄扔掉
  };
  dependencies: Dependency[];
};
type SourceSpan = { block_id: string; start: number; end: number | null };
type Dependency = {
  id: string;                  // 本候选内稳定的关系ID，不是文件路径
  kind: 'figure' | 'table' | 'formula' | 'prior_context';
  label: string;               // 如“图3.60”“前例参数”；不是定位键
  requirement: 'required' | 'reference' | 'uncertain';
  block_ids: string[];         // 已找到的目标；没找到为[]
  asset_ids: string[];         // 已有资产身份；没有身份为[]，不能由路径冒充
  resolution: 'embedded' | 'identified' | 'unresolved';
};
issues?: Array<{
  key: string;                 // 本候选内 code + 定位的稳定键
  category: 'content' | 'metadata';
  code: string;
  block_ids: string[];
  dependency_id: string | null;
}>;
review?: null | {
  content_hash: string;         // 用户明确确认的内容版本
  resolutions: Array<{
    issue_key: string;
    decision: 'corrected' | 'not_applicable' | 'source_checked';
  }>;
};
```

一个字段不能无消费者地加入合同。以下表同时定义默认、生命周期与退役条件；“临时”指服务响应/页面内存，刷新和丢弃批次即删除；“回执子集”只在成功导入后保存。

| 字段 / 新增的叶字段 | 为什么旧字段不够；生产者 → 消费者 | 默认、旧数据与约束 | 持久化 / 删除条件 |
|---|---|---|---|
| `projection` | source 是自由文本，无法表达角色；教材投影器 → 校对/准入服务 | legacy 为 null；v1 必须完整提供，非 IR fallback 不伪造 | 临时；回执只取下述子集 |
| `projection.version` | 分辨未知合同而非猜字段；投影器 → DTO、提交服务 | v1=1；未知版本拒绝 v1 提交，保留候选 | 回执保留；版本不再读取前不得删 |
| `canonical_hash`（extract 与 projection） | unit_id 在不同 IR 版本不够；现有 canonical_book_fingerprint → 来源对照/提交复核 | legacy null；v1 必填；不以文件mtime替代 | 回执保留；批次删除时随之删除 |
| `unit_ids` | 随机 candidate.id 不是 source unit；投影器/拆并函数 → 对照、差分、提交 | 默认[]仅 legacy；v1至少1个，同一教材版本；来源unit全集不因改题干缩短 | 回执保留；与批次同寿命 |
| `scope`及chapter/page_start/page_end/source_mode | units不能还原用户选择范围；复制既有分析请求 → 提交服务重新检查块是否在范围内 | 与分析请求相同默认：空章/null/null/exercise_sections；heading:标识原样保留；v1必填，改变范围重新分析 | 临时；完整内容hash包括scope，回执不必保存可重建的筛选参数 |
| `method` | split_confidence 不是结构依据；投影器/编辑 reducer → 预览/准入 | legacy无方法；v1不能缺失；修改内容后 user_edited | 回执保留；它说明映射精度，不是准确率 |
| `parts` 五个角色键 | 范围不等于实际贡献；投影器/人工划分 → 高亮、串行化、完整覆盖检查 | 每键[]；无法分离时原块归 unassigned，question_text仅作为可编辑完整材料提案 | 回执保留，供入库来源核对；不保存正文副本 |
| `SourceSpan.block_id` | 定位具体块；投影器 → IR解析/对照 | 必须在注册表且版本一致，不可用文本相似匹配替代 | 随 parts |
| `SourceSpan.start/end` | 支持人工同块拆分的可追溯范围；投影器/编辑映射 → 对照/覆盖检查 | 整块为0/null；非空范围按原始 block.text 的 Unicode码点，左闭右开，JS不可直接用UTF-16下标 | 随 parts；格式化产生的 `$` 不计入源范围 |
| `dependencies` | 题干有图题不等于输入可用；投影器 → 定向校对/准入 | 默认[]仅表示未发现依赖，不等于已证明无依赖；来源未知仍有 issue | 临时；批准入库的文字型输入已经进入正文/parts，不将全部风险永久存库 |
| Dependency `id/kind/label` | 连接具体缺口与操作；投影器 → issue引用/局部提示 | id必填且批内编辑稳定；label可空；kind必填 | 临时；明确绑定后仍只是候选来源身份 |
| Dependency `requirement` | 参考图与必需图不同；投影器/显式校对 → 准入 | 默认 uncertain；不能由“含图”推 required | 临时；确认前不能自动变reference |
| Dependency `block_ids/asset_ids` | 源块与像素是不同身份；投影器 → 对照/准入 | 默认[]；旧图以 figure block_id作教材图身份；若原 IR 另有 asset_id 则保留，二者不混淆 | 临时；原资产留在教材，候选丢弃不删除源资源 |
| Dependency `resolution` | 找到文件不等于独立练习可用；校验器 → 准入 | 默认 unresolved；embedded=正文已包含所需文字/表/公式；identified=只定位来源；不设虚假的 available | 临时；不增加无消费者的下载状态 |
| `extract.source_blocks` | units只有ID，UI无法对照块类型/位置；教材读取器 → 对照/投影测试 | legacy[]；仅本批次范围与有限邻接证据，去重；禁止整书传前端 | 临时；与批次一起释放 |
| 块快照复用字段 | 使用下述白名单；读取器 → 对照 | 缺失保留null/[]，不臆造页/bbox | 临时；版本化源IR长期保留，回执不复制这些大字段 |
| `source_blocks[].order` | 字典或ID顺序不能代表阅读顺序；读取器 → 原文排列/边界检查 | 全书 Canonical blocks 的零基序号，仅该版本有效；不等于原生block_index | 临时；可由冻结IR重建 |
| `issues` | 旧字符串混合元数据与内容；校验器 → 筛选、计数、准入 | legacy省略(null)；v1数组必填，可空；未知content code保守待校对 | 临时，不写入Exercise.notes当长期权威 |
| Issue `key/category/code` | 可稳定定位与分类；校验器 → UI/确认记录 | 必填；无confidence；code→文案/处理策略由本域固定映射 | 临时；成功回执不保存整段诊断 |
| Issue `block_ids/dependency_id` | 用户必须知道修哪一段；校验器 → 对照与修正动作 | []/null允许全候选问题；非空必须可解析 | 临时 |
| `review` / `content_hash` | needs_review只表建议；明确确认操作 → 提交复核 | 默认null；非空仅由用户点击当前题的确认操作生成；hash不匹配视为未确认 | 回执只存确认类型及正文hash，候选清空即释放原对象 |
| `review.resolutions` / `issue_key/decision` | 不能一键抹掉所有风险；用户定向操作 → 服务端检查 | 默认[]；只能引用当前问题键；无效/过期键不能完成校对 | 临时；不把用户判断包装成数学验证 |

**块快照白名单**：复用 DocumentBlock 的 `block_id, block_type, text, section_path, page_start, page_end, bbox, equations, table_title, table_header, table_rows, source_kind, review_status`；从 attributes 只取 `source_page_idx, source_block_index, bbox_space, bbox_format, bbox_units, mineru_type, semantic_role` 以及已有资产的 id/hash/status（如有）。不整体透传 attributes、source_file、asset_relpath、source_relpath、绝对路径。源文件定位在服务端按教材版本解析，前端只见书名/物理页/块位置。无bbox坐标元数据时只显示位置数值或“坐标系未知”，不能画假精确框。

这不是新 DocumentBlock schema；块快照是现有类型的安全 DTO 投影。新增 order 是显示顺序；现有 source_page_idx/source_block_index 是原始来源位置，不能混为一谈。

### 2.2 来源不变量

- `unit_ids` 与现有 units[].source_block_ids 定义**完整来源范围**；`parts` 定义**具体角色贡献**。裁去后续旁文不删除来源；放入 context。未知部分放入 unassigned。
- 初次机器投影须覆盖范围内每个源块（含空文字图）一次；同块可分不重叠span，空图用0/null。仅允许明确记录的共享上下文引用；不得把同一解答既塞题干又塞解析。装饰空白可留在相邻span，不能静默掉非空字符。
- 外部于 unit 的块只有进入本批次注册表并明确记录 context/依赖关系，才可参与提案；不得越过用户所选教材/章节/页范围自动补题。找到范围外图号仅提示“需补充范围”，不读取正文。
- `method=user_edited` 且用户明确确认当前完整题干时，允许仍保留原 unassigned 作为“未精确对齐的来源依据”；它本身不再阻断人工整理后的新题，实际missing_input/solution_in_stem等问题仍须逐项解决。不能把原源块不明的角色伪改成已精确对应。
- `method=user_edited` 时保留 parts 作为**原提案来源依据**，不再声称用户新文字与每个span精确对齐。能精确跟踪的移动操作可重映射；任意手写不做猜测映射。新内容由用户承担校对确认，不伪造新的source block。
- 所有查找以 (book scope, canonical_hash, block_id) 为准。源版本变化/块缺失不能按标题、题号或新IR悄悄重绑。

## 3. 结构状态与问题语义

状态是 read-only 派生值，表示系统当前证据结论，不叫 verified。以下互斥主状态只用于概览；issues允许同时保留多个问题，不因优先级丢掉副问题。

| 状态 | 计算条件（自上而下） | 正文含义 / 独立练习前动作 |
|---|---|---|
| `source_unknown` | 缺projection/注册表、IR版本不符、块无法解析或关键来源不足 | 未评估/来源不足；legacy单独兼容，v1不自动入库 |
| `missing_input` | 未解决必需资源、条件/题页缺失，或必需图片只有 identified | 缺必要输入；补正文或留待后续图片能力 |
| `possible_leakage` | 仍有未解决的 solution_in_stem | 完整材料可能仍混解；分离/人工校正 |
| `uncertain` | 未解决边界、资源归属、依赖性质、公式结构问题，或机器投影有 unassigned/用户改写未确认 | 定向核对；不是“低分坏题” |
| `ready` | 上述均无；题干非空、来源覆盖可解释、必需输入已embedded | 已识别可独立练习的结构；不证明OCR、答案真值或人工核对 |

review是否有效是另一轴：`review=null`→系统提案/未确认；有效hash→用户已确认当前内容；发生内容修改→自动清空review。普通题可 `ready + 未确认` 批量提交；复杂题必须 `ready + 用户确认`。用户确认只是“核对当前结构及输入”，不提升为模型/数学准确性。

### 最小 issue code 表

| category / code | 含义与消费者动作 | 准入作用 |
|---|---|---|
| metadata / `missing_concepts`, `unknown_type`, `difficulty_hint`, `duplicate` | 保留标签、题型、难度建议；重复继续走既有skip | 不构成结构阻断；duplicate不改变算法 |
| metadata / `legacy_notice` | 无法分类的旧提示，原字符串保留在validation_issues | 不伪造结构通过；也不一律阻断旧客户端 |
| content / `solution_in_stem` | 当前题干包含未分离解段/例题角色不明 | 必须修正或针对误报给出source_checked |
| content / `boundary_uncertain` | 后续小节、多题/子问、归属范围存在歧义 | 需具体来源比较、编辑或not_applicable确认 |
| content / `missing_required_input` | 所需图、表、条件、题页未具备 | 不能仅点“已核对”解除 |
| content / `dependency_uncertain` | 图号/前例关系不能确认 | 指明关系、补条件或确认非必需；不是自动绑定 |
| content / `formula_review` | 显示失败或源公式碎片/符号疑点 | 影响题干可读/条件时阻断；仅解析争议可人工source_checked保留源解，不宣称正确 |
| content / `source_unavailable` | 版本/块缺失、无结构来源 | v1不可宣布完成；先恢复来源 |
| content / `edited_content` | 任意正文改写/拆并后，原自动投影已不精确 | 当前题显式校对后解除；不要求补造答案 |

code → 结构状态/可解决动作在本域固定表中定义，不再添加 severity/confidence 字段或通用规则引擎。结构短句（“可能切分不完整”“选项不足”“含多题”“低切题边界”“incomplete_learning_unit”）不能因来自旧 validation_issues 就归 metadata；v1须映射到相应content code并核实证据，纯长度阈值仅产生待核对信号，不证明缺题。空标签/空答案绝不生成 content issue。

**兼容字段**：`validation_issues` 继续作为旧客户端可读字符串摘要（可含新内容提示），不再是新 UI 的质量权威；v1 UI不重复展示两份。`needs_review` 不改旧默认，不表示用户已核实；`confidence`/`split_confidence` 仍只是启发式元数据，不参与准入。系统推断不能写 review。

## 4. 确认、编辑与哈希

`content_hash = SHA256(UTF-8 canonical JSON)`，JSON对象键排序、紧凑分隔、UTF-8，不做大小写/空白/公式规范化。输入仅包含 `question_text, answer, explanation, projection`；不包含issues/review/可变UUID、subject/tags/type/difficulty/source展示标签。这里不是 question_fingerprint，不能复用其lower/去空白语义。跨语言提供固定Unicode/emoji/换行用例；前端计算或服务端返回摘要的普通工程选择由Sol决定，但服务端必须重算。

- 确认动作只确认当前候选与该hash；浏览、选中、全选、切换预览、批次提交不生成review。
- 修改题干、答案、解析、角色映射、资源依赖、来源版本，清空review并转user_edited；来源范围改变必须重新分析。仅改tags/type/difficulty不失效结构确认。
- 合并只允许同书同版本的相邻候选；unit_ids取有序并集，保留各原单元，parts合并后重验，不复制首题的review。拆分两子题各保留原unit；有源答案/解析不能凭空复制为两题答案，更不能因既有空行操作丢失，未分配文本归unassigned并留在来源。两种操作均需再次确认。
- `corrected`：服务端检查修正后的字段/映射，问题事实已消失才解决。`not_applicable`：用于资源非必需/边界误报等可人工判定项；仍需当前hash确认。`source_checked`：只承认用户看过具体来源并接受该结构/源解，不把源公式争议修成数学真值。
- 来源版本不符、空题干、无法解析span、必需图尚无正式读图合同，不接受泛化确认解除。不得把客户端自行声明的 `issues=[]`、`state=ready` 当权威。

## 5. 提交与持久化：不以needs_review隔离练习

当前 `needs_review` 仍可进入练习（D-01 A01），因此 v1 采用**候选阶段拦截**：未解决内容不写 Exercise。正式库不新增“隔离题”状态，不修改 Learning Runtime 或练习选择合同。正常题、明确分离且输入齐全的提案可整体确认入库，仍不能标“已人工校对”。

### 5.1 v1 请求增量

- `TextbookExerciseAnalyzeRequest.candidate_contract_version?: 1`，默认null，旧客户端原行为。新 Electron 显式请求1；返回必须回显 `candidate_contract_version:1`，否则保留内容并提示后端不支持，不能悄悄降级写库。
- v1提交使用新协议路由 **`POST /exercises/candidates/batch-add`**，复用既有批次DTO、领域服务与bank事务；不是第二套导入流程。旧后端该路由不存在，404即保留候选，防止老后端静默忽略新增JSON字段后写库。原`/batch-add`继续服务legacy；新后端收到该旧路由携带v1/context时拒绝并指向新路由。
- `ExerciseBatchAddRequest.candidate_contract_version?: 1`，默认null；新协议路由必须为1。v1整批中的每项在现有ExerciseAddRequest旁增加 `candidate_context?: {projection, review}`；issues不作为客户端可信入参。单题 `/add` 若出现 candidate_context 必须明确拒绝并指向新协议批次路由，不能静默丢弃字段。
- v1批次每项context必须存在且同书；声明v1却缺失、未知版本、混合 legacy/v1均拒绝该批次（422，可定位origin_id）；不写部分记录。前端先按资格生成提交集合，尚未解决者留在候选中。
- 服务端应用服务在写库前重新加载该书Canonical、核对版本和unit/块范围、重放确定性检查、验证角色与正文一致性（user_edited按编辑合同处理）、必需资源与review hash。对用户确认的歧义只记录其判断，不假称机器证明。IO按教材候选分支惰性解析；Router只做DTO/错误转换。
- 确认失效/版本变化返回409及具体候选标识，恢复校对；规则已知不满足返回422及content issues。重复沿用原bank算法，count/skipped/batch_id维持原回执。
- 无法原子验证整个提交集合时不先写其中的正常题。用户可以在现有UI明确提交“可入库的N题”；不能服务端悄悄过滤然后仍返回全量成功。

传输字段也有明确退役边界，不能成为另一套业务状态：

| 可选字段 | 生成 → 消费；为什么需要 | 默认/旧数据 | 持久化与删除 |
|---|---|---|---|
| 分析/提交 `candidate_contract_version` 及分析响应同名回显 | 新客户端 → API；服务端 → 新客户端，确认对方确实支持v1而非忽略未知字段 | null=legacy；未知非空版本拒绝 | 不持久化，随请求结束；legacy退役前不能删兼容分支 |
| 提交项 `candidate_context` / projection / review | 前端候选快照 → 准入服务；旧AddRequest没有校对依据 | null仅legacy可用；v1必须有projection，review允许null | 传输对象不持久化，只取回执子集；请求结束即释放 |
| 批次输出 `candidate_receipts` | 同事务持久结果 → 既有批次核对UI | 老批次[]，表示未记录，不表示已人工确认 | 见下节；不另存候选草稿数据库 |

### 5.2 有限长期来源回执

在**既有 `exercise_import_batches.data` JSON**内增加可选 `candidate_receipts`，默认[]。不改SQL、不迁移老批次、不改变ExerciseRecord/PracticeSession。

```ts
candidate_receipts?: Array<{
  exercise_id: string;
  origin_id: string;
  projection: Pick<Projection, 'version'|'canonical_hash'|'unit_ids'|'method'|'parts'>;
  body_hash: string;          // hash(question_text, answer, explanation) 的精确版本
  review_kind: 'system_proposed' | 'user_confirmed';
}>;
```

这里持久化的 `body_hash` 为**入库正文摘要**，只含三个正文键；候选的review.content_hash包含projection，二者使用不同字段名，用途不能互换。服务端生成，客户端不能提交回执。回执的书身份来自同书bank和批次source，不从可编辑source标签反解。

| 字段 | 必要性、生产者/消费者、生命周期 |
|---|---|
| candidate_receipts | 已有批次无来源/确认依据；应用服务给出最小子集，由bank与题目同一事务写；既有导入批次核对入口消费，支持逐题核对来源/未知提交结果；可选[]兼容旧批次 |
| exercise_id / origin_id | 前者关联实际新记录，后者关联本次候选；bank生成前者，来源候选给出后者；跳过重复不生成假入库回执，不给既有题添确认 |
| projection子集 | 精确版本、source units、角色依据；来源核对读取时必须匹配版本，不要求永远保有旧全文；丢源显示不可回查，不重绑 |
| body_hash | 检查题库正文是否仍为当时版本；批次核对消费；后续正式答案/正文变更导致hash不同，仅能显示“导入时回执”，不能继承当前已核实身份 |
| review_kind | 区分普通批量提案与显式逐题确认；导入回执/批次核对消费；不是正确性认证 |

回执和批次一起备份、一起保留；回滚批次沿用原记录更新为rolled_back，回执保留历史语义，不删除源IR。既有批次删除政策若未来生效，回执同寿命，无独立清理任务。不往notes塞序列化JSON或108条审计标签。S2必须在现有“读取批次供核对”路径显示最小来源/确认明细，否则这些字段没有落地消费者，不能声称S2完成。

### 5.3 兼容边界必须明说

| 组合 | 行为 |
|---|---|
| 新前端 + 新后端 v1 | 新候选结构门槛生效，未解决题不写库 |
| 新前端 + 老后端 | 无分析版本回显即停止；即便分析后服务端降版，新提交路由也404，不会在旧batch-add静默写库 |
| 老前端 + 新后端（未请求v1） | 旧分析/导入行为保留，标识legacy/unassessed，不宣称受到新结构门槛保护 |
| 老候选缺projection | 不推断人工核实；可留在原legacy流程，若要新保证需从来源重新分析，不批量迁移 |
| 手工录入/文件候选 | 维持旧合同，不为本次教材改造强制访问IR；无新安全/正确性承诺 |
| 已有题库/练习记录 | 不改写、不回填、不追溯封锁 |

保留旧入口意味着不能保证任意旧客户端/手工payload都受新门槛约束。这是明确兼容取舍，不能用v1测试通过宣称A01旧手工路径已修复。若要求全入口强制结构证据，须另案批准旧客户端退役/人工录入合同及历史资产策略，不能由Sol扩张本任务。

## 6. 具体示例

以下是自造合成内容；不公开真实教材全文。哈希占位字符串只为阅读，实际校验必须为真实64位SHA256。

```json
{
  "candidate_contract_version": 1,
  "data": [{
    "id": "toy-c1",
    "question_text": "【例1】求2与4的平均值。",
    "answer": "",
    "explanation": "解：相加后除以2，得3。",
    "source": "演示教材 / 第1章 p1-1 / b1",
    "needs_review": true,
    "validation_issues": ["未识别知识点"],
    "projection": {
      "version": 1,
      "canonical_hash": "<该合成IR的64位逻辑hash>",
      "unit_ids": ["b1"],
      "scope": {"chapter":"第1章","page_start":null,"page_end":null,"source_mode":"examples"},
      "method": "block_boundary",
      "parts": {
        "question": [{"block_id":"b1","start":0,"end":null}],
        "answer": [],
        "explanation": [{"block_id":"b2","start":0,"end":null}],
        "context": [], "unassigned": []
      },
      "dependencies": []
    },
    "issues": [{"key":"missing_concepts","category":"metadata","code":"missing_concepts","block_ids":[],"dependency_id":null}],
    "review": null
  }],
  "extract": {
    "canonical_hash": "<同上>",
    "units": [{"unit_id":"b1","kind":"example","text":"【例1】求2与4的平均值。\n\n解：相加后除以2，得3。","source_block_ids":["b1","b2"],"page_start":1,"page_end":1,"truncated":false}],
    "source_blocks": [
      {"block_id":"b1","block_type":"paragraph","text":"【例1】求2与4的平均值。","order":10,"page_start":1,"page_end":1,"bbox":null,"equations":[]},
      {"block_id":"b2","block_type":"paragraph","text":"解：相加后除以2，得3。","order":11,"page_start":1,"page_end":1,"bbox":null,"equations":[]}
    ]
  }
}
```

此题 `ready / system_proposed`，空answer不阻断；完整源解放explanation，没有为了非空answer从末句猜“3”。若源有独立“答案：3”块，才放answer。

缺图例（仅展示增量）：

```json
{
  "dependencies": [{"id":"figure-A","kind":"figure","label":"图A","requirement":"required","block_ids":["fig-a"],"asset_ids":["toy-figure-A"],"resolution":"identified"}],
  "issues": [{"key":"missing_required_input:figure-A","category":"content","code":"missing_required_input","block_ids":["fig-a"],"dependency_id":"figure-A"}],
  "review": null
}
```

图已找到，不等于文件不存在；但没有正式题库读图能力，仍是 missing_input。资产ID只用于来源定位，不可拼 `file://` 或磁盘路径。普通无答案题可 `whole_unit + issues=[] + review=null`；同块混解例应 `unresolved + unassigned=[原块] + solution_in_stem`，保留完整原文直到人工编辑和确认。

真实 C001 的提案映射：unit `1d4bb621ade704532cf1`；question=同名块；explanation=`3e3e4f67c745d62f74f9`、`b2889696c2d5bde16696`；answer可空。三块均p14，原位置page_idx=13，block_index=12/13/14。以[审计账本](../../qa/question-extraction-quality-2026-10-17/candidate-audit.jsonl)为依据；这是源结构提案，不是人工金标。
