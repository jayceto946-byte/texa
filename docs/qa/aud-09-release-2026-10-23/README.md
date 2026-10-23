# AUD-09 发布资源隔离验收

日期：2026-10-23，Asia/Shanghai。修复在 `Texa_MacOS`，叠加原审计七项修复；图片恢复已提交于 `e870e3b`。本次没有迁移数据、安装依赖、调用付费模型或构建完整 Texa 安装包。

## 实现与结果

macOS 用 mktemp、Windows 用 GUID 创建专属空 staging，Vite 显式接收 `--outDir` 与 `--emptyOutDir`；PyInstaller 仅收录该目录到原有的 `frontend/dist`。退出清理自身 staging。普通构建的 `emptyOutDir:false` 与旧手机资源保留策略不变。

| 验证 | 结果 |
|---|---|
| 发布脚本回归 | 3 passed，替身 npm/Python 执行真实 macOS shell 脚本；连续两版、带空格路径、前后端失败清理、其他构建目录保护；静态中间件旧chunk返回200 |
| 真实两版 Vite | 每版 395 文件，42,845,254 bytes；两次独立 staging |
| 最小真实 PyInstaller | 两版均逐文件/哈希匹配 staging，冻结探针启动返回 AUD09_PAYLOAD_OK 395 |
| 服务目录保护 | 前后 3921 文件，112,717,031 bytes，全量哈希相同 |
| 定点后端 | 31 passed，包含新构建回归、原审计回归、工具协议、静态资源、发布验证/许可门槛 |
| 全量后端 | 2166 passed / 3 failed，101.69秒；同原有 Policy 冻结schema/绑定失败 |
| 前端 | 251 passed，lint通过；TypeScript/Vite由上述两次真实构建覆盖 |
| Electron单元 | 53 passed；第一次沙箱回环监听EPERM，允许监听后同套通过，初次日志保留 |

`payload-verification.json` 包含两版完整文件清单、大小及SHA-256。`payload-verification.log` 为精简汇总，`vite-*.log` 与 `pyinstaller-*.log` 为真实构建日志。`backend-full.log`、`frontend.log`、`lint.log`、`desktop*.log` 为此次补跑。原审计证据不覆盖、不计为新的实测收益。

## 复现

使用已有 venv310 Python3.10、Node/npm 与本地依赖，从仓库根目录执行：

```sh
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q tests/test_release_frontend_isolation.py tests/test_audit_regressions.py tests/test_tool_calling_audit.py tests/test_static_asset_compression.py tests/test_standard_release_validator.py tests/test_release_content_gate.py
venv310/bin/python docs/qa/aud-09-release-2026-10-23/verify_payload.py
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix desktop test
```

真实payload探针只冻结一个读取内置frontend/dist的最小Python程序，验证 `--add-data` 的目录及字节身份，不加载应用后端。脚本会覆盖本目录同名构建记录；需要保留旧记录时先另存。macOS原生执行通过，Windows无本机PowerShell，仅审阅对应脚本；Windows CI使用的入口已同步，但未在本次本地验证中执行。完整安装、升级、回滚及真实手机旧shell仍未验收。

## 提交边界

仅提交本次AUD-09与原审计的无关修复及证据，共享Runtime与patch_notes按hunk选择；搁置功能及其开关保留未提交。原审计 `backend-final.log` 包含范围外实现traceback，原始文件保留本地，提交 `backend-final-summary.md` 的原始hash、失败计数及摘要；原始失败结论在三份报告中仍保留。

## 暂存源码独立验证

通过 `git checkout-index --all --prefix=<临时目录>/` 导出实际暂存源码，只链接已有 node_modules，随后在临时目录执行同一31项定点后端（通过）、前端249项（通过）、lint与TypeScript/Vite生产构建（通过）。工作树的251项包含未纳入提交的其他前端用例，不能用该数量代表提交版本。日志为 `staged-backend.log`、`staged-frontend.log`、`staged-lint.log`、`staged-build.log`。

真实macOS Electron加载暂存版本的production renderer，12项通过：双向迟到分页、正常双向分页去重、同ID重载失效、公式、三档窗口及无renderer异常。`electron-aud09-staged/`保留首次结果，其中760截图捕获到侧栏过渡中间态；QA脚本补充等待目标窗口宽度并在截图时禁用动画，复跑 `electron-aud09-staged-stable/` 仍12项通过。三档截图已查看，稳定760布局无过渡侧栏遮挡，1280/1024公式与输入区正常。两组目录位于原审计证据目录，日志为本目录 `staged-electron*.log`。这是内存HTTP夹具，未运行付费模型或完整后端，不作真实端到端性能对比。

源码、脚本和文档的空白检查通过；原始工具日志保留其尾空格/空行，不为通过格式检查改写实测记录。
