# Texa Runtime — Main Integration

2026-10-14，Asia/Shanghai。最终状态：**MERGED**。

Runtime / DeepSeek 收尾、历史 Policy V0.1 执行边界修复已通过必要免费回归，正常合并并推送至实际主分支 `master`。初轮 BLOCKED 记录保留在 `afc407a:TEXA-RUNTIME-MAIN-INTEGRATION.md` 和原失败日志；本报告取代其最终结论，没有覆盖历史证据或降低测试门槛。

## 1. 最终 Git 状态与主分支身份

- 实际主分支 `master`，`origin/HEAD -> origin/master`；没有创建另一条 `main`。
- 原 Main：`898bec3ae520fe06d0b5ac486752499760091bac`。起始分支 `codex/cross-module-remediation`，HEAD `f91633673c40cf9c353e49804e2584b64f3131cc`；初始 Index 为空，25 个 tracked 修改及未跟踪 Provider/测试/QA/实验材料，分支相对自身远端 ahead 6 / behind 0。
- 开发源码 Checkpoint：**`b12671bdfe2653cd5a79c93173419cfbd4e06233`**。
- 正常 merge：**`6a5f50ca44e28d6738e36215c06982c56744811d`**，父提交为原 Main 和上述开发 Checkpoint。`ort` 合并没有冲突，合并树与验收 Checkpoint 逐文件一致。
- GitHub 现有 origin 为 `git@github.com:jayceto946-byte/texa.git`。SSH 22 连接关闭后采用命令级 GitHub 官方 SSH 443，未改 remote/SSH 配置。合并前 fetch 确认 Main 无其他设备新提交、无分叉；正常 push 已成功更新远端 master 和开发分支。
- 本报告及合并后日志随后作为纯文档提交进入 master；**最终 Main HEAD（包括本报告）的精确 SHA 使用 `git log -1 --format=%H -- TEXA-RUNTIME-MAIN-INTEGRATION.md` 定位**。报告不能在自身内容里预先写入自身提交 hash；本轮已验收实现 SHA 是上面的 merge SHA，最终交付同时提供服务端 HEAD。
- 没有 reset、stash、强推、跳过 hooks、改写已有历史或删除分支/worktree。其他 5 个 worktree 和所有原有开发分支保留；当前 checkout 位于 master。

初始分支与 worktree、全部 48 个原有 Main 差异提交见 [git-audit.json](docs/qa/evidence/runtime-main-integration/git-audit.json)。该文件明确是初轮审计快照；当前合并验证见 [postmerge-validation.json](docs/qa/evidence/runtime-main-integration/postmerge-validation.json)。

## 2. 纳入范围与 Commit 清单

| Commit | 目的 |
|---|---|
| `33d6db0` | Runtime/DeepSeek 私有协议、多工具、预算、SQL/SSE 发布与验证；测试及公开回放 fixtures |
| `e843b8b` | UI 严格换行、真实执行进度、验证状态及教材切换竞态 |
| `f6f8464` | 历史验收、Astra ADR、QA 复现脚本、技术报告与版本说明 |
| `ad6d812` | 恢复测试使用当前 Python 3.10，独立导出不依赖仓库内 venv 相对路径 |
| `afc407a` | 初轮安全 Checkpoint、BLOCKED 报告和免费验收材料 |
| `b12671b` | Policy V0.1 原冻结源码隔离执行、生产对照和漂移拒绝回归 |
| `6a5f50c` | 正常合并 Main，保留全部既有历史 |
| 本报告提交 | 最终 MERGED 报告及合并后证据，不改变运行代码 |

起始开发分支此前未推送的 `3221643`、`09d512c`、`08cf3fc`、`6c418db`、`cd36765`、`f916336` 已随开发分支保全。48 个历史提交包含已有 Notes、Runtime Policy、Mobile S0/S1/S2 与跨模块整改，是当前分支的既有基线；本轮未新开发移动功能、重写其他分支或随意剥离相互依赖的成果。

本轮收尾没有依赖/lock 升级、SQL schema 迁移、用户配置改动或默认模型切换。无关实验和两份11.7MB/19.7MB冗余 Electron 原始记录原地保留，仅本地 exclude；350 个文件的路径/大小/hash见 `local-only-manifest.json`，两份大记录有公开摘要。没有提交临时 profile、数据库、env、安装包或构建产物；根目录 Vitest 缓存也仅本地保留。

## 3. 两处源码变化与冻结测试设计意图

