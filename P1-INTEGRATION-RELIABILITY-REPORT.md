# P1 Integration Reliability 与真实《传感器》教学验收

验收日期：2026-10-18（Asia/Shanghai）。这是小规模诊断验收，不是模型能力排行榜或数学正确率证明。

## 一、Git 与隔离

- Worktree：`/Users/jichengqian/Documents/ChatGPT/texa-p1-reliability`
- Branch：`fix/p1-integration-reliability`
- Base SHA：`9c1c013418f6a8e6d9a983b8490e6e1471592897`，来自干净的 `integration/p1-abc`。
- 基线已包含 A `c75695c`、B `0c2f073`、C `bfe4933`、候选题合同 `eadc350`，以及集成 fencing 修复。没有从原功能分支重新实施。
- 最终 Commit SHA：本报告和修复共同提交，精确 SHA 由提交后的交付回执给出；在此 worktree 执行 `git rev-parse HEAD` 可核对。同一提交内的报告不写自身哈希，避免自引用失真。
- 工作区：提交完成后核对 tracked/untracked 干净；前端依赖链接仅用于复用现有依赖，验收后移除，没有重装依赖。
- 原始 `Texa_MacOS` 工作区已有未提交修改，未清理、修改或带入。本轮未 merge、push、reset，也未改动三个原始功能 worktree。
- 修改文件：`backend/tools/math_tools.py`、`backend/services/agent_runtime/{native_loop,store,chat_binding}.py`、`backend/services/exercise_knowledge.py`、`knowledge/exercise_structure.py`、前端 `streamPresentation.test.ts`、新增 `tests/test_p1_reliability.py`、两份有限验收脚本、本报告、`patch_notes.md` 与 `docs/qa/p1-reliability/` 证据。

## 二、基线追踪与实际修复

已阅读 `P1-ABC-INTEGRATION-REPORT.md`、此前真实教学 `REPORT.md`、12 项 gzip 原始记录、Provider 用量回执、原验收脚本，以及实际数学 worker、Runtime、metadata 与保存服务。

旧 Qwen 结果仍为 A1/A2/A3/B2/C1/AC PASS，B1/B3/C2/C3/AB FAIL，ABC NOT VERIFIED。它们只能说明此前观察，不能与本轮换模型后的结果直接组成修复因果证据。

### B1：v3 数学合同

旧记录中 `x!=1` 被映射为 `x:nonzero`，条件被塞进等式 RHS；AB 导数检查缺少 `candidate`。v3 Schema 有大量默认空字符串，工具说明没有各 kind 的最小调用，错误只有 `expression is required` 或通用 schema 错误。

修改：明确 `left/right`、`original/candidate`、`context` 的职责；按 kind 在输入校验时指出必填字段；提供最小 derivative、equivalence、steps 调用；identity 使用 `before.left` 和 `after.left`，条件从冻结原题绑定，禁止模型补 assumptions。Runtime 参数错误回执给出正确字段说明。工具仍叫 `verify_math_result`、版本仍为 3，验证器、定义域与可信来源逻辑未放宽。

温度 1 基线 B1 仅做 simplify/limit，没有 v3 回执。修复后真实模型直接调用 v3 steps，一步验证 `(x^2-1)/(x-1) → x+1`；Runtime 绑定 `x:real` 与 `x!=1`，返回 `verdict=valid`、`scope=listed_steps_only_not_whole_answer`。模型准确解释局部范围并保留 x≠1。完成了真正的 v3 链路，不借用旧候选解验证冒充通过。

### B3：computed 与 verified

旧 Qwen 和本轮温度 1 基线 B1 都出现把纯计算称为计算核验的表述。原先静态提示不足以让模型始终遵守状态边界。

修改：每次模型请求根据 SQL 中的实际数学回执，补充“尚无独立核验通过”或“仅局部 scope 通过”的提示；解释 success 仅是执行成功，computed 不能称作局部验证。若最终没有通过的独立核验，答案增加明确状态说明，验证投影保持 unverified，不自动升级整题。

