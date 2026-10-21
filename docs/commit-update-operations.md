# Commit 更新通道操作

2026-10-21：按用户要求使用未签名 Windows 安装包。Windows 构建和发布不再需要签名证书，也不再依赖仓库签名配置或 `TEXA_COMMIT_UPDATES_ENABLED` 变量。

## Windows 安装版

向 `Texa_MacOS` 推送代码会自动构建、验证并公开发布对应 commit 的 Windows x64 NSIS 更新。仅文档变更不构建。手动执行 workflow 时 `publish` 默认 false，可先获取 Actions 产物。

流程：绑定完整 commit → 后端/前端/桌面测试 → 冻结后端自检 → 未签名打包 → 清单/哈希校验 → 从 v0.9.1 检查包实际覆盖升级 → 发布 commit 预发布 Release。失败时不发布，现有正式版 latest 标记与 `v0.9.1` 草稿保持原样。

应用内「设置 → 关于与更新」检查公开 GitHub Release，下载后重启安装。框架可差分下载；首次下载或差分不可用时下载完整安装包。安装版从打包产物获取修复，不在普通用户电脑安装 Git、Python 或构建依赖。文件校验保留 SHA-512、长度及分支/commit 身份，禁止降级；用户已明确选择不要求 Authenticode 签名。

旧稳定包需要先安装一次包含 commit 通道的新包。已经安装 v0.9.1 检查包的用户已有该通道。内部版本为 `1.0.1-commit.<count>.<sha8>` 类格式，v0.9.1 是原检查包批次名称。

## 源码版

固定跟踪 `origin/Texa_MacOS`：检查 → 准备修复 → 应用并重启。归档指定提交并构建通过后才快进当前工作区；本地改动、分叉、依赖和数据格式变更会阻止自动应用，不自动 stash/reset、切分支或重装依赖。macOS 与 Windows 源码运行都使用这条更新路径。

## macOS 安装版边界

当前采用的 Electron/Squirrel.Mac 自动替换机制要求签名；本 Windows 更新 Release 不提供 macOS 自动更新包。无开发者签名的 macOS 包可独立构建并手动替换，不应把它宣称为已支持自动覆盖升级，也不修改系统安全设置。

依据：[Electron autoUpdater 官方说明](https://www.electronjs.org/docs/latest/api/auto-updater)，[electron-builder v26 Windows 配置](https://www.electron.build/v26/docs/win/)。

## 验收记录

- 原签名门槛预检 39437490894 报告凭证为空。用户随后明确不需要签名；此前要求配置七项 Secrets 的步骤已撤回。
- 本次改为 Windows 独立发布，不再因 Mac 签名状态阻断。实际构建/升级回执见相应 Release 的 `upgrade-verification.json`，公开发布之后还需核对真实 GitHub feed。
- CI 升级验证使用真实 Electron NsisUpdater、回环 HTTP 清单下载和真实 NSIS 覆盖安装；校验包内版本/完整 commit 与现有用户文件夹内代表性夹具不变。它不等同于人工 Windows UI 验收或公开网络下载实测。
