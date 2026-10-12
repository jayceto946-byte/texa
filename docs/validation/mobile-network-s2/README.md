# Texa Mobile S2 — Network Diagnostics 验收（2026-10-11）

交付入口：设置 → 高级与诊断 → 网络连接。普通区域显示连接观测、带时间的最近 RTT、重新读取／检测并尝试优化；展开 Network Diagnostics 后显示 Direct / Peer Relay / DERP、采样来源、Home DERP、冷却、路径变化和单独的 HTTP 完整请求耗时。390px 的诊断页使用全宽，并可返回设置分类。此功能不进入核心业务偏好。

## 已实现的控制边界

| 能力 | 行为与范围 |
|---|---|
| Auto（默认） | 使用 Tailscale 原生路径选择；恢复时读取状态，不主动 Ping |
| Prefer Direct | 当前浏览器会话可选择“恢复连接时自动优化”；启动、恢复前台、pageshow、online 时合并事件；非 Direct 且非 Offline 时最多三次 disco ping、单次超时2秒、进程总预算10秒、后端全局60秒冷却。只促成探测/NAT traversal，不强制路径，不阻断学习请求，中继仍可用 |
| 手动检测 | 与恢复探测复用同一预算和冷却；以最后一次实际回复判定 direct_observed / relay_observed，超时不宣布直连 |
| DERP 区域限制／自建 DERP | 必须由管理员修改 Tailnet derpMap，影响其他设备；本次不修改、不提供开关 |
| Peer Relay | 识别路径；部署与授权需要 Tailnet policy，路径由 Tailscale 选择；本次不部署、不提供手动强制切换 |
| 单连接强制 Direct/DERP、指定 Tokyo | 本次审计未发现受支持、可靠的逐连接 CLI 操作；不实现虚假控制 |

