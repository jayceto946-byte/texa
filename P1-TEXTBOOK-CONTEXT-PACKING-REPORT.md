# P1-A Textbook Context Packing Reliability

实施：2026-10-18；交付：2026-10-19（Asia/Shanghai）。范围为教材最终上下文打包，不重设计检索、摄取或 Agent Loop。

## 1. Git 基线与隔离

| 项目 | 值 |
|---|---|
| Worktree | `/Users/jichengqian/Documents/ChatGPT/texa-p1-context-packing` |
| Branch | `fix/p1-textbook-context-packing` |
| Base | `655aa481743b20e24eaab52f5f75d141b4db83dc` |
| 实现、测试与验收证据 Commit | `4e1b385c9f3d28af2f0291b68d9a7b83b2e260ef` |
| 报告 Commit | 本报告作为后续独立文档提交；最终交付回执提供其准确 SHA，避免同一文件自引用自身哈希 |

先检查了 `git status`、`branch -vv`、`worktree list`、`log`。基线分支干净，包含 P1-A `c75695c`、P1-B `0c2f073`、P1-C `bfe4933` 的集成、`9c1c013` 验收及最新 Reliability 修复。没有从旧功能分支重新实施。

原始 `Texa_MacOS` 保持 `ac071ba`，结束前其未提交文件清单与开始一致；未切分支、提交、stash、reset、clean、合并或推送。未修改其他 worktree。实现与测试均在指定独立 worktree，复用已有 Python 3.10.21 / venv310；无依赖重装、数据库迁移或生产库写入。

## 2. 真实失败与根因 A–G

读取了 `P1-INTEGRATION-RELIABILITY-REPORT.md`、`docs/qa/p1-reliability/` 的 C 场景摘要、原验收脚本，以及本机临时目录中的 Runtime 原始记录。只读加载真实 Canonical JSONL、活跃 lexical 快照、manifest 和 MinerU structured content，未创建生产 Chroma 客户端，未打开生产学习 SQLite。

教材为彭杰纲《传感器原理及应用》第2版，第1.3.1节，PDF p.16–17。锚点 `e62ed1070495dd21e981`，Canonical hash `89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`，index `c8b6947edb7858f2`。IR 有4925块，活跃 lexical 快照2489行；身份文件 hash 见 [deterministic.json](docs/qa/p1-context-packing/deterministic.json)。

链路逐项追踪：生产 BM25 锚点 → `_section` / Canonical IR → `expand_textbook_context` → `pack_learning_unit` / EvidencePack → `search_textbook` ToolResult → SQL receipt → `prepare_chapter_subgraph` / `prepare_answer_generation` → 实际网络请求。

### A. 为什么展开39块

锚点原始 source block 是“最小二乘拟合”引入、过程提示、直线方程引入三段。`_section` 找到显式 MinerU paragraph_title `4. 线性度`，到下一编号标题前共39块。该范围还包含一般线性度、多项式、非线性误差、前四种拟合及配图。它是来源结构边界，不是39块都与当前推导同等必要，也不是检索重复召回了39次。未修改这套来源边界规则。

### B. 哪些是真正需要的内容

以0起算，块21–38（18块）构成主锚点起始的连续片段，包含式(1.5)–(1.11)、校准点与残差说明、平方和、两个偏导、k/b及随后解释。当前最小二乘教学不需要先消耗预算交付所有其他拟合方式。前21块仍可通过 `preceding` 读取；不把省略的式(1.4)冒充已交付。

### C–D. 为什么 Provenance 超预算，哪里重复

旧算法将整单元 figures 预先计入，再为每个块重复记录 source_kind、source_file、bbox_space/format/units，并重复出现块身份。39块正文只有3207字符，完整旧元数据结构默认 JSON UTF-8 为16440字节（紧凑序列化15212字节；两者字段相同）。旧上限实际按 Python JSON 字符估计，并非准确字节数；也未完整计入最终来源标签、版本字段与截断后指针开销。

本轮固定 profile 的旧代码先消耗7993字符估算额度，只容纳前14块、1197字符正文，尚未到第22块主锚点。来源开销而非正文长度导致截断。

### E. 为什么整体退回381字符

EvidencePack 随后检查首个 anchor 的全部 source IDs 是否在已选块中。失败后丢弃已经打包的前缀，以原 indexed excerpt 替换整个单元。最终381字符中，实际原文只有72字符，其余是状态/图片限制提示；连续推导和全部七个公式均未进入正文。

此前摘要中的 `formula_tags: ["1.7"]` 使用字符串包含判断；此片段有“图1.7”，不能证明式(1.7)存在。本轮按实际 `\\tag{...}` 及公式块逐项核对，修复前真正可见公式数为0。

### F. 现有 partial / continuation 能否复用

已有 complete/partial/unknown 和版本化 continuation 指针，但没有读取该指针的生产函数或工具参数；不能将“有指针”称作已能续读。本次复用同一 EvidencePack、Canonical 服务和 `search_textbook`，补齐同单元读取；没有新增搜索工具、模型调用循环或自动跨段执行。