修复后 B3 模型选择了 v3 steps，但普通自然语言题面不符合可信条件块合同，工具正确返回 unknown。模型明确区分执行成功、unknown 和自己的数学推导，没有声称工具 valid。**该次真实复测没有覆盖 computed 分支**；computed-only → 明示 unverified 由确定性 Runtime 回归覆盖。真实教材 B 的 computed 与局部 verified 同时存在，最终仍为未完成。

### C2：metadata 与证据 span

旧 Qwen 把 metadata 写成裸 fenced JSON，解析失败且正文被污染；旧偏移 `[39,71)` 与 quote 的真实 `[46,84)` 不符。拒绝错误证据是正确行为。

修改：提供同次响应的最小合法标签示例；只接受 `<texa_structure>` envelope，保留原 Schema、Canonical ID、范围、版本验证。对末尾保留名称 knowledge/diagnoses 的裸 JSON 只隔离出正文并标记 invalid_envelope，**不接受其为学习数据**。Schema 错误记录不含原文的字段路径和错误码。

span 改为可省略：模型逐字提供唯一 quote；Runtime 在该 Attempt 原文中精确定位并写入 start/end。重复片段（含重叠）、不匹配、单侧偏移、错误偏移、题目版本不一致继续拒绝；显式 span 也不绕过唯一性。确认仍需用户动作、CAS、digest 和重新校验。

修复后温度 1 C2：模型 quote-only 提出第三行的过程遗漏，Runtime 得到 `[50,71)` 与 `[72,83)` 的两个真实片段并保存 suggested。未确认时弱点为空。真实教材 E1 的有效复测也定位到合成作答的第一、第二行，随后通过模拟明确确认与题目编辑验证失效；没有自动确认生产诊断。

### C3：status 与教学条件

旧 Qwen 的 knowledge 缺少 status，默认 unclassified 却携带分类项而被拒绝。修改为模型输出 Schema 必填 status，并给出显式 proposed/unknown 用法。空教材候选时，正式关联与性质列表必须为空；知识解释仍可写入正文。

非法 metadata 可以保留答案，但答案保存服务不再把无效分类的兜底结构报告为 saved，返回 metadata_invalid；错题解释也不写入非法分类或诊断。合法的既有资产仍受版本校验保护。

仅在这一领域的补充提示中要求保留定理适用条件：闭区间连续函数需要包含端点、内部驻点和内部不可导点，不能由多项式题推广为任意连续函数只查驻点。没有重写整个教学 Prompt。

温度 1 C3：合法 status，只有 final_answer_incorrect、空 concept_ids、step=null；正文明确没有过程不能判断具体错因，并包含不可导点。C2/C3 没有温度 1 修复前对照，故不能证明此成功是代码修复的单一因果效果。

### AB：预算耗尽的失败交付

旧 Qwen 曾 native_loop_failed、正式答案空。本轮温度 1 基线也在 4 次工具预算后 tool_budget_exhausted，正式答案空。

修改：预算错误统一保留；包括非法参数预留失败路径和批次包装错误。未执行的原生 tool call 补预算失败 ToolMessage 并 checkpoint，不再请求模型。只投影已完成的确定性数学回执；没有可靠结果时也给出明确未完成原因。failed run 保存 failure_answer 与 output，SSE 先 replace 掉阶段草稿，再发 canonical error。task/run 仍 failed，不走成功 final/outbox。

修复后真实 AB：仍因预算失败，已有 derivative/equivalence/候选代入的局部 verified 回执可查，正式输出非空且明确未完成。**失败交付 PASS，完整联合教学 HOLD。** 没有增加预算、解除 timeout/cancel，或强制追加最终模型请求。最终代码还在失败摘要中绑定所验输入；该展示补充由确定性测试覆盖。

## 三、DeepSeek 真实模型验收

### 模型身份、配置与用量

