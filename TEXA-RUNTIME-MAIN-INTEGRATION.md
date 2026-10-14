# Texa Runtime — Main Integration

2026-10-13，Asia/Shanghai。最终状态：**BLOCKED**。

Runtime / DeepSeek 的专项免费回归、前端构建和 Electron 回放通过；整体合并仍被 Policy V0.1 冻结源码校验的 48 项失败阻断。没有修改批准的 hash、降低断言、重新批准旧金标或把失败解释为 Warning。**没有合并或推送主分支。**

## 1. Git 状态与范围

- 仓库实际主分支为 `master`，`origin/HEAD -> origin/master`；本任务中的 Main 指它，不创建平行 `main`。
- 起始分支 `codex/cross-module-remediation`，HEAD `f91633673c40cf9c353e49804e2584b64f3131cc`，相对自身远端 ahead 6 / behind 0。Index 初始为空，25 个 tracked 文件修改，另有未跟踪的 Provider、测试、报告、QA 材料与实验目录。
- GitHub SSH 22 连接关闭；命令级 `ssh -p 443 -o Hostname=ssh.github.com` fetch 成功，未改 remote URL 或 SSH 配置。
- 本地及远端 `master` 均为 **`898bec3ae520fe06d0b5ac486752499760091bac`**。起始开发 HEAD 相对它 ahead 48 / behind 0，没有分叉、冲突或来自远端 Main 的新提交。
- 48 个历史提交已包含 Notes、Runtime Policy、Mobile S0/S1/S2 和跨模块整改。既有 Git 隔离报告确认其历史关系；这些是当前实现的已有依赖，不在本轮重新 cherry-pick、改写或开发移动端。本轮没有合并这段历史到主分支。
- 所有其他分支与原有 6 个 worktree 保留；未 reset、stash、删除、强推、重写历史或操作其他 checkout。
- 实验目录及两份 11.7MB / 19.7MB 冗余 Electron 原始记录原地保留，仅加入本地 `.git/info/exclude`。350 个保留文件的路径、大小与 SHA256 见 `local-only-manifest.json`；两份原始记录另提供公开摘要。首次从根目录运行 Vitest 生成的 `node_modules/.vite/.../results.json` 缓存也仅本地排除，没有安装依赖。

详细分支、worktree、历史提交清单见 [git-audit.json](docs/qa/evidence/runtime-main-integration/git-audit.json)。最终开发 Checkpoint 可用 `git log -1 --format=%H -- TEXA-RUNTIME-MAIN-INTEGRATION.md` 定位；该报告无法在自身内容中记录自身提交 SHA。

## 2. 收尾提交

| Commit | 目的 |
|---|---|
| `33d6db0` | Runtime / DeepSeek 私有协议、多工具、预算、SQL/SSE 最终发布与验证；对应测试和必要公开回放 fixtures |
| `e843b8b` | UI 严格换行、执行进度、验证状态和教材切换竞态 |
| `f6f8464` | 历史验收、Astra ADR、QA 脚本、技术报告及原版本说明 |
| `ad6d812` | 恢复测试子进程使用当前 Python 3.10；支持独立源码导出，不改变恢复断言 |
| 本报告提交 | 最终免费回归、阻断说明、安全检查与交接 |

起始分支已有但未推送的 `3221643`、`09d512c`、`08cf3fc`、`6c418db`、`cd36765`、`f916336` 随正常开发分支推送保全。Runtime 与 Provider / 验证共改同一原生循环，采用一个有依赖闭合的代码提交；没有为了形式将其切成不能独立运行的补丁。

本轮新增提交没有依赖/lock 升级、SQL schema 迁移或用户配置变更；没有提交 API Key、临时 profile、数据库、构建产物或实验源码副本。

## 3. Runtime / Provider 合同核查

