# Commit 更新通道上线操作

源码桌面端固定跟踪 `origin/Texa_MacOS`。安装版从同一分支提交构建的平台更新包获取修复，不在用户机器运行 Git 或重新构建 Python。安装版仍需下载构建产物；框架可差分下载，失败时回退完整包。

## 1. 配置签名

登录 [Actions Secrets](https://github.com/jayceto946-byte/texa/settings/secrets/actions)，逐项创建 **Repository secret**，不要把密码放入聊天、源码、工作流文本或发布附件。

| Secret 名称 | 内容 |
|---|---|
| `WINDOWS_CSC_LINK` | 包含私钥的 Windows 代码签名 `.pfx`/`.p12` 文件的 Base64 |
| `WINDOWS_CSC_KEY_PASSWORD` | 上述证书导出密码 |
| `MAC_CSC_LINK` | 包含私钥的 Developer ID Application `.p12` 文件的 Base64 |
| `MAC_CSC_KEY_PASSWORD` | 上述证书导出密码 |
| `APPLE_ID` | 用于公证的 Apple 开发者账号 |
| `APPLE_APP_SPECIFIC_PASSWORD` | 该账号的应用专用密码 |
| `APPLE_TEAM_ID` | 对应开发者团队 ID |

当前工作流使用可导入的证书文件。如果 Windows 凭证实际是 USB 硬件密钥或云签名服务，需要调整签名接入，不能把硬件或云账号直接填作 PFX。不要将私钥证书上传为公开下载文件。

在自己的 macOS 终端中，可将证书编码到剪贴板，然后直接粘贴到 GitHub Secret 输入框；该命令不打印证书正文：

```sh
base64 -i "/absolute/path/to/signing-certificate.p12" | tr -d '\n' | pbcopy
```

分别处理两份证书，填完后清空剪贴板。密码只在 GitHub Secret 输入框中填写。格式依据 [electron-builder v26 签名说明](https://www.electron.build/v26/docs/features/code-signing/)；GitHub 操作见 [Repository secrets 官方说明](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)。

## 2. 构建及验收

在 Actions 的 `Texa commit updates` 中，选择 `Texa_MacOS`，手动运行；`publish` 保持 `false`。预检仅报告配置是否存在，不能证明证书有效。两平台必须继续通过测试、冻结后端自检、签名、公证与产物清单检查。

下载 Windows x64 和 macOS arm64 Actions 产物，完成原生启动、旧版覆盖升级、学习数据保留、检查更新及重启后的 commit 身份核对。首次启用签名通道需要安装一次包含 commit 通道的签名包；旧稳定版不会因远端源码变化而自行切换到该通道。

## 3. 启用自动发布

验收通过后，在 Actions Variables 创建 **Repository variable** `TEXA_COMMIT_UPDATES_ENABLED`，值为 `true`。手动运行同一 workflow 并选择 `publish=true`，或推送后续修复提交。两平台成功后才发布相应 commit 的预发布 Release，保留现有正式版 latest 标记。

原有 `v0.9.1` 检查包仍保持草稿。正式 commit 更新使用独立的 `v1.0.1-commit.<count>.<sha8>` 类标签；不需要把该未签名检查草稿直接公开。

## 当前实测状态（2026-10-20）

- 源码 `0d25eddfa5fd3a1e7ed9dfdeea0ebca4eba2da1d` 已推送；39 项桌面回归、语法与 YAML 检查通过。禁止通道降级，并在发布前校验双平台附件实际哈希、尺寸和 commit 身份。
- [远端预检 39437490894](https://github.com/jayceto946-byte/texa/actions/runs/39437490894) 报告上述 7 项配置全部缺失、发布开关关闭；构建和发布按预期跳过。
- 用户确认已有凭证但尚未配置，等待通过 GitHub 安全录入。正式签名构建、原生覆盖升级及上线仍未完成。