- 读取已有专用 profile：`profile-mv69dwg1` / `deepseek_v4.1_flash_test`。本地 registry 显示 DeepSeek V4.1 Flash 对应实际请求 ID **`deepseek-flash`**，不是 `deepseek-v4-flash`，没有猜 ID 或替代。
- endpoint：`https://api.deepseek.com`；凭证仅从已有 DeepSeek 专用凭证读取到进程内。其他 Provider/profile/凭证未修改。
- 正式配置：temperature=**1**；thinking enabled；reasoning_effort high；max_tokens=8192；streaming；自动重试 0；单模型请求超时 180 秒。所有正式任务固定这组参数。服务端没有提供可固定的不可变模型修订号；因此只能证明同一个 API model ID/配置，不能额外宣称供应商内部权重快照被锁定。
- 原生工具连续性沿用 `DeepSeekChatOpenAI` / RAM-only `PrivateProtocol`，reasoning_content 随工具消息连续返回 API，但不进入 LC 公开消息、checkpoint、SSE、报告或日志。仅统计 reasoning token 数量。
- 29/30 次真实请求后主动停止，其中 10 次发生在用户将 temperature 更正为 1 之前，全部标为作废，不纳入正式验收或前后比较；仍全部计入付费预算。正式温度 1 共 19 次。
- 所有请求合计：input **94,552**、output **46,807**、total **141,359 tokens**。正式温度 1：input **60,039**、output **29,023**、total **89,062 tokens**。输出用量包含供应商报告的推理 token；没有推算金额。
- 不调用模型评委，没有第二个分类模型，没有强制 tool_choice。URL/模型/温度/输出额度在网络发送前检查。没有把整个教材索引发送到 API。

原始合成场景工具参数、SQL 回执、公开最终回答、SSE 与终态保存在 `docs/qa/p1-reliability/` 的对应 gzip 记录；请求用量、耗时和公开输入 hash 在 `usage.json`。真实教材正文和完整生成结果只留在本机 `/private/tmp/texa-p1-reliability`，提交摘要不复制教材段落。

| 温度 1 场景 | 请求数 | 总 tokens | 端到端秒 | 验收 |
|---|---:|---:|---:|---|
| 修复前 B1 | 2 | 9,450 | 14.95 | NOT VERIFIED：未调用 v3；存在计算/核验措辞混淆 |
| 修复前 AB | 1 | 4,062 | 7.11 | FAIL：预算耗尽，正式答案空 |
| 修复后 B1 | 2 | 10,333 | 14.07 | PASS：v3 steps valid，解释范围正确 |
| 修复后 B3 | 2 | 9,612 | 12.94 | PASS：unknown 未伪装 valid；computed 分支仅确定性复验 |
| 修复后 C2 | 1 | 6,868 | 22.40 | PASS：metadata、quote-only 证据、suggested 保存 |
| 修复后 C3 | 1 | 4,832 | 13.65 | PASS：final-only 限制与不可导点条件 |
| 修复后 AB | 1 | 4,428 | 6.37 | 部分 PASS：失败交付；完整教学 HOLD |
| 修复后 AC | 1 | 3,692 | 6.40 | PASS：真实模型候选合同→入库→分类 Job/API 保存 |

PASS 是该样本对应合同的观察结果，不是稳定成功率。少量样本和模型行为差异不能证明所有改动的因果收益。

## 四、真实《传感器》教材验收

### 身份与执行边界

实际教材为彭杰纲《传感器原理及应用》第 2 版，电子工业出版社，2017，ISBN 978-7-121-30967-0。身份来自本地真实源及 IR，未下载替代教材。