| 合同 | 实际结论 |
|---|---|
| 默认/可选 | Qwen3.7 Plus 保持默认，显式 profile 优先；DeepSeek V4.1 Flash 仅可选 |
| 原生 wire | Qwen 保留 `max_completion_tokens` / `enable_thinking`；DeepSeek 专属 adapter 使用 `max_tokens`，工具续答回传同 Run 私有推理；其他 provider 不注入该字段 |
| 私有推理 | ContextVar 共享可关闭 RAM 作用域，在公开 LangChain callback 前截获；退出、取消、异常、超时清空，迟到线程不能复活；不进入 SQL/SSE/UI/公开 checkpoint |
| 多工具 | 整批 ID/READ 权限/schema 校验，局部 Condition 顺序门；逐项 FixedRunner 预算/owner 栅栏、SQL 收据与 ToolMessage checkpoint；致命停止阻止后续项 |
| 恢复 | SQL 是执行权威；协议身份冻结。新 Qwen checkpoint 可按现有边界恢复且不重放；DeepSeek 含 assistant 的私有状态丢失、旧身份缺失或模型变更均在新调用前明确失败 |
| 输出预算 | DeepSeek 单次默认 8192，Qwen 4096，显式较小值优先；SQL 累计模型次数与工具次数分别计数；`length` 或没有最终正文不得成功 |
| RequiredOutputs | 格式/字面/数值及绑定核验明确分类，语义完整性未知保留 `unverified`；自然语言旧锚点不冒充确定性证明，真实结构/字面缺失仍失败 |
| 最终交付 | 核验说明通过元数据/执行记录展示，不追加正文；SQL task/run/outbox 与最终 SSE replace 一致；严格三行由 Electron 保持逻辑换行 |
| 阶段正文 | 不用于满足最终 RequiredOutputs，不自动获得 verified；严格格式最终正文不拼接阶段推导 |
| 教材/教学 | DeepSeek 原生路径复用固定检索和 EvidencePack；teach/summarize 的 chapter 先于正文；未扩展工具权限或开放循环 |

已阅读原 Astra ADR 与串行门二审补充，本轮未调用 Astra、未新增架构。

## 4. 本轮免费验证

| 验证 | 结果 / 证据 |
|---|---|
| 23 文件关键后端合同 | **314 passed**；`backend.log`，Python 3.10.21 / venv310 |
| 初次全量后端 | 1614 passed / 50 failed；`backend-full.log` |
| 生命周期局部修复回归 | **45 passed**；`lifecycle-fix.log` |
| 修复后全量后端 | **1616 passed / 48 failed**；`backend-full-final.log` |
| DeepSeek 恢复测试路径修复 | **39 passed**；`recovery-test-portability.log` |
| 独立已提交源码导出 | **133 passed**；`checkpoint-smoke-final.log` / `checkpoint-smoke-identity.json`，对应 `ad6d812`；不依赖本地排除的实验和原始录屏 |
| 前端 Vitest | **203 passed，45 文件**；`frontend-tests-final.log` |
| 桌面壳 Node 测试 | **15 passed**；`desktop-tests-final.log` |
| TypeScript / Vite | **通过**；`frontend-build.log`，使用已有 Node / node_modules，未安装或升级依赖 |
| macOS Electron | **FREE-VERIFIED**；S6 两轮三行与独立 unverified 状态、S5 实际数学工具；1280×820 / 1024×768 / 760×820 无横向溢出，截图已检查，`errors=[]`、`strict_dom_lines=3` |

本轮 Electron 使用正式 API/Runtime/SQL/SSE，Provider HTTP 为 Mock 公共历史响应回放；不称为新真实 Provider 验收。脚本禁止外部连接、使用隔离 `/private/tmp` profile/数据，已退出 Electron 与 QA 后端。

初次前端命令从根目录执行，误把 Node 桌面测试交给 Vitest；随后在 `frontend` 目录使用同一套现有测试通过。桌面端口测试初次沙箱 EPERM，经本机端口执行权限复测通过。独立源码导出初次因测试写死相对解释器路径失败，修复为 `sys.executable` 后复验。保留全部失败日志，没有删除断言或伪装为产品通过。

证据等级：本轮 **FREE-VERIFIED**；此前正式 S1、S5/S6 和 Qwen 真实结果为本轮的 **HISTORICAL LIVE**，原始报告中 `LIVE-VERIFIED` 标签仍表示当时实际运行。本轮 **0 付费模型请求**，没有 Benchmark；Windows/Android 实机及安装升级验收仍 **PENDING**。

## 5. 合并阻断与下一步

剩余 48 项失败：`test_policy_baseline_v01.py` 1 项、`test_policy_dataset_v0.py` 20 项、`test_policy_seed_v0.py` 27 项。

