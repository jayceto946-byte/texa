# 按 commit 更新：实现与验收

2026-10-20。用户确认安装版和源码版都需支持。实现复用「设置 → 关于与更新」，普通使用者无需手动比较 Release 名称或反复下载安装包。

## 源码运行

`desktop/source-updater.cjs` 固定主工作区 `origin/Texa_MacOS`，仅接受配置的 Texa GitHub origin。检查远端后显示具体提交；本地改动、未跟踪文件、分支错误或分叉会阻止自动应用。依赖清单、数据库、迁移、嵌入资产等变更要求完整升级或人工处理，不自动运行 npm/pip install。

流程：检查 → 准备修复 → 应用并重启。准备时通过 `git archive` 将检查时确定的提交导出到 Git 元数据目录，复用现有 Node 依赖进行 TypeScript/Vite 构建，并用现有 Python 3.10 对后端源码做编译检查；通过后再次检查主工作区。应用时先执行现有草稿/任务退出握手并停止后端，替换构建资源，再以 `merge --ff-only --no-overwrite-ignore` 更新源码，成功后重启。失败恢复旧构建；不自动 stash、reset、切分支或覆盖 ignored 本地文件，不修改学习数据库与教材索引。

真实桌面点击已查询远端成功：运行提交 `161aadbd`，返回「当前提交已是分支最新；工作区另有本地改动，尚未包含在提交中。」没有在含其他开发工作的真实工作区应用更新。

- [1280×820](source-check-1280.jpg)
- [1024×768](source-check-1024.jpg)
- [760×820](source-check-760.jpg)

## 安装版

继续使用 electron-updater 与平台签名更新，不在普通用户电脑安装 Git/Python 构建环境。新 `commit` 通道只接收同分支、带完整 commit 身份且版本后缀与 SHA 对应的构建；缺少身份时停止下载。显示源提交，用户下载后重启更新。差分下载沿用框架，无法差分时可回退完整下载，不保证每次都是很小的文件。

`scripts/prepare-commit-update.cjs` 在 CI 中为确定的 SHA 生成可比较的 `1.0.1-commit.<history-count>.<sha8>` 类版本，绑定 package、锁文件与 VERSION，并在 `commit.yml` / `commit-mac.yml` 加入 sourceCommit / sourceBranch。这里只改变 CI 构建副本，未改变当前工作区应用版本和依赖。

`.github/workflows/commit-updates.yml` 为 Windows x64 和 macOS arm64 分别执行测试、冻结后端 smoke、构建和签名验证。两端完成后才一起发布预发布修复，正式发布的 latest 标记保持原样。Mac 选择 `macos-14` 原生 arm64 runner，依据 [GitHub 官方 runner 列表](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。

## 安装版启用前仍需完成

1. 将实现纳入目标分支，配置 Windows 与 Mac 签名凭证、Mac notarization 凭证。未读取或导出密钥，本次未确认仓库 secret 配置是否齐全。
2. 手动执行 workflow 验证首个双平台构建；工作流的 publish 输入默认 false。
3. 完成两端真实安装升级验收后，设置仓库变量 `TEXA_COMMIT_UPDATES_ENABLED=true`，启用分支提交后的自动构建与发布。本次未设置该变量、未触发 CI、未发布应用。
4. 现有旧包需安装一次包含 commit 通道的新包，之后才能在应用内按提交获取修复。旧包无法靠本次源码改动自行获得尚不存在的更新能力。

## 实测与边界

- 源码更新隔离 Git 仓库测试覆盖快进成功、脏工作区、依赖变更、构建失败、准备后新改动、分叉、资源替换失败及 ignored 文件保护。额外使用真实 TypeScript/Vite 对候选归档执行构建并验证提交更新。
- commit 版本和清单测试覆盖身份一致、错误分支/版本拒绝及 Mac 清单注入。桌面完整测试（36 项）与前端 52 文件/243 项测试通过；修改前端文件 lint、类型检查、生产构建与 diff 检查通过。
- 原生 macOS Electron 检查正常显示比例的三档尺寸，未裁切控件；源码检查实际连接 GitHub。源码应用成功和失败在临时本地 Git origin 内执行，未把夹具通过当成真实安装升级通过。
- 未验证真实 Windows/Mac 安装包覆盖升级、代码签名、notarization 或上线 CI。发布机制已准备，安装版尚不能宣称已上线可用。
