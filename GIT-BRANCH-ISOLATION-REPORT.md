# Git 状态审计与 MacBook 分支隔离报告

日期：2026-10-09（Asia/Shanghai）。仓库：`/Users/jichengqian/Documents/ChatGPT/texa`；Darwin arm64 / MacBook。结论：已建立可恢复开发 Checkpoint 并推送独立分支；不等同于正式发布验收。

## 审计前后

| 项目 | 审计前 | 整理后 |
|---|---|---|
| Branch | `Texa_MacOS` | `feature/mobile-remote` |
| 代码 HEAD | `9b04c873b1e130d62a6f5fdadd2cc559f2cfa9db` | `4e8c3d492e837da8221f0c4ebf9f8c4d3c64d342`；本报告作为其后的独立文档提交 |
| Upstream | `origin/Texa_MacOS`，0 ahead / 0 behind | `origin/feature/mobile-remote`；Checkpoint 已成功 push 并建立 tracking |
| Working Tree / Index | 95 个 tracked 文件修改、227 个实际 untracked 文件；Index 空、无 unmerged entries | 194 个文件纳入 Checkpoint；全部原始文件保留；代码 Checkpoint push 后工作区与 Index 干净 |
| Stash / Worktree | Stash 空；共 4 个 Worktree（当前、2 detached、1 checkpoint-remediation） | 未使用 stash；原 4 个 Worktree 未切换或删除 |
| Remote | `git@github.com:jayceto946-byte/texa.git` | URL 保持；SSH 22 失败后通过 GitHub SSH 443 fetch/push |

首次 `fetch --all --prune` 的 SSH 22 连接关闭；使用命令级 SSH 443 完成 fetch。初始浅克隆已通过第二次 `fetch --all --prune --unshallow` 补全；`ls-remote --symref` 核实远端默认为 **master**，目标 Feature Branch 原先不存在。未执行 pull/merge/rebase，未改远端默认分支。

报告提交的最终 HEAD 可用 `git log -1 --format=%H -- GIT-BRANCH-ISOLATION-REPORT.md` 精确定位；报告不能把自身 SHA 写进自身内容。代码 Checkpoint SHA 上述固定，交付副本另附最终服务端核验。

## 历史、基线及归属

完整历史下，相对原 HEAD 的结果：

| 远端分支 | Merge Base（缩写） | 本地 ahead / behind | HEAD 文件差异数 |
|---|---|---:|---:|
| `master` | `898bec3` | 17 / 0 | 1020 |
| `Texa_MacOS` | `9b04c87` | 0 / 0 | 0 |
| `codex/checkpoint-remediation` | `773c57f` | 13 / 0 | 861 |
| `refactor-rename-to-texa` | `be20fea` | 26 / 0 | 1067 |
| `Refactor-ONNX` | `6d49b08` | 81 / 0 | 1270 |
| `refactor/decouple-services` | `96ae9d9` | 88 / 0 | 1380 |

- **公共历史基线**：`898bec3ae520fe06d0b5ac486752499760091bac`，是 HEAD 与远端默认分支的真实 merge-base；不是默认把最新 HEAD 认定为公共基线。此项证明共同历史，不证明所有业务已经发布签收。
- **已同步进度基点**：`9b04c87`，已在远端且包含 Mobile Remote S0、Notes/教材/Runtime 等共享成果。现有后续修复相互依赖，使用它作 Checkpoint 父提交，保留从公共基线至今的 17 个提交，不人为剥离必要共享代码。
- 历史确实交叉包含 `ddf7f3b` Runtime Policy、`7127964` Policy-SFT 冻结交付与 `9b04c87` Mobile Remote。作者邮箱相同，不能证明提交机器；本机 Reflog 明确记录 `7127964` 的创建及两次 amend，故不把它认定为外来 Windows 实验。工作树中的 V0.1 基准、理解适配、教材修复有既有 patch notes/审阅/回归记录，作为共享依赖保留；没有新 cherry-pick 或合入其他电脑实验。
- 本地原分支没有未推送 commit。未提交有效代码及关键 untracked 服务/测试/源码 pins 确有遗漏于 Git，已纳入 Checkpoint。相关远端分支全部为现有 HEAD 的祖先；未发现分叉需强行整合。
- 检查 `master..HEAD` 非 merge 提交的稳定 patch-id，无重复补丁组。`4687669` 的两父为 `9598930`/`773c57f`，后者即 remediation 分支，未发现错误合并证据。Index 无冲突项，代码中无冲突标记，未发现进行中的 merge/rebase/cherry-pick。
- **不可见边界**：GitHub 无法反映 Windows 未 push commit、工作区和 stash；不能据此声明两机已完全同步或准确识别全部 Windows 内容。

## 保护、修复与提交边界