- Canonical hash：`89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`。
- active index：`c8b6947edb7858f2`，schema 6；4925 个 Canonical 块，2489 个 lexical/catalog 行；manifest 记录 13 个章节 collection、1826 个可检索索引块。
- 读取桌面数据目录的 Canonical JSONL、active lexical version、manifest，以及 `mineru_output/传感器原理及应用/hybrid_auto_external/CGQ/structured_content.json`。完整路径、文件 hash、块数与锚点在 sensor-identity/preflight 摘要中。
- 真实检索使用生产 BM25 `search_rows`，限定第 1 章、取实际 top-ranked 锚点，再走生产 Canonical 展开、EvidencePack 与 Runtime。**未打开生产 Chroma 或生产学习 SQLite**；完整向量/混合检索、主聊天准入与 Electron 真实模型交互未验，不能声称全入口链路通过。
- 正式 KG 在已查教材资源目录中缺失；没有用合成 KG 冒充，所有正式知识 ID 列表为空。
- 写入仅在显式 `/private/tmp/texa-p1-reliability/{sensor-exercises.db,sensor-mistakes.db,progress/...}`。D 使用真实答案生成和保存领域服务，Job 身份输入由测试适配器传递，**不冒充 D 已覆盖正式 JobManager/HTTP UI**；合成 AC 已覆盖实际 Job/API 保存。
- 第一版测试脚本曾被自动审批拒绝，原因是存储隔离不够显式。该版本未执行/落盘，随后改为显式临时库与路径断言，通过审查。生产源文件每个测试前后比对 hash 未变。

### 六项任务与针对性复测

| 任务 | 原文锚点/范围（PDF 页号） | 请求数/总 tokens/秒 | 结果 |
|---|---|---|---|
| A 概念 | 1.1.2；chunk `ac5796dc81698aff50f5`，p.12；10 个 IR 块 | 1 / 4,432 / 6.52 | PASS：定义、通常而非必须为电量、规律性与精度要求均利用教材解释，引用 E1 |
| B 灵敏度与表 1.1 | 1.3.1“5.灵敏度”、例 1.3；chunk `b3696cd4e1f3706e7fd5`，p.18 | 1 / 5,070 / 9.74 | FAIL 完整交付：表格、公式、线性条件进入上下文；计算 7/30 和表中差分正确，有局部 verified，但继续调用超过 4 次预算，只交付有限结果 |
| C 连续推导 | 1.3.1 最小二乘；chunk `e62ed1070495dd21e981`，p.16–17 | 1 / 5,571 / 14.40 | FAIL 完整性：39 块展开后 provenance 预算使锚点退回 381 字片段；模型看不到 (1.5)–(1.11)，正确披露无法完整讲解 |
| D 真实习题 | 章末第 8 题，block `d09eb1bf265fc6309d79`，p.35；教材容差检索 chunk `c631d5113b708d810f95` | 首次 1 / 3,570 / 5.57；复测 1 / 3,481 / 4.39 | 首次 metadata invalid；正文结果 4.9m/5.1m 正确。补明确空候选合同后，复测合法 unknown、空正式 ID，领域保存成功 |
| E1 过程诊断 | 同第 8 题；明确合成作答，把 2% 当作 2 | 首次 1 / 5,010 / 16.30；诊断复测 1 / 4,660 / 15.40 | 首次 metadata invalid；同提示协议复测 parsed。精确 quote 定位 [0,9)、[10,44)，suggested；未确认弱点为空，SM-2 未变；模拟确认后题目修订到 2，旧诊断不再作为当前事实 |
| E2 只有答案 | 同第 8 题；明确合成最终答案 | 1 / 3,991 / 11.72 | PASS：仅 final_answer_incorrect，concept_ids=[]、step=null；未猜具体错因，未改变 SM-2 |

B 的可靠数值是 `7/30≈0.233 Ω/°C`，仅证明输入运算或等式；没有完成最终教学说明，不能因值正确把任务记成功。

C 的公式实际存在于真实 IR，缺口是最终证据裁剪，不是教材本身没有相关内容。这是本轮发现的 P1-A 真实内容阻断，记录为后续修复，未提高 provenance/Runtime 预算或重建摄取来绕过。IR 的 (1.9) 还出现对 k 偏导标签与随后 (-1) 因子不一致的可疑记录，需核对原图；本轮模型根本没看到该式，不能说它已识别或修正。

