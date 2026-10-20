# Windows 检查包交付

- 打包源码：`24973dbc4a12695019ba8a8ed0142c3aa765cd0a`，分支 `Texa_MacOS`。本记录为构建后的文档提交，不改变包内源码。
- 文件：本地 `release/texa_test.exe`，Windows x64 portable，未签名，241,547,307 字节（约 230 MiB）。构建使用空白 Standard seed，不包含本地教材、笔记、会话、凭证或其他未提交工作。
- [最终 Windows 构建](https://github.com/jayceto946-byte/texa/actions/runs/39353263515)：成功，9m10s。[官方产物](https://github.com/jayceto946-byte/texa/actions/runs/39353263515/artifacts/12234880301)，Actions 保留 14 天，本地 EXE 不受该期限影响。
- Windows 实测：笔记后端 48、前端 239、桌面 24 项测试、lint、构建及 Standard 内容/模型资产校验通过；冻结后端实际 SQLite/Chroma/ONNX 查询与临时目录清理通过。没有调用付费模型。
- 下载 ZIP 已核对官方 SHA-256；提取后核对 EXE 哈希、长度、MZ/PE 文件头及源码提交。详见 [verification.json](verification.json)。
- EXE SHA-256：`ec0a83f69429a5bef7e2e054e572488eea5b4084d6405601997dabce1c2eb15b`。
- Windows UI 人工视察仍待完成；macOS 原生截图与鼠标验证见既有笔记证据。不能用后端 smoke 代替 Windows UI 体验验收。

构建中依次修复了中文测试样本默认编码、自检数据库句柄释放、electron-builder 命名参数。原失败记录保留：[编码](https://github.com/jayceto946-byte/texa/actions/runs/39351437598)、[句柄](https://github.com/jayceto946-byte/texa/actions/runs/39351845315)、[命名参数](https://github.com/jayceto946-byte/texa/actions/runs/39352629608)。没有跳过或放宽检查，没有发布正式 Release 或改变签名/更新策略。

## Release 附件

按用户要求创建、并经明确批准公开发布 [V0.9_pre_release 预发布版本](https://github.com/jayceto946-byte/texa/releases/tag/V0.9_pre_release)，附件 `texa_test.exe` 已上传，远端大小与 SHA-256 一致，并重新下载核验。原创建状态为草稿；2026-10-20 20:45（Asia/Shanghai）经用户批准公开发布，保留 prerelease=true。原有 Release 附件及更新清单保持原状。回执见 [release-upload.json](release-upload.json)。一次性上传流程完成后移除，执行源码与日志保留在对应提交及 Actions 记录。

公开发布状态及附件直链见 [release-publication.json](release-publication.json)；[texa_test.exe 下载](https://github.com/jayceto946-byte/texa/releases/download/V0.9_pre_release/texa_test.exe)。一次性发布流程完成后移除，完整执行记录保留在 Git 历史及 Actions。
