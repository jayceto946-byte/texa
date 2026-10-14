# Mobile Remote S0 实施与验证

日期：2026-10-08。基线 HEAD `71279642383ca144c0f3930197cf2b29c406edf5` 加工作区已有修改，未提交、未暂存、未覆盖原有修改。起始清单见 `baseline-status.txt`；原 `desktop/main.cjs` 关闭窗口修复保持不变。Python 使用 venv310 3.10.21；测试数据位于 /tmp，不修改现有教材、索引、Session 或数据库。

## 本次代码改动清单

- `desktop/main.cjs`：桌面托管后端和动态端口选择强制 loopback，保留原强制 token；停用遗留 LAN 采集开关（不删除其已有设置文件），不再生成 LAN 凭证 URL。只向本机主窗口提供实际 Serve 目标、实例身份及命令；显式按钮复制管理 token 到系统剪贴板，token 不通过 HTTP、状态对象或日志输出。SKIP_BACKEND 外接模式不提供 S0 凭证。
- `desktop/preload.cjs`、`frontend/src/types/electron.d.ts`：本机 S0 状态/复制 IPC。
- `backend/api/system.py`：受现有鉴权保护的只读 `/api/system/remote-ready`，仅返回回答模型就绪及强制 token 标志，不返回 profile 或凭证。
- `frontend/src/api/client.ts`：远程浏览器强制同源 `/api`，忽略/清除 desktop api_base；hash token 使用后移除，远程只保存在 sessionStorage，删除旧 localStorage token。401 清除 token 并回到连接门槛；文字 SSE 离线事件中断并报错，传输失败/缺失终止事件不当作完成。
- `frontend/src/components/RemoteConnectionGate.tsx`、`App.tsx`、`FirstRunGuide.tsx`：HTTPS 凭证连接门槛置于业务 Provider 外；通过后直接复用已有工作区，手机首次进入不重配模型。
- `frontend/src/components/settings/MobileRemoteS0.tsx`、`SystemHealth.tsx`：桌面设置显示动态端口/Serve 命令、复制临时管理 token，沿用现有视觉组件。
- `tests/test_mobile_remote_s0.py`、`frontend/src/api/remoteConnection.test.ts`：鉴权、只读就绪、远程 bootstrap、桌面 bootstrap、SSE 断开/无终止边界及 offline 回归。
- 本指南、验证记录、基线清单及 `patch_notes.md`：部署和真机验收交接。

## 已执行验证

| 项目 | 结果与限制 |
|---|---|
| Python security + S0 + chat stream reliability | 43 passed，6 个既有依赖弃用 warnings；ENV_PATH=/dev/null，DATA_DIR/PROGRESS_PATH 指向 /tmp |
| 前端 client + remoteConnection | 17 passed；包含无终止事件、reader 异常、browser offline 均报错；桩网络，不是真手机 |
| TypeScript / Vite production build | 通过；仍有已有大 chunk / 混合静态动态 import 警告，不在 S0 扩大处理 |
| 新增前端文件 ESLint | 通过 |
| Electron Node 检查与桌面单测 | main/preload 语法检查通过，14 passed。初次沙箱禁止端口绑定 EPERM；在授权的 loopback 测试环境重跑通过 |
| macOS Electron 开发启动 | 使用 `/tmp/texa-mobile-s0-desktop` 独立 userData，跳过模型/向量预热，启动 Python3.10 托管后端并载入现有首次设置页面；没有填写凭证或调用模型 |
| 运行实例 HTTP | 动态端口 58815，日志确认 bind `127.0.0.1`；页面 200，缺失 token 401，错误 token 401；无密钥记录 |
| 桌面退出 | 关闭本次隔离进程后 health 不可达，未遗留第二个后端 |
| 变更检查 | git diff --check 通过；现有改动保留 |

精简日志随本目录保存；不保存真实 token、模型密钥或业务正文。

## 尚未完成的真实验收

本环境未发现 Tailscale CLI/应用，未安装、登录、设置 Serve、Funnel 或系统网络。未连接真实手机、校园网/蜂窝网，未检查用户实际 tailnet Grants/ACL，**不能宣称未授权设备已被实际阻断**。网络访问隔离必须由有效 tailnet policy 及负向设备测试确认。

隔离桌面未配置模型/教材；没有真实模型请求，因此**已有教材/Session 手机读取、真实文字教材问答、手机 SSE 与引用展示、原数据桌面问答均未实测**。已有问答链路保持复用，相关离线流合同通过不替代上述端到端门槛。尚未验证 Windows/打包版、真实手机渲染、锁屏、睡眠、双端并发；S0 不新增恢复状态机，回前台需重读现有 Session/任务。

代码侧 S0 可交接；真机验收待按 [连接指南](../../mobile-remote-s0-guide.md) 执行。正式独立学习 token、设备授权、照片与移动布局属于后续阶段，不在本次开发范围。