D/E1 首次仅留下 generic invalid，未保留失败 envelope 的具体字段原因，**无法追溯断定是 status、性质列表还是其他字段**。修复后增加有界字段错误码，并在末次诊断复测临时保留过滤后的公开响应。D 成功与空候选提示修改一致，但不是单因果证明；E1 协议未放宽就重跑成功，明确归为行为波动，不能抹掉首次失败。

### 图片与数据质量边界

原始裁剪图资产可用，表 1.1 使用的是真实 IR 表格文本。没有任何图片字节发送给模型，配图 metadata 始终为 not_read/not_required。A/B/C 没有声称读懂图 1.2、1.7、1.8 的图形细节。V4.1 Flash 本地配置声明可接受图像，但真实视觉入口本轮 **NOT VERIFIED**，不把图注当作图像证据，也不宣称入口不支持图像。

MinerU 来源使 source_status=unknown；A 结构 text=complete，B 本地子标题边界 text=unknown，C/D 存在 partial。complete 仍只代表存储结构完整，不代表 OCR 正确。没有批量外发无关章节、真实用户作答/学习记录、整书或完整索引。

## 五、回归、残留与结论

### Deterministic Tests

- Python 3.10.21 / 既有 venv310：**232 passed**。覆盖新失败路径及现有 v3 来源/定义域、数学进程隔离、原生工具连续性/取消、C 分类/版本/诊断确认、A 展开和候选题合同。
- React/SSE 相关 Vitest：**31 passed**，包括失败输出 replace 后 canonical error 仍保留正文与 failed 状态。
- 前端 TypeScript `tsc -p tsconfig.app.json --noEmit` 通过，增量文件定向临时目录。
- Electron 壳 Node 回归：**24 passed**。第一次本地端口测试被沙箱 EPERM 阻止，获本地回环测试权限后通过；不是代码回归。
- 没有全库依赖安装、数据库结构迁移或生产库复制。未跑全仓库测试、完整 Electron UI/付费模型恢复与视觉；上述测试不替代这些验收。
- Git diff、敏感信息、教材正文检查通过后提交。没有新增模型 Router、Agent、模型评委、工具预算或外部服务。

### 残留风险

1. AB 和真实教材 B 的工具使用仍会耗尽预算。可靠失败交付已修复，完成率问题未解决，不能以加预算掩盖。
2. 真实长推导受到 provenance 预算和 fallback 裁剪影响；C 未能服务完整教学，必须后续修复并做覆盖回归。
3. metadata 仍有真实失败与波动；本轮增强提示和拒绝/隔离/保存语义，不能宣称格式遵循已稳定。首次 D/E1 的细分原因不可追溯。
4. 无 KG 时 unknown 是正确边界，**不等于主考点/关联考点分类语义已经验收**；没有正式 ID 的准确分类目前 NOT VERIFIED。
5. B3 computed-only 的正式真实模型分支未重现，仅确定性覆盖；无温度 1 修复前 C2/C3 对照。
6. 没有真实图像阅读、完整混合检索、全 Electron 交互、模型别名不可变修订号、付费中断恢复测试。P1-A/C 的合成回归通过不能抹掉这些范围。

| 判断 | 结论 | 含义 |
|---|---|---|
| ENGINEERING | **PASS** | 本次局部修复与相关回归可独立审查；不代表全仓库/全端验收 |
| REAL MODEL ACCEPTANCE | **HOLD** | v3/诊断/失败投影样本通过；联合完成与 metadata 稳定性仍未达到完整门槛 |
| REAL TEXTBOOK ACCEPTANCE | **HOLD** | A 与有限资产链路可用；B/C 失败，正式分类/视觉/全检索未验 |
| TEACHING RELEASE | **HOLD** | 不建议据此扩大普通教学发布范围 |

有效修复独立提交供审查；剩余阻断如实保留，不降低通过标准。
