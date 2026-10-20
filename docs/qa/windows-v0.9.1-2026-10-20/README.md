# Windows v0.9.1 检查安装包

用户明确授权 commit/push、构建 `texa_test_v0.9.1.exe` 并上传名为 `v0.9.1` 的新草稿 Release。本次只创建草稿，没有公开发布或改变正式更新通道。

- [草稿 Release](https://github.com/jayceto946-byte/texa/releases/tag/untagged-b43538064e1529272a99)，tag/title 为 `v0.9.1`；草稿页面需要有仓库权限的 GitHub 登录。
- [成功构建](https://github.com/jayceto946-byte/texa/actions/runs/39430872799)，Windows x64 **NSIS 安装包**，不是便携版。
- 构建源码：`0411aa5e594464069a8d652c9d7b9f1f538fbd07`。
- 内部版本：`1.0.1-commit.232.0411aa5e`。v0.9.1 是用户指定检查批次；内部 commit 版本用于可比较的更新顺序，避免从现有 1.0.0 误降级。
- 安装包：`texa_test_v0.9.1.exe`，258,842,561 bytes（约 246.9 MiB）。本地副本位于主目录 release/，不写入 Git。
- SHA-256：`3255575d6d1dad2803e2890eeedbbfb96eb30cf69de3bf7f1d6d176033da1bb3`。

## 验收

Windows runner 后端笔记合同48项、前端52文件/243项、桌面36项、lint、版本一致性、TypeScript/Vite生产构建全部通过。冻结后端 ONNX/SQLite/Chroma smoke 返回 `TEXA_FROZEN_SMOKE_PASS`，之后才打包与上传。

从官方 Actions artifact 下载 ZIP，核对 ZIP SHA-256 与 Actions 上传日志一致；提取实际 EXE 后核对本地 SHA-256/文件长度与 runner 构建身份及 GitHub Release 附件 digest/size 三者一致。确认 MZ、PE 与 NSIS 标记。PE 证书表长度0，确认为未签名测试安装包。

[上传回执](release-upload.json)中 `isDraft=true`、`tagName=v0.9.1`，安装包及 blockmap、commit 清单、build身份均为 uploaded。公开 GET release-by-tag 返回404符合草稿不可公开读取的状态，未把404当成未上传。

首轮 [6383a18 构建](https://github.com/jayceto946-byte/texa/actions/runs/39430217017) 在 Windows 路径规范化回归失败，未进入打包；0411aa5修正后完整通过。原测试断言保留，未跳过失败测试；最终回执提交另加强故障测试的前置状态/原因断言，本地10项通过，不改变本安装包的生产代码。

## 边界

这是未签名检查安装包，尚未进行 Windows 原生安装向导、实际覆盖升级或人工 UI 验收；不能把构建和冻结自检等同于这些操作已通过。包内含 commit 更新通道，但该通道仍需后续签名双平台发布和启用；本草稿不是正式自动更新源。

完整哈希与逐项检查见 [verification.json](verification.json)，构建身份见 [texa_test_v0.9.1-build.json](texa_test_v0.9.1-build.json)。
