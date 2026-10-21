# 未签名 Windows commit 更新验收

2026-10-21。用户明确不需要签名，要求安装版与源码版按提交获取修复，并授权提交、推送和打包上传。

## 已发布

- 源码：`da550b4827013bd71b6ab99a121e3aef024065f8`，分支 `Texa_MacOS`。
- [公开修复 Release](https://github.com/jayceto946-byte/texa/releases/tag/v1.0.1-commit.245.da550b48)：`v1.0.1-commit.245.da550b48`，预发布，未设置为正式 latest。
- [Windows x64 NSIS 安装包](https://github.com/jayceto946-byte/texa/releases/download/v1.0.1-commit.245.da550b48/Texa-Setup-1.0.1-commit.245.da550b48.exe)：259081611 字节，未签名。
- SHA-256：`a5b48e9e96ec58ab4a945a6c9f1855c08cfef9af5d4f7da68cef99ffc5035c53`。
- [成功构建与发布](https://github.com/jayceto946-byte/texa/actions/runs/39532998962)。原 `v0.9.1` 草稿仅被读取作为基线，未被此流程发布或覆盖。

## 实际验证

| 检查 | 结果 |
|---|---|
| Windows 相关后端回归 | 155 项通过，含 5 轮双会话并发计数与 13 项路径/锁边界检查 |
| 完整前端回归 | 52 文件、243 项通过，lint 和生产构建通过 |
| 桌面回归 | 40 项通过，语法检查通过 |
| 冻结源码 | 12 个已批准源码摘要保持原字节并通过校验 |
| 冻结后端 | SQLite、Chroma、ONNX、UTC/上海时区和前端资源自检通过 |
| 真实安装升级 | 从固定哈希的 v0.9.1 NSIS 安装旧版，使用真实 Electron NsisUpdater 下载候选包并执行 NSIS 覆盖安装，通过 |
| 安装后 | ASAR 内版本及完整 commit 正确；安装目录内的后端使用随包模型资产自检通过；现有用户目录代表性文件哈希不变 |
| 公开 GitHub 更新源 | 使用真实 NsisUpdater/GitHubProvider，从旧检查版版本发现本次修复，commit、分支、版本、文件 URL、长度及 SHA-512 一致 |
| 发布附件 | GitHub 服务端 SHA-256 与 CI 实际下载/升级使用的 EXE SHA-256 一致 |

`upgrade-verification.json` 是发布前原始回执，正文中的 `githubPublicFeedCheck: required after publication` 保持原样。发布后的实际检查单独保存在 `public-feed-verification.json`。

## 修复及运行方式

- Windows 安装版不再要求证书或七项签名 Secrets；代码推送后自动构建、验证并发布 commit 修复，纯文档提交不发包。应用内检查更新、下载后重启安装。差分不可用时下载完整包。
- 源码版固定跟踪 `origin/Texa_MacOS`，候选构建后快进并重启。工作区改动、分叉和依赖变更仍会阻断自动应用。本次依赖清单变化要求旧源码版先人工同步一次代码，Windows 还需同步 `tzdata`；macOS 无新增依赖安装要求。更新器不会自行安装依赖。
- 新包修复 Windows 时区缺失、备份/笔记校验 SQLite 句柄释放，以及 `\\?\` 路径前缀引起的虚假越界与锁身份差异。数据位置及格式保持原样。
- macOS 源码版沿用源码更新；当前 Electron 原生自动替换机制要求签名，本通道不包含 macOS 自动更新包，未签名 macOS 安装包采用手动替换。

## 验证边界与保留问题

- Windows 安装升级使用静默 NSIS 与真实更新器；为等待子进程结束，测试对启动函数作同步等待适配，保持更新器生成的安装命令。未进行 Windows 原生界面人工验收，也没有声称点过 Windows 设置页面。
- CI 的完整文件下载来自回环 HTTP 服务，服务文件就是实际发布候选；发布后另行验证了真实公开 GitHub feed。两者通过发布附件 digest 与升级回执绑定。
- 可选的 Mac 本地完整归档下载因网络中断没有完成，不把部分文件算作本地完整哈希校验。取得的 GitHub 安装包前缀包含有效 MZ/PE 头，证书表长度为 0。完整发布文件身份依赖 GitHub 服务端 digest、发布前完整哈希检查及实际升级回执三者一致。
- 全库后端尝试 `39526215635` 在取消前有 1723 通过、14 失败，见 `full-suite-attempt.json`。其中升级相关的版本顺序、时区、恢复和并发路径问题已被本次相关回归覆盖；四项离线 policy 快照与一项源工作区 SPA 前提失败未逐项处理，也未重新执行全库，因此不宣称全库全绿。

同目录保存公开发布元数据、CI 原始身份/升级回执、公开更新器检查、验证汇总和早期失败记录，不包含凭证或临时签名下载 URL。