### G. 是否影响其他教材

是通用打包路径的结构性问题：块多、来源位置重复、配图多、锚点较远的任何教材均可能触发。合成的数学教材回归覆盖相同失败形态；真实教材验收仅限本书，不宣称其他书的真实质量已验证。

另在同链路确认：展开正文被用作 `content_fingerprint` 时，Evidence continuity 回读 indexed anchor 会误判原文变更。本次保留锚点 fingerprint，另用 `visible_fingerprint` 记录实际送入模型的片段；测试确认正常复用通过、实际变更仍拒绝。

## 3. 最小修复与文件

| 文件 | 核心变化 |
|---|---|
| `graph/textbook_context.py` | 公共位置字段无损提取/展开；复用实际来源投影按UTF-8保守计量；整块连续窗口；只保留当前片段及显式引用的配图状态；前/后续读指针；同版本、同单元、同章读取；区分锚点指纹 |
| `graph/evidence_pack.py` | 来源投影提取为共用函数；优先保留实际连续原文；保底 excerpt 也服从剩余元数据额度；去掉重复 retrieval 正文副本；保留最终可见证据及来源默认字段 |
| `backend/services/agent_runtime/textbook_tool.py` | 既有工具增加有界 continuation 参数；校验冻结教材/索引、Canonical hash和单元边界；工具版本2→3 |
| `tests/test_textbook_context_expansion.py` | 长单元、锚点、原块/公式、图片、共享预算、UTF-8、版本/指纹、continuation和暂停恢复回归 |
| `scripts/accept_p1_context_packing.py` | 默认仅确定性验收；显式 `--model` 才请求真实模型，持久化最多3请求；正文/公开回答仅存本机临时目录 |
| `docs/qa/p1-context-packing/`、`patch_notes.md` | 记录身份、预算、用量、结果、失败和边界，不提交教材正文或隐藏推理 |

公共 source_location_defaults 只抽取完全相同的来源类型/文件和坐标约定。每块身份、页码、bbox保留；`source_locations(item)` 可逐项无损还原，差异字段不共享。review_status、Canonical hash、索引版本、块类型和必要图片状态未删除。旧格式仍可读取。

全部预算维持原值：EvidencePack QA 9000 / 章节6000字符、Provenance 8000、ToolResult 128000字符、chat/native checkpoint 64000字符、扫描128块。没有提高工具/模型调用预算。`preceding`、`continuation` 每次都是正常受控读取，不自动堆叠成无限上下文。

`complete` 仍只表示当前版本化IR明确边界的完整投影，不代表OCR、公式、模型理解或原书完整性。本例始终 `partial` / `source_status=unknown`。旧search_textbook v2暂停合同按既有版本/schema栅栏拒绝复用，需重新发起；不迁移或篡改历史回执。

## 4. 修复前后与真实教材确定性验收

| 指标 | 修复前 | 最终代码 |
|---|---:|---:|
| Canonical 展开范围 | 39块 / 3207字符 | 相同 |
| 主锚点是否进入连续Canonical窗口 | 否，触发excerpt替换 | 是 |
| 最终原文 | 72字符excerpt | 18连续块 / 1537字符 |
| 最终模型可见证据（含限制提示） | 381字符 | 1846字符 |
| 实际可见公式 | 0 | (1.5)–(1.11)全部7式 |
| 完整度 | partial | partial，source unknown |
| 最终来源元数据 | 5023字节，未含连续推导 | 6601字节，含逐块metadata；保守预留6605≤8000 |
| Runtime receipt | 旧失败见原报告 | 15976字符 / 17587字节，≤128000字符 |
| Chat checkpoint | — | 27533字符，≤64000 |
| Native messages checkpoint | — | 3207字符，≤64000 |

旧完整候选元数据与新分段元数据覆盖范围不同，不用16440→6601冒充同字段全量压缩率。修复收益是有限额度内连续交付需要的内容，并保留其余内容的读取路径。

确定性脚本从 Base SHA 直接加载旧实现到进程内复现381字符，不改基线文件；随后运行当前实现的真实SQL ToolResult、回执、章节再次打包、生成器和最终 messages。证明每个选中块的原文和所有七个公式逐字进入最终 human message，来源位置可无损还原。

主片段保留18块。前文通过 `preceding` 和两次有界 continuation 读取可覆盖全部39块，版本和hash始终一致；不意味着这39块同时进入一次模型请求。普通短样本A的EvidencePack正文与基线完全相同。Canonical、manifest、lexical、structured content前后hash均不变。

最终 human message SHA-256：`8820d0ff5f3525281bb630329a615a3a264812eaeb317865aec01ba5a0fcd47c`。最终代码生成的内容与真实网络请求中的human message逐字相同；末次来源指纹/同章保护调整没有改变已验模型正文。