批准的 V0.1 固定源码 pins 与实际 `backend/services/decision/resolver.py`、`backend/tools/registry.py` 不一致，均触发 `source_content_digest_mismatch`。两文件在起始 `f916336` 已经漂移，当前 bytes 与该 HEAD 一致；不是本轮新增差异。详见 [frozen-baseline-drift.json](docs/qa/evidence/runtime-main-integration/frozen-baseline-drift.json)。这不是 48 个独立生产故障，但确实是待合并历史中尚未满足的冻结基线门槛。

原生命周期探针用“温度补偿”自然语言锚点断言确定失败，新语义合同合理返回 unverified。现改成显式 `literal` 缺失，原 `failed` / `passed=False` 断言保持；两项 Context Eval 回归恢复。此修复没有降低生产验证标准。

G3 尚未满足：不能宣布关键及受影响既有门槛全部通过。因此停留在已提交开发 Checkpoint，不执行 Main merge/push。没有尝试绕过分支保护，也没有创建掩盖失败的合并 PR。

下一步应单独复核这两处改动对 Policy V0.1 的行为影响，决定保留原冻结环境作为历史基线，或建立**新版本、经明确审核**的源码基线；保留旧 pins、样本、金标与故障校验。不得仅重算旧 hash、关闭漂移检查或回滚有效 Runtime 代码来获得绿色状态。完成对应 48 项及必要回归后，再 fetch 并进行正常主分支整合。

## 6. 安全与本地材料

- 当前 tracked / nonignored untracked 共 3522 个文件，以两把真实 Qwen / DeepSeek 凭证在 RAM 中做精确比较，命中 **0**；隔离 QA env/profile/SQL/WAL/SHM 精确命中 **0**。见 `privacy.json`。
- `origin/master..f916336` 新可达历史对象共 2131 个 blob，同样精确命中 **0**；见 `history-privacy.json`。后续收尾提交在当前扫描范围内。五个通用 key 模式文件为已有合成 canary / 脱敏测试说明，不输出值或密钥 hash。
- QA 保存器过滤凭证字段，并有实际 profile save → env writer 的免费测试。修复已经进入开发 Checkpoint，**尚未进入 Main**，因为合并被阻断。
- 历史 QA `local.env` 曾落盘真实凭证；当前清理与零命中不排除历史同步、备份或系统快照副本。用户仍需自行轮换当时使用的 **DeepSeek 与 Qwen API Key**；没有撤销或更改当前凭证。

## 7. 已知非阻塞边界

Python AnyIO/SWIG 的 6 条既有弃用提示及 Vite 大 chunk 警告保留；没有为了消除 Warning 扩大改动。历史公开响应/日志的原始行尾空白与 EOF 空行也保留，代码 diff 检查通过，不改写原验收文字来美化证据。

DeepSeek 丢失私有续答状态不能无损恢复；旧无身份 checkpoint 明确拒绝；语义、阶段推导和未全面绑定的公式保持 unverified；一次 S1 成功不证明 8192 的统计稳定性。这些边界不是本轮新的合并阻断，也不意味着 V1.0 Release Candidate 已完成验收。

## 8. Main 结果与 Mobile S3 交接

最终 Main SHA：**`898bec3ae520fe06d0b5ac486752499760091bac`**，本地 `master` 与 `origin/master` 保持一致且未改。没有 merge commit，合并后 Smoke Test **不适用**；本轮执行的是开发 Checkpoint 的独立导出冒烟。

开发交接：统一 `/api/chat/stream` 与 ExecutionEvent / LearningTask 状态继续生效；SQL 决定任务、预算、工具收据和最终答案，前端 reducer 不以迟到旧 run 覆盖新 run。会话游标仍基于权威 append-only 消息；暂停任务的只读 SQL 投影不写入消息历史，正式 outbox 消息替代同 ID 投影。取消以后不继续排队工具；恢复必须保留同 task/turn、身份及累计预算。

Mobile S3 可参考本次开发 Checkpoint 的接口与明确恢复边界，但不要将仍未整合的开发分支称作稳定 Main。旧移动端分支和 worktree 均保留，本轮没有移动端功能开发。

**结论：当前 Texa Runtime 尚未满足作为 V1.0 后续移动端开发的稳定 Main 基线条件；专项实现已验收并保存，但须先解决冻结 Policy V0.1 门槛并完成主分支整合。**
