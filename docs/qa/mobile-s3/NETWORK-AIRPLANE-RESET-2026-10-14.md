# Redmi 飞行模式重置后采样

2026-10-14 10:48:15–10:48:19（Asia/Shanghai）。用户报告移动数据下开启一段时间飞行模式后恢复网络、打开Tailscale并刷新Texa网页。

先被动观察：Android在线且Active=true、无CurAddr/PeerRelay，Relay=nue，判定当前DERP。随后最多3次、单次2秒有界ping：DERP(nue) 449ms、404ms、429ms；探测后仍DERP(nue)，无Direct证据。

之前10:39样本为DERP(lax) 1335ms、561ms；本次中继区域变化且三次RTT低于此前两个样本，但不能据小样本保证稳态改善。重置没有恢复直连，因此“仅刚退出旧VPN的短暂过渡”不足以解释当前状态；仍需手机侧网络/NAT诊断或保持Mac不变换手机网络对照，不能据此确定设备责任或断言运营商封UDP。

本轮未更改Serve、防火墙、VPN或Tailscale配置。探测可能促成打洞，但没有升级Direct。脱敏结果见同名JSON。
