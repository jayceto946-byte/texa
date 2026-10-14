# MacBook Neo ↔ Redmi 直连诊断 — 2026-10-14

用户要求核对为什么之前可以直连、现在为DERP；用户确认Redmi当前使用移动数据或其他Wi-Fi，与旧环境不能视为相同，未确认亮屏/锁屏。

## 实测

- 10:38–10:40（Asia/Shanghai），Mac Tailscale 1.104.1，Running，Health=[]；Mac/唯一Android peer在线，密钥未过期。
- Mac一次netcheck：UDP=true、IPv4=true、IPv6=true、MappingVariesByDestIP=false、CaptivePortal=false；UPnP/PMP/PCP=false。后二者不自动证明直连失败，不能凭无端口映射要求打开路由器设置。
- Mac系统防火墙disabled、block-all disabled、stealth off；系统代理字典为空。没有对第三方网络扩展/路由器防火墙做完整排除，因此不称“Mac绝无问题”。
- 10:39:56有界Tailscale ping（最多3次，timeout2s，总预算10s）：解析到2个成功回复，均DERP(lax)，1335ms和561ms。命令exit0不代表3次全部成功，不将未解析尝试记为丢包率。探测前peer闲置Active=false，不能仅据Relay判为当时活跃DERP；探测后Active=true、CurAddr空、PeerRelay空，仍DERP。
- 本轮没有观察到Direct；没有重启手机VPN、强制线路、持续ping、改变Serve/ACL或防火墙。

## 判断与边界

Mac具备一般UDP可达性、非目标相关NAT映射及IPv6连通条件。当前证据不支持“Mac完全封UDP/系统防火墙阻断”的解释。考虑Redmi网络发生变化，更可能是当前手机网络的NAT/UDP限制或切网后的端点发现状态；这是推断，不是手机硬件/系统责任结论。没有手机侧netcheck，也没有保持Mac不变只换Redmi网络的受控对照，暂不能定责。

最少对照：Redmi亮屏保持Tailscale前台，刷新Texa现有网页（不调用模型）；先保持当前网络做观测，再仅把手机切回此前可直连网络，重新观测。若同Mac、当前网络DERP而旧网络Direct，重点定位手机接入网络；若不换网络，仅重新建立手机VPN后Direct，更支持切网/发现状态而不是持续网络封锁。手机VPN重连会中断流，应在没有生成任务时由用户执行。

官方依据：[Connection types](https://tailscale.com/docs/reference/connection-types)、[Device connectivity](https://tailscale.com/docs/reference/device-connectivity)。直连依赖两端UDP路径及NAT组合；两端hard NAT难以直连，一侧健康不证明端到端路径健康。

脱敏原始结果：NETWORK-DIAGNOSIS-2026-10-14.json。未保存设备地址、节点身份密钥或管理token。