## 5. DeepSeek V4.1 Flash 实际表现

使用既有专用 `deepseek_v4.1_flash_test` profile，实际model ID `deepseek-flash`，endpoint `api.deepseek.com`；未替换Qwen。temperature=1、thinking enabled、reasoning_effort=high、max_tokens=8192、streaming、max_retries=0，沿用已验证配置。没有修改凭证或profile文件。

仅1次正式请求（上限3），输入4264、输出8120、总12384 tokens；其中供应商报告reasoning 7039 tokens，只记录数量，不落盘推理正文。请求约41.53秒，端到端约43.50秒，finish_reason=stop。

| 观察项 | 结果 |
|---|---|
| 实际发送内容 | 请求侧检查(1.5)–(1.11)均存在；只发送当前片段和必要协议，不外发整书、学习记录或无关章节 |
| 连续推导 | **PASS（单样本）**：讲解残差、平方和、两个偏导、正规方程、k和b表达式 |
| 式(1.9) | 指出对k求偏导与右端(-1)不匹配，明确按推导应为对b求偏导；没有悄悄改写IR |
| 条件与缺口 | 说明直线模型及分母非零；不把统计假设冒充教材内容；说明式(1.4)未见、图片未读 |
| Runtime终态 | run completed；task **degraded / unverified**。没有独立数学核验回执，不升级整题verified |
| 全面数学正确率/稳定教学成功率 | **NOT VERIFIED**；一次样本、无额外模型评委 |

此前一次验收脚本误向模型工厂传入不支持的http_client参数，在发网络前失败；0请求，作为 `FAIL_HARNESS_BEFORE_NETWORK` 单独保留，修正适配后完成上述唯一请求。未将脚本失败归因于检索或模型。

公开完整messages、Runtime记录和回答只保留 `/private/tmp/texa-p1-context-packing/`，提交摘要含hash/字段级判断与用量。密钥比较扫描通过；隐藏reasoning不进入checkpoint、SSE或交付文件。

## 6. 式(1.9)源数据问题

只读查看了 MinerU保留的 `images/page_16_equation_25.jpg`；图上也写成对k求偏导，而右端乘(-1)。图像hash `0027175f29a044cfca9911155cd7ff0d09976f2f43e843891df94dfa26158019`。

确认**源图自身的数学标记不一致**；不能说已证明OCR识别错了这个字母。没有获得独立整页PDF对照，因此不进一步断言纸书印刷版本情况。IR和OCR原文均未改写。这是独立数据质量缺陷，不是打包失败的剩余原因。

图1.7的图注/空caption资源绑定仍存在限制：IR可见caption，但资源解析保留missing/未读状态。当前模型仅收到文本，不据图注宣称已读图。该绑定与视觉问题不在本次修复范围。

## 7. 回归、复跑与结论

- Python 3.10.21：最终20个相关测试文件，**205 passed**，13.70秒。涵盖长学习单元、UTF-8/共享元数据预算、partial正文、主锚点保底、整块公式、必要图片、版本/同单元continuation、初始128块上限、evidence continuity、checkpoint暂停恢复和旧工具合同拒绝。
- Electron壳：`node --test desktop/*.test.cjs`，**24 passed**。本次不改UI、桌面入口、路径、构建或依赖，未重建前端。
- `git diff --check`通过；交付凭证检查通过。没有全库测试、安装包构建或完整Electron付费教学/重启恢复验收。
- 默认复跑：`venv310/bin/python scripts/accept_p1_context_packing.py`（解释器可使用主目录既有venv310）。不带`--model`不发模型请求；脚本明确隔离临时Runtime数据库和环境路径，教材服务只读桌面来源。

| 验收范围 | 结论 |
|---|---|
| 核心381字符退化确定性复现与修复 | **PASS** |
| 来源身份、公式/原块、现有预算与可恢复回执 | **PASS** |
| 真实《传感器》所需七式进入最终上下文 | **PASS** |
| 同版本继续读取与普通短问答回归 | **PASS** |
| DeepSeek完成本次连续教学 | **PASS（1个有限样本）** |
| 整题独立数学核验 | **NOT VERIFIED**，正确保留degraded/unverified |
| 全生产向量混合检索、其他真实教材、图片理解、全Electron交互/真实Provider暂停恢复 | **NOT VERIFIED** |
| 全面教学发布 | **NOT VERIFIED**；不以本次范围内PASS替代其他P1阻断验收 |

剩余限制：单个原文块自身超过正文预算时仍不能保证一次交付，本次不切断公式或伪造完整；continue读取保持有界，不新增自动循环。OCR/源式错误不能由可靠打包自动修正。模型别名无供应商不可变权重快照，不能据此宣称长期模型行为稳定。

本分支仅供审查，未自动合并master或Texa_MacOS、未push。范围内目标完成：已获得的必要教材内容可在原预算下连续交付，同时保留来源、限制和后续读取路径。
