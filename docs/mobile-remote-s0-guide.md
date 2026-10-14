# Mobile Remote S0 手机连接指南

适用：本人手机访问正在运行的 Texa Desktop，验证已有教材文字问答。手机复用桌面 FastAPI、React、Session 和配置；不要再启动第二个后端。本阶段管理 token 权限完整，只用于临时验证，不是正式远程授权方案。

## 连接

1. 桌面与手机自行从 [Tailscale 官方下载页](https://tailscale.com/download) 安装并登录同一 tailnet，手机开启 Tailscale VPN。若 CLI 不在 PATH，按对应发行版官方说明使用完整路径。这里没有自动安装、登录或提权。
2. 在 Tailscale 管理后台检查有效 Grants/ACL：仅授权本人手机的 Tailscale 地址访问桌面节点 TCP 443。不能保留覆盖该目标的 `* → *` 或其他宽泛允许规则再指望一条窄规则限制访问；规则允许范围会叠加。不要开启 Funnel。用一个已加入 tailnet、但未授权的测试设备验证拒绝，再用未加入 tailnet 的设备验证不可达。
3. 构建源码版前端（`cd frontend && npm run build`），启动桌面（`cd desktop && npm run dev`）；打包版需重新打包安装，现有旧安装包不会自动获得本次代码。先在桌面完成回答模型配置、确认教材可检索。
4. 桌面“设置 → 关于与更新 → 手机远程连接 · S0”查看**实际端口**。先运行 `tailscale serve status` 和 `tailscale funnel status`。443 若已有映射或任何 Funnel 暴露，先人工核查与处理，不覆盖其他服务，不直接执行全局 reset。
5. 执行界面给出的命令，例如下面的 `PORT` 必须替换成当前端口：

   ```sh
   tailscale serve --bg --https=443 http://127.0.0.1:PORT
   tailscale serve status
   ```

   首次启用 HTTPS 可能需要按 Tailscale 提示在账户后台授权。确认输出为 tailnet 内 HTTPS 地址、目标为当前 `127.0.0.1:PORT`。Serve 访问仍受 tailnet 访问控制。[官方 Serve 说明](https://tailscale.com/docs/reference/tailscale-cli/serve)、[访问控制说明](https://tailscale.com/docs/features/tailscale-serve)。
6. 手机浏览器打开 Serve 给出的 `https://…ts.net/`。在桌面点击“复制临时管理令牌”，通过本人受控方式将其粘贴到手机连接页并连接。不要放进命令行、查询参数、消息、截图或日志；不要复制 Electron 含 `api_base=127.0.0.1` 的启动链接。使用后清空剪贴板。连接页只读取桌面就绪状态，不要求再次填写模型密钥。
7. 手机选择已有 Session、确认其历史，再选择已有教材和学科，用教材中可人工核对的文字问题发问。观察正文逐步出现、引用可打开，记录 task/turn、验证状态和耗时。刷新 Session 检查持久化正文与来源；桌面刷新查看同一会话。HTTP 200 和 `completed` 不代表答案事实正确，仍需人工核对。

## 启动故障诊断

- 手机出现“Texa 启动失败”时，等待约10秒，只记录页面中的 `build / phase / appMounted / asset / probe*`。这些字段不包含token；无需提供请求头、HAR或完整启动URL。
- `phase=html` 且资源探测200后超时，表示启动资源正文未读完，尚未到React或Token验证。不能以 `/health` 成功认定页面加载成功。
- 桌面重启后需重新复制临时token。若报告端口被另一后端实例占用，先完整退出旧Texa和自己启动的本地后端；不要启动第二个服务、重置本地配置或覆盖数据。开发版已校验实例身份，拒绝盲目接管旧服务。

## 故障验证与收尾

- **错误 token**：新建隐私窗口，输入错误值；受保护 API 应返回 401，不能进入学习页面。有效 token 被桌面重启失效后，下一次受保护请求应回到连接入口。
- **断网**：生成中关闭手机网络/Tailscale；应显示中断/失败，不能显示成功。网络恢复后重新打开原 Session，读取后端任务状态；只有既有界面确认中断时才使用恢复入口。S0 不自动重发、不保证锁屏后台持续生成，也没有新增逐 token 回放。
- **桌面退出/睡眠**：服务应不可达，问答失败。`--bg` 的 Serve 配置会保留；它不让 Texa 后端在退出后继续运行。
- **重启/恢复后端**：点击“刷新实际端口”，核对 Serve 映射和当前端口；必要时只更新本服务对应映射。重新复制 token。不要把旧端口映射当成当前实例；端口可能被其他进程复用。
- **结束 S0**：若 443 映射由本次独占创建，执行 `tailscale serve --https=443 off`，然后 `tailscale serve status` 核查。关闭手机标签页，并退出/重启桌面使随机管理 token 失效。若人为配置了固定 `KAOYAN_API_TOKEN`，重启不会撤销它，需在桌面移除或更换该固定值。

验收至少覆盖蜂窝、校园 Wi-Fi、切网、桌面退出/重启、授权和未授权设备。无真实设备/网络时只能报告代码与本机验证。S0 未开发拍照、错题、笔记、PWA 或新移动布局。


## 历史与窄屏复测

刷新原Serve地址后，展开侧栏确认功能区和历史区顺序排列；切换另一会话再展开侧栏，列表不应闪空或重读。重复点当前会话应直接回到已有内容；其他会话首次读取仍有网络往返，不能用本机耗时作为手机承诺。若仍明显缓慢，只报告操作与耗时；开发者可结合脱敏`session-detail`服务耗时与字节数分析，不发送Token或含鉴权日志。此修复复用现有页面，不代表完成全站移动布局或原生壳。验证记录见[历史与窄屏结果](validation/mobile-remote-s0/history-layout/results.md)。
