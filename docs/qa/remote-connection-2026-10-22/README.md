# Windows 手机连接与 iPad 诊断修复

本次修改位于 `Texa_MacOS` 工作区。用户反馈出现在 Windows 的“手机连接”设置，无法生成访问地址；未访问用户设备，未把本地夹具验收描述为 Windows/iPad 真机通过。

## 修改

- Electron 使用 Windows 路径拼接，并依次查找 ProgramW6432、ProgramFiles、ProgramFiles(x86)、标准安装位置与 PATH；已缓存程序消失时重新发现。后端补齐相同的 Windows 安装位置查找，保留 macOS 和 PATH 行为。
- 首次安装返回 JSON `null` 的 Serve 配置按“尚未创建共享”处理，允许开启入口。非法 JSON 仍阻断写配置。
- 区分 CLI 缺失、未登录、未连接、服务不可达、权限不足、版本不支持、超时、HTTPS 未启用、共享查询/写入失败。原始命令输出和登录 URL 不进入界面。HTTPS 设置引导只使用固定官方管理页，不复用 CLI 返回的授权链接。
- 开启/关闭后的状态查询失败不能当作操作成功；刷新设置页会移除旧错误提示。保持实际动态端口、现有映射所有权与 Funnel 保护。
- 诊断自动候选覆盖 Android、iOS、iPadOS；多个移动设备仍返回 ambiguous，只有明确指定的已知 peer 才能探测。不根据设备名称或开发者账户绑定目标。

## 验证

| 检查 | 结果 |
| --- | --- |
| `venv310/bin/python -m pytest -q tests/test_network_diagnostics.py tests/test_mobile_remote_s0.py` | Python 3.10.21，26 passed；DATA_DIR 使用临时目录，事件写入 mock；保留既有 Starlette 弃用提示 |
| `cd desktop && npm test` | 48 passed；第一次受沙箱 loopback bind EPERM 影响为 47/48，在允许临时本地端口的环境重跑通过 |
| `cd frontend && npm run build` | TypeScript / Vite 通过；保留既有 MathLive 大 chunk 提示 |
| 两个修改组件的 ESLint | 通过 |
| `npm test -- src/api/remoteConnection.test.ts src/api/networkDiagnostics.test.ts` | 13 passed |
| `scripts/qa-remote-connection-electron.mjs` | macOS 真实 Electron + 生产渲染器/真实 preload/真实 remote service，经 IPC 执行 Windows CLI 夹具；31 项检查通过，见 [results.json](results.json) |

Electron 覆盖 1280×820、1024×768、760×820：从空 Serve 配置开启、生成当前用户地址、复制、关闭、HTTPS 未启用、固定设置链接、错误脱敏、长文案与横向溢出、刷新清除错误并重试，以及权限不足/CLI 缺失和多设备诊断。截图已人工查看开启态和窄窗口 HTTPS 错误态；没有改变布局与主题。

QA 中修正了两处测试夹具问题：生成临时主进程脚本时的 Windows 路径双重转义；在当前桌面布局中错误地要求显示“返回设置”按钮。后一轮失败保留于 [fixture-navigation-failure.json](fixture-navigation-failure.json) 及同名截图，不计为产品通过；最终结果独立保存。

未执行原生 Windows、真实 Tailscale Serve/证书授权、iPad Safari 或 Windows 安装包验收；未发布安装包。所有 CLI 配置操作均为进程内夹具，正式学习资料、配对令牌、Tailscale 设置和模型服务不参与验证。

## 外部合同核对

使用 Tailscale 官方 [Serve 命令说明](https://tailscale.com/docs/reference/tailscale-cli/serve)、[Serve 功能说明](https://tailscale.com/docs/features/tailscale-serve) 和[官方实现](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/serve_v2.go) 核对 Serve 与 HTTPS 的区别及命令形式。固定恢复入口为 `https://login.tailscale.com/admin/dns`，使用用户自己的登录会话。
