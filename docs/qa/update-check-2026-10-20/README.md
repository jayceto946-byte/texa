# 设置检查更新实测

2026-10-20，macOS 当前主目录源码构建，Electron 窗口地址 `127.0.0.1:51735`。本次只检查，不下载或安装应用，不修改发布状态、更新配置或学习数据。

## 实际桌面操作

在设置 → 关于与更新点击「检查更新」。界面当前版本为 `1.0.0`，返回「开发模式不执行自动更新。打包后的安装版会启用 GitHub Releases 更新。」见 [实际结果](electron-check-disabled.jpg)。当前源码入口不会拉取 `Texa_MacOS` 分支，也没有执行 Git 同步。

## 更新机制

- 前端 `SystemHealth.tsx` → preload IPC → `desktop/main.cjs` 的 `updates:check` / `updates:download` / `updates:install`。
- `configureUpdater()` 默认拒绝非打包运行；生产配置指向 `jayceto946-byte/texa` GitHub Releases。没有分支、commit 或 git pull 更新逻辑。
- 使用 electron-updater。检查发布清单、比较应用语义版本；用户点击下载后获取程序更新，点击重启安装后停止后端、处理未保存草稿并 `quitAndInstall(false, true)`。`autoDownload` 与 `autoInstallOnAppQuit` 均为 false。
- Windows 安装版使用 NSIS 更新包，Mac 使用 ZIP 应用更新；框架有差分下载及完整下载回退。它更新程序文件，不是在本机重新安装 npm/Python 依赖或编译仓库。

## 当时的远端只读结果

通过 GitHub connector 实时读取发布列表及 `/releases/latest`；直接 curl GitHub API 返回 403，未将该请求失败当作不存在发布。

- 最新预发布 `V0.9_pre_release` 仅有 Windows 便携测试包 `texa_test.exe`，源码 `24973dbc4a12695019ba8a8ed0142c3aa765cd0a`，包内版本仍为 `1.0.0`。没有更新清单和 Mac 文件，不包含本次 `218a164` 界面提交。
- GitHub `/releases/latest` 返回正式发布 `v0.2.0`，附件包括 Windows installer、blockmap 和 `latest.yml`，没有 `latest-mac.yml` / Mac ZIP。当前稳定应用默认不接收预发布；Release 名称改变也不会改变包内版本号。
- 全部所列发布均无 Mac 更新文件。另有模型资源发布，与程序更新包不同。详情见 [远端快照](releases.json)。

## 结论与边界

当前 Mac 源码运行无法通过设置更新到最新分支；已发布的测试包也不构成当前自动更新链路。开发路径要先把改动整合进当前分支，再重新构建启动；安装版要先从确定提交生成更高版本的平台更新包与清单、发布至相应通道，之后用户可在应用内下载并重启更新，无需每次手动打开网站重装。

本次未执行真实安装版下载、覆盖安装、签名校验、Windows UI 或升级后数据兼容测试，不声称整条自动升级已验收。