依据：[官方连接类型](https://tailscale.com/docs/reference/connection-types)、[CLI](https://tailscale.com/kb/1080/cli)、[DERP 配置](https://tailscale.com/kb/1232/derp-servers)、[Peer Relay](https://tailscale.com/docs/features/peer-relay)。字段与优先级核对 [ipnstate](https://github.com/tailscale/tailscale/blob/main/ipn/ipnstate/ipnstate.go) 和 [status CLI](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/status.go)，探测输出核对 [ping CLI](https://github.com/tailscale/tailscale/blob/main/cmd/tailscale/cli/ping.go)。

## 监控与成本

- 后端 `GET /api/system/network-diagnostics`：15秒缓存、single-flight 锁；诊断页可见时每30秒读取，隐藏／关闭时停止。没有后台线程持续 Ping 或常驻网络监测循环，历史是离散观测，不能保证捕捉全部变化。
- `POST /api/system/network-diagnostics/probe`：只探测已出现在本机 status 中的目标。优先 `TEXA_NETWORK_PEER_IP`，未配置仅接受唯一 Android；多 Android 时返回 peer_ambiguous，不猜测。展示的是 Mac→选定手机，不依据伪造转发头推断调用者，也不接受任意 Ping 地址。已有 token／跨站写入保护继续适用，响应 no-store。
- Passive status 只表示最近活动路径估计：Active + CurAddr 优先 Direct，其次 PeerRelay，再其次 Relay；空闲为 Unknown，不能用陈旧端点声称保持直连。Offline 使用控制面 Online=false，并非包交付测量。Home DERP 与实际 DERP 区域分开。
- RTT 仅来自显式 disco ping，不是 HTTP/SSE RTT。每条样本保留路径，不将初始化 DERP 与后续 Direct 汇总成稳态 P50/P95。采样时间为 CLI 输出收集时间、切换时间为被观察到的时间，不是精确底层事件发生时间。
- 最近64个 RTT 与64个变化在进程内；变化通过既有 RuntimeEvent 的 `system.network` 诊断命名空间最佳努力写入，仅含 origin_kind/capability/status/phase/reason_code，不创建学习 Session/turn，不保存设备地址、用户名、原始 CLI、密钥或内容。不扩展 RuntimeEvent schema，无数据库或依赖迁移。
- 只读诊断因 TypeError 网络失败可重试一次；不自动重放 Ping POST、学习问答或 SSE。恢复策略不修改 Session/task 身份与所有权，原确认中断及恢复门槛保持适用。

## 真实本机证据

[脱敏 live-diagnostics.json](live-diagnostics.json)：2026-10-11 15:08（Asia/Shanghai）一次有界探测，初始 Unknown/Home DERP sfo → 实际 DERP(sfo) 1167ms → Direct 43ms；紧接着被动 status 为 Direct/Home DERP 仍为 sfo。未控制或操作手机，未使用模型。

[后续 idle-observation.json](idle-observation.json)：15:15:37 被动读取显示 Online=false / Offline；两次观测之间没有追加主动 Ping。没有同步记录手机锁屏时间、网络、Tailscale后台状态，因此不能断言直连因锁屏退化，也不能据此得出稳态 DERP 延迟或校园网直连可行性。

沙箱内 CLI 最初因 preferences 不可读失败；允许读取本机状态后 CLI 正常。部署时如果 CLI 缺失、权限不足或未登录，界面显示 Unknown/诊断代码，学习链路继续可用。

## 自动化与实际视觉验证

- Python 3.10.21 / venv310：新监控、S0 鉴权、RuntimeEvent 22项通过；S1、LearningTask 状态机、Chat SSE、跨层恢复63项通过，共85项。覆盖 DERP→Direct、Direct→DERP、Idle→Unknown→Direct、Peer Relay、CLI失败、歧义设备、超时、冷却、有界记录、脱敏及 token。
- 前端全量42文件191项通过：新增恢复、hidden/offline、冷却、诊断 GET重试、不重放 POST、诊断与主动请求分离、查询期间转后台不探测；延迟碎片化中文／公式 SSE 保留 conversation/turn、只提交一次；原断流与迟到 run 合同继续通过。这是传输夹具，不等同真实 DERP SSE 实测。
- Electron 既有15项合同通过；TypeScript、相关 ESLint、Vite 构建通过（已有大 chunk 提示保留）。使用已配置的 bundled Node，无依赖重装。
- [ui-results.json](ui-results.json)：独立 Chrome 合成夹具在390×844、760×820、1024×768、1280×820下无横向溢出，手动动作恰好一次，DERP→Direct结果与 Unknown禁用状态通过。实际查看 [390截图](network-390.png)、[1280截图](network-1280.png)，窄屏修正后重新验收。没有本轮原生 Electron 页面或 Windows 渲染证据。
- 可复现脚本：`scripts/mobile-network-s2-smoke.mjs`，需要已有 Playwright 模块路径及 `TEXA_BENCH_BROWSER` 指向已安装浏览器；仅合成数据／独立浏览器，不连接用户后端、手机或模型。

## 一次集中实机验收（待做，不能用离线合同替代）

使用更新后的正常桌面构建，保持原 Serve 映射，不改 Tailnet／防火墙。默认 Auto 完成以下连续流程，再仅在恢复失败时勾选自动优化作对照；不要用持续 Ping 保活。

1. 手机移动数据打开现有 Session，记录检测后的 Direct 与 RTT；锁屏5分钟、30分钟后唤醒。先被动读取再按需主动检测，记录恢复是否先走 DERP、多久返回 Direct。记录实际锁屏／唤醒时间，区分控制面 Offline 与真实连接失败。
2. 在同一次流程切 Wi-Fi↔移动数据，并在可用时补校园 Wi-Fi；检查状态、Session ID、已有正文和权威 task状态。无法直连时必须仍能通过中继访问。
3. 在真实观察到 DERP的时段运行一次正常 SSE；确认正文逐步到达，切网／锁屏后不伪造完成、不重复用户问题。网络恢复后先重新读取原会话／任务，只有后端确认可恢复才使用原恢复入口。
4. Direct→DERP 是否出现由真实网络决定，不通过封禁 UDP 或更改全局设置强制造成。记录断流、HTTP完整耗时和实际路径观测各自的时间；不把 HTTP 或 LLM等待写为网络 RTT。

本工作区源码与 frontend/dist 已构建；未重启或部署用户正在运行的 Desktop/Serve，不能宣称既有手机入口已加载此版本。

## 用户重新连接后的复测（2026-10-11 15:21）

用户明确报告手机已重新连接 Tailscale 后，运行同一有界探测一次。被动状态初始为 Unknown / Home DERP lax；三次实际回复为 DERP(lax) 1662ms、DERP(lax) 923ms、Direct 41ms，随后的 status 也确认 Direct，Home DERP 仍为 lax。再次复现中继→直连升级；只有一个 Direct RTT样本，不能宣布稳态或锁屏保持通过。原始脱敏证据：[live-retest-20261011T072149Z.json](live-retest-20261011T072149Z.json)。未追加持续 Ping 或修改网络配置。

## 用户报告锁屏后的复测（2026-10-11 15:23）

用户明确报告手机已锁屏。先被动status读取为Unknown/Home DERP lax（空闲不据旧端点宣布保持）；随后一次三次探测的实际回复全部为Direct：45ms、40ms、42ms，紧接着status确认Direct。首次回复即为Direct，本次未观察到DERP回退，说明该次锁屏状态下可直接通信。探测本身会触发路径发现，且未记录准确锁屏起点，因此不能证明全程保持直连，也不能外推5/30分钟或Android深度休眠。脱敏证据：[locked-retest-20261011T072302Z.json](locked-retest-20261011T072302Z.json)。未追加持续Ping或修改设置。
