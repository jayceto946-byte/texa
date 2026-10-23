# 安装版静默重启更新

## 行为与边界

`desktop/main.cjs` 的安装版更新分支由 `quitAndInstall(false, true)` 改为 `quitAndInstall(true, true)`。用户在应用内完成下载并点击“重启更新”后，Windows NSIS 在后台更新现有安装并自动运行新版，不再主动展示安装向导。首次手动安装仍保留安装目录选择；Windows 需要的系统权限确认不由此绕过。

继续使用现有的下载校验、commit 分支身份、用户数据位置和关闭准备流程；不在普通退出时自动安装，不自动下载，也不在工作中强制重启。源码启动仍走既有 staged source updater。没有数据库/索引/依赖或更新协议迁移。

本地实际依赖为 `electron-updater 6.8.9`：读取其 BaseUpdater/NsisUpdater 实现确认两个布尔参数的含义。该版本不同于官网 next/v27 的新 options-object API，本次不升级依赖或采用后者的新接口。官方 [NSIS 说明](https://www.electron.build/v26/docs/nsis/) 与 [Auto Update](https://www.electron.build/docs/features/auto-update/) 仅作平台合同参考，以项目实际安装版本为准。

“不显示安装向导”与“每次只下载很小补丁”分开验收：生产更新器保留默认差分下载支持，现有发布流水线携带 blockmap；差分条件不满足时更新器仍可回退完整包。本轮未测量下载节省比例，不新增自制二进制补丁格式，也不宣称已完成差分实网验收。

旧客户端自身仍执行旧的非静默调用，因此更新到首次包含本修复的版本时仍可能出现安装向导；之后才使用新参数。

## 验证

- `cd desktop && npm test`：53 passed，包含新增 5 项回归；测试临时 loopback 端口在允许绑定的环境执行。
- `cd desktop && npm run check`：通过。
- `git diff --check`：通过。
- 新增回归直接执行生产 `installAppUpdate` 和其 IPC handler：下载未完成/草稿未保存/非本地调用会阻止安装；后端未退出前不调用安装；重复点击合并；源码更新仍应用后重启。
- 真实已安装 NsisUpdater 的 `install -> doInstall` 代码收到生产调用参数后生成 `--updated /S --force-run`，进程启动由夹具替代，没有在开发机执行安装程序。该测试不模拟真实 Windows 权限、程序占用或 NSIS 窗口。
- 初次测试因 VM 与测试线程的微任务时序差异，等待后台关闭的夹具尚未建立即被调用；改为等待一个事件循环轮次后，同一行为断言通过。产品流程没有为该失败放宽条件。

本轮没有 Windows 真机/安装包覆盖升级验收，也没有发布版本。此前流水线已有实际 NSIS 静默覆盖升级检查（`scripts/verify-windows-commit-upgrade.cjs`）；它不能代替本次客户端完整退出、替换、重启的真机验收。不更改教材、用户记录、Tailscale 或模型配置。