1. 变更前建立 `refs/safety/branch-isolation-20261009/original-head` 及 24 个 Reflog 提交安全引用，保留包括修订前 Policy-SFT 提交的可恢复历史；安全引用不推送。
2. 本地备份：`/Users/jichengqian/Documents/Codex/2026-10-09/texa-git-github-texa-branch-macbook-5/work/git-isolation-safety/`，含验证通过的 `history.bundle`、322 个原始待提交文件的 `working-files.tar.gz`/SHA-256 manifest、working-tree/index 二进制 patch、原始 Index、refs/reflog/worktree/stash 快照；归档逐文件 hash 校验通过。忽略的模型、真实库、缓存未被改动，不需要搬入 Git。后续另存原始 `info/exclude`。
3. **实际修复**：全量测试首轮 1491 passed / 1 failed。`test_visual_terminal_stays_delivered_when_domain_write_fails` 用 `b"test"` 伪 PNG，新 S1 上传解码校验导致它在目标故障注入前退出。仅改用 PIL 生成真实 PNG，保留 final/pending/恢复恰好一次的原断言；没有放松生产上传校验。
4. Runtime/API/Config 核对：`original_file` 和图片 `preview` 均可选、旧调用路径保留；图片/文本有限正文 deadline 与 SSE 流分别处理；理解角色默认 off、独立配置且无回答模型 fallback；Policy 源码 pins 使用已审阅 V0.1，旧 V0 gold/pins 不覆盖。已通过对应合同与冷启动/故障隔离回归；未来两分支同时改共享文件仍有语义冲突风险。
5. 按逐文件清单提交 194 个文件，凭证形态/JSON检查通过，测试中的显式假 key 经核对仅为防泄漏夹具。新纳入的 `evaluation/fixtures/policy_dataset_v0_1` 是保留原样本的微型实现回归 fixtures，非训练数据集；冻结源码是 pins 审阅证据，非第二套生产实现。未提交模型权重、实际学习库、教材原文投影、密钥、缓存、安装包或构建产物。
6. 129 个原始诊断/日志/数据投影/预览文件 **原地保留**，逐路径写入本机 `.git/info/exclude`；并非删除后制造干净状态。完整清单在 `/Users/jichengqian/Documents/Codex/2026-10-09/texa-git-github-texa-branch-macbook-5/work/local-only-files.json`。旧报告中引用这些本地证据的链接在其他机器可能缺文件，必须读取报告摘要或另行安全交接，不能当已上传原始材料。
7. 临时分支 `checkpoint/macbook-20261009` 保留代码 Checkpoint；从它创建 `feature/mobile-remote`。原 `Texa_MacOS`/`master`/其他本地与远端分支未改。正常 push 成功，不强推、不自动合并回主分支。

## 验证与剩余风险

| 验证 | 结果 |
|---|---|
| Python 3.10.21 全量，离线隔离数据 | **1492 passed**，6 条既有弃用提示；首轮失败日志保留 |
| 前端 Vitest / Electron 单测 | **174 / 15 passed** |
| TypeScript / 全量 ESLint / Vite | 全通过；构建到本任务 work 临时目录；既有大 chunk 提示保留 |
| 从 Checkpoint `git archive` 独立导出再验证 | **254 passed**：S0/S1、effects、Policy V0.1、理解适配、远程读取；证明关键合同不依赖被排除的原始诊断或预览 |
| 空白、Index、工作区 | Checkpoint diff --check 通过；无 staged/unstaged/untracked 可提交改动；本报告单独提交后再核验 |

验证日志：`/Users/jichengqian/Documents/Codex/2026-10-09/texa-git-github-texa-branch-macbook-5/work/git-isolation-verification/`。未操作正式学习库或当前 frontend/dist，未调用模型、训练、迁移或重启正在使用的桌面服务。当前未再做 Android 真机、原生 Electron UI、Windows 或安装/升级/恢复验收；Android 图片与错题/笔记正式保存闭环、教材原页/人工核验仍依既有报告待验收，开发 Checkpoint 不提升为发布 GO。

## Windows 下一步

1. 先在 Windows 独立执行相同审计、fetch 与本地安全保护，列出未 push commits/未提交文件；不要直接 pull/rebase 覆盖现场。
2. 拉取 `origin/feature/mobile-remote` 后比较其与 Windows HEAD 的 merge-base/ahead-behind；重点核对 decision/router、policy/projection、question_understanding、API/Config、V0/V0.1 pins 与 SFT/benchmark 合同版本。旧冻结 benchmark 保留其原代码身份，不直接替换为 V0.1。
3. 按 Windows 的实际历史建立自身 Checkpoint 与 `feature/policy-model`；若该分支已存在先核验关系。不要未经 Windows 归属核对就从本次完整 Mobile 分支承接全部实验，也不要直接按文件名删共享依赖。
4. MacBook 后续只在 `feature/mobile-remote` 开发；Windows 在 `feature/policy-model` 开发。公共修复后续用明确审阅的 PR/有依赖说明的提交整合；本次未创建或修改 Windows 分支，未合并回 master/main。
