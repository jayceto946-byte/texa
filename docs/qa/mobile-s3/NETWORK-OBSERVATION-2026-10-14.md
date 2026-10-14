# 手机连接被动观测 — 2026-10-14

采样时间：2026-10-14 10:32:06（Asia/Shanghai）。用户明确表示手机Tailscale已开启，并要求记录当前DERP/Direct状态。

`tailscale status --json` 被动读取后脱敏；唯一Android peer：Online=true，Active=true，CurAddr为空，PeerRelay为空，Relay=lax。按照现有 `backend/services/network_diagnostics.py` 的判定合同，本次观测为 **DERP（lax，洛杉矶）**，没有当前Direct端点证据。

计数：RxBytes=47060，TxBytes=373372；均为采样时累计值，不是吞吐测试。BackendState=Running。

未主动ping、未执行Prefer Direct、未改变Serve/ACL/DERP设置；不借探测把路径改变后当作原始连接状态。被动状态仅代表采样时最近活动路径，不能证明整段SSE都走同一路径；没有RTT样本，不提供延迟数字。

启动核对：用户授权在macOS Terminal分别启动Texa与Serve；Electron托管127.0.0.1:59999，沿用HTTPS443映射。Tailscale入口本机只读GET HTTP200。没有用本机访问代替手机端实际验收。此观察不改变审计报告中的真机学习/键盘/弱网闭环待验证结论。