Registry 相对原 V0.1 的全部变更来自 `08cf3fc`：`ToolContext.cancelled=None`、`timeout_seconds=5.0`，`ToolSpec.execution_mode="thread"`。这些是取消/超时及隔离工具执行的新增接口，既有位置参数与默认线程模式兼容；原 schema、runtime metadata、权限合同不变。

Resolver 相对原 V0.1 的全部变更来自 `6c418db`：增加 `math.verify -> symbolic_math, verify_math_result`。这是有意的候选行为扩展，仍经 Registry 的 builtin/READ/schema 与 Runtime 权限/预算栅栏，不回滚有效生产能力。

V0.1 README 原本把它作为**离线 Policy 数据集、seed 投影和规则选择评测的默认批准源码身份**；不是生产应用的启动门禁，也不是要求生产源码永久不可扩展的合同。后续 Runtime 变化导致其旧入口混用历史身份与当前生产代码。先前48项拒绝是正确暴露版本混用，不是48个独立产品故障。

修复采用明确的历史执行边界：

- 原 source-manifest、十二项 pins、source 快照、旧 V0/V0.1 样本及 gold 完全不变，不替换旧 hash。
- validator 校验固定原冻结目录；数据不能选择源码路径或自签新版本。
- 原 Registry/Resolver/Matcher/Projection/RulePolicy、理解提示和 wire 合同在私有模块名下执行；生产 imports 不被替换，不回退到当前应用源码。
- 缓存装载仍重新检查 pins；原 canonical schema、损坏/缺失源码、自重算版本与锁定集门槛保持拒绝。
- 教材 Evidence helper 保存同一纯函数，并保留原 AST hash `cdf2ce44cd54939b3f770c16f981bcf57b64463496c801947064bd950efbd270`；原 Projection 正文无需 AST 改写，也不导入当前模型栈。
- 报告显式标注 historical runtime-source/v0.1 snapshot，不能将其通过结果当成当前生产或新样本的 V0.1 准入。当前生产继续接受独立功能回归；新生产评测仍须新版本审阅。

新增对照测试证明生产数学候选保留、历史候选不扩展；污染当前生产函数不影响历史执行；缓存后篡改冻结源码和 helper 仍失败。见 [version-boundary-audit.json](docs/qa/evidence/runtime-main-integration/version-boundary-audit.json) 及 V0.1 README 的“历史执行边界”。

## 4. Runtime / DeepSeek 收尾核查

| 合同 | 核查结果 |
|---|---|
| 默认与可选 | Qwen3.7 Plus 默认，显式 profile 优先；DeepSeek V4.1 Flash 可选 |
| Provider wire | Qwen保留max_completion_tokens/enable_thinking；DeepSeek专属adapter使用max_tokens与本Run私有推理回传，不污染其他provider |
| 私有状态 | callback前截获到可关闭RAM作用域；结束/取消/超时清空，迟到线程不能复活；不进入公开SQL/SSE/UI/checkpoint |
| 工具与权威 | 整批ID/READ/schema校验、局部顺序门、逐项FixedRunner预算/owner栅栏与SQL收据/ToolMessage；停止后不继续排队项 |
| 恢复 | 新Qwen按既有边界恢复且不重放；DeepSeek assistant私有状态丢失、旧身份缺失或模型改变均在新调用前明确失败 |
| 预算与完成 | DeepSeek单次8192、Qwen4096，显式较小值优先；模型与工具次数独立；length或无最终正文不成功 |
| 答案发布 | RequiredOutputs结构/数值/字面与语义未知分开；严格格式正文不追加核验说明；SQL/task/outbox/最终SSE一致；阶段推导不自动verified |
| 教材/教学 | 同范围固定检索与EvidencePack，chapter先于正文；不新增开放循环或工具权限 |

原 Astra ADR 和二审条件保留。本轮未调用 Astra，未扩大生产 Runtime 架构。冻结执行修复仅属于离线评测边界。

## 5. 测试与构建

| 验证 | 实际结果 |
|---|---|
| 初轮关键后端 | 314 passed，`backend.log` |
| 初轮修复后全量 | 1616 passed / 48 frozen-source failures，原日志保留 |
| 版本边界/当前功能专项 | **297 passed**，`frozen-and-current-regression.log` |
| 边界修复后全量 | **1670 passed / 0 failed**，`backend-version-boundary-full.log`，Python3.10.21/venv310，隔离数据、无凭证 |
| 历史CLI默认report | 18 samples、locked=false、real_model_calls=0，`frozen-cli-report.log` |
| 合并后关键后端 | **438 passed**，`postmerge-backend.log`；历史冻结、Provider/多工具、验证、Checkpoint、恢复、SSE、取消与过滤 |
| 合并后前端 | **203 passed / 45文件**，`postmerge-frontend.log` |
| 合并后Electron壳 | **15 passed**，`postmerge-desktop.log` |
| 合并后TypeScript/Vite | **passed**，`postmerge-build.log`，使用既有Node/依赖，无安装升级 |
| 已提交源码独立导出 | 初轮133 passed，`checkpoint-smoke-final.log` |
| macOS Electron实际UI | 本轮收尾前FREE-VERIFIED：S5真实数学工具、S6两轮三行/独立unverified，1280×820/1024×768/760×820，errors=[]、strict_dom_lines=3；实现与merge树一致 |

初轮命令目录、loopback权限及测试解释器路径导致的失败全部解释并保留；版本边界首次适配的2项失败也保留，随后297和1670项通过。没有删除断言、降低锁定门槛或掩盖失败。

证据等级：本轮新运行是 **FREE-VERIFIED**；此前正式S1、S5/S6、Qwen真实结果为本轮 **HISTORICAL LIVE**，原报告LIVE-VERIFIED仍表示当时真实调用。Electron使用正式API/SQL/SSE但Provider HTTP是Mock回放，不能冒称新实时Provider验收。**本轮0付费模型请求、无Benchmark**。Windows/Android实机、安装升级与完整RC验收仍 **PENDING**。

## 6. 安全与凭证

- 初轮3522个当前文件及隔离QA数据，两把真实Qwen/DeepSeek凭证RAM精确命中0；新增可达历史2131个blob精确命中0，见原privacy/history-privacy记录。
- 合并前3223个tracked文件再次精确命中0，见 `premerge-privacy-20261014.json`；不输出凭证或密钥hash。
- 通用key模式的五个既有文件属于合成canary/脱敏测试说明。新增提交没有真实凭证、临时数据库或用户配置。
- QA保存器过滤API_KEY/SECRET/TOKEN/PASSWORD/PRIVATE_KEY/AUTHORIZATION，实际profile save→env writer回归通过；修复现在已经进入Main。
- 历史QA local.env曾写入真实凭证。零命中及清理不能排除历史同步、备份或快照副本；用户仍需自行轮换当时 **DeepSeek与Qwen API Key**。没有撤销或修改现有凭证。

## 7. 合并门槛与结果

G1–G10满足：成果有可追溯提交，当前回归无未解释失败，冻结边界拒绝仍有效，无新P0/P1、语义冲突、凭证风险或未经批准的迁移；Qwen默认、DeepSeek可选，既有Main/开发历史完整保留，未混入本轮无关实验或移动新任务。

采用正常 `git merge --no-ff`，随后正常推送；未遇到需要PR的保护拒绝，没有绕过保护或force push。合并后源码与已验收Checkpoint一致，438/203/15项及构建通过。最终文档提交后再核验工作区、origin/master与服务端SHA；旧开发分支/worktree不自动删除。

## 8. 非阻塞边界与Mobile S3交接

Python AnyIO/SWIG弃用提示与Vite大chunk警告保留；原始公开响应/日志的行尾空白不改写以美化证据，代码diff检查通过。DeepSeek丢失私有协议状态不可无损恢复，旧无身份checkpoint明确拒绝；教学语义/阶段推导与未全面绑定公式保持unverified，一次S1不证明8192统计稳定性。

Mobile S3以合并后的master为开发基线：统一 `/api/chat/stream`、ExecutionEvent、LearningTask；SQL决定执行身份、预算、工具收据和最终答案。旧run迟到事件不得覆盖新run；停止后不再执行队列工具。恢复保持同task/turn、累计预算和协议身份，并向用户披露不可恢复边界。

会话使用权威append-only消息与游标分页；暂停任务只读SQL投影不写历史，正式outbox消息替换同ID投影。资产/笔记仍独立，历史Assistant不是教材事实证据。旧移动端分支保留，本轮没有Mobile S3功能开发；Windows/Android、安装升级及RC完整验收由后续独立工作完成。

**结论：当前Texa Runtime已具备作为V1.0后续移动端开发的稳定Main基线条件；这不等同于V1.0 Release Candidate已经完成全部发布验收。**
