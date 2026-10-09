# Mobile Remote S2 第一批

日期：2026-10-09（Asia/Shanghai）。范围：S2-00 / 01 / 02；测量证明有必要的 Markdown 复用。基线 `feature/mobile-remote@52cc1f5`，独立分支 `codex/mobile-s2-first-batch`。性能数值见 [performance.md](performance.md)，原始记录见 `baseline/results.json` 与 `final/results.json`。

## 分支与数据保护

- 开始时只有用户提供的 `Texa-Mobile-S2-Experience-Performance-Design.md` 未跟踪。本轮不提交该输入文件。
- 当前基线领先 `Texa_MacOS` 2 个提交、MacBook checkpoint 1 个提交、`codex/checkpoint-remediation` 15 个提交，三者均是当前 HEAD 祖先，没有反向独有提交。
- remediation worktree 在 `/Users/jichengqian/.codex/worktrees/ad0b/texa`；另两个 worktree 位于 `6c0d`、`7617`，均 detached `898bec3`。未切换、合并、清理或修改这些 worktree。没有 fetch、push，也未核对 Windows 未推送成果。
- 未修改 Runtime 所有权、Submission 表、Policy/Agent、通信协议、Tailscale/DERP/Serve 配置或用户学习库；没有真实模型调用。

## 实际改动

1. `features/books` 共享目录成功快照（内存，30 秒）、single-flight、失效代次；目录变更与凭证更换/401 清除缓存，拒绝迟到的旧结果；失败不缓存。聊天、侧栏、学习、习题、错题、目标页复用；带 `include_archived=true` 的管理查询仍保持独立。移除侧栏无过期/数据源身份的持久目录缓存。后台目录刷新不改变现有会话范围。
2. `features/chat/useReadingScroll` 承担贴底跟随、用户发送、会话切换、前插历史和来源定位。上翻不跟随 delta，可显式回最新回答。沿用原 Notes/source locator 和来源面板，关闭面板保持阅读位置。
3. 文本/图片/Figure 与恢复路径使用共享 `streamPresentation`；错误正文与已生成文本分离。Markdown/公式继续显示部分正文，明确未完成。显式空replacement不复活已撤回的旧正文。没有自动重发、自动恢复或将 partial 标记为最终结果。没有新增 partial 的耐久存储承诺。
4. 移动输入 16px、主要输入工具和发送按钮 44×44；恢复可见范围选择，修正窄屏头部的固定 flex-basis，避免第二行覆盖正文；桌面控件尺寸不变。
5. 热切换的响应后显示路径确认较重，复用未变化的 Markdown/KaTeX。比较内容、概念、回调、媒体策略和 citation ID 集合；回调随教材变化更新，不忽略交互闭包。没有虚拟化、渲染 worker 或全文重构。
6. PDF 仍按已有鉴权 Blob 路径显式全量读取，按钮和等待文字如实说明“完整 PDF”。没有将 `#page` 冒称按页传输，没有自动预取全书。
7. `?texa_perf=1` 启用可选性能导出按钮；默认关闭、独立 lazy 模块。导出耗时、尺寸、固定资源类别、build、viewport、协议、paint/LCP/longtask；不导出 URL/query、token/header、用户/教材/任务 ID、正文、照片或 prompt。最多 512 条资源和 256 条 observer 记录。关闭查询参数即撤销诊断入口。

Harmony：基线已经在 `main.tsx`、远程 CSS 和 `useLearningNoteFont` 使用系统字体；浏览器瀑布证实 Harmony **0 请求**。本轮没有再实现或认领字体策略。既有 gzip、lazy loading、图片压缩、轻预览及 SSE 合并均不算本轮成果。

## 可重复测量

使用本地安装的 Chrome、项目 Vite、已有 Playwright；不安装依赖。夹具 HTTPS 绑定 `127.0.0.1:18429`，合成 API `18029`，可选 Electron `18439`。Chrome 通过临时 resolver 将 `texa.test` 指向 loopback。证书只用于隔离测试。

```sh
mkdir -p /private/tmp/texa-s2
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /private/tmp/texa-s2/key.pem -out /private/tmp/texa-s2/cert.pem \
  -subj /CN=texa.test -days 1
# 在 frontend 下，用已有 Node 执行：
node node_modules/vite/bin/vite.js build --outDir /private/tmp/texa-s2-build
# 回到仓库根目录；NODE_PATH 指向已有 Playwright 包目录：
TEXA_BENCH_BROWSER='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
node scripts/mobile-s2-performance.mjs /private/tmp/texa-s2-build \
  /private/tmp/texa-s2-run/results.json /private/tmp/texa-s2
```

5 次新浏览器上下文冷进入，20 次同页最近会话热切换；固定 400ms latency、5Mbps 下行、1Mbps 上行；100 条合成消息（50 轮，含中文/公式/表格/引用）。夹具扩展返回窗口到100条，只用于已有历史展开后的渲染压力，不作为真实分页 API 行为或普通40消息首屏SLO。夹具故意保持 gzip 和不可变静态缓存与基线一致。固定初始无匹配教材的范围，再读取同一合成 Session；避免把首次自动选书与自动化点击的竞态混入结果。冷指标必须等100个 Markdown 正文实际渲染及两次 rAF，不能以消息壳/懒加载占位为可读。热指标从 DOM 真实 click 到正文挂载并经过两次 rAF；原始 `bodyToReadableMs` 包含 React、布局、绘制以及浏览器自动化观测延迟，不冒称纯 React CPU 时间。

`Server-Timing` 是该合成服务处理到响应头的时间。Resource Timing 的 TTFB/body 字段分别保留；Chrome CDP 可能把注入的 400ms 等待计在 body 段，不能把它全部叫字节传输，也不能从两者相减得到精确 DERP 网络耗时。构建/localhost 测量与真实手机/模型时间分别报告。

## S1 验收补录

本轮向用户询问原 Tailscale 入口、图片预览、错题正式保存、笔记正式保存是否成功，用户回复 **“都能”**。据此补录为用户真机确认可用，不重复开发这些闭环。此前源码、桩模型与服务端真实资产核对保留在 [S1 results](../mobile-remote-s1/results.md)。本轮重跑对应后端合同。

| 七路径 | 本轮证据 | 仍缺什么 |
|---|---|---|
| 文字问答→引用→错题 | 浏览器假 SSE / 公式 / 来源返回；用户确认错题保存；后端来源合同 | 本轮真机逐步耗时与相同 mistake_id |
| 拍照→识图→回答→刷新 | S1 原有压缩/图片资产/完整答案合同重跑；用户确认预览可用 | 本轮真实 DERP 上传、首接受/识图/首正文分段耗时 |
| Session→笔记→编辑→正式保存 | 原有 Notes 合同重跑；用户确认正式保存 | 本轮手机→桌面相同 note_id/revision 对照 |
| 错题/Notes→原消息→原资产 | 沿用已有 locator；原页面返回合同未重做 | 真机往返操作数、键盘/返回键 |
| 长 Session 阅读 | 固定 100 消息、五冷/二十热、流式上翻/错误 | 真实 VPN 抖动、100 轮与手机内存 |
| 教材片段/Figure→带来源提问 | 图/片段优先、PDF 全量提示；共享 presentation 覆盖 Figure | 真机 PDF 频率与文件字节、单页方案另评估 |
| 离开→继续 | 保留原恢复入口，不新增自动对账 | S2-03/04 的未知 task、刷新/断线权威恢复，本轮不实施 |

不能将用户的简短确认扩展为本轮获取了截图、ID、逐步操作数或真实性能 trace。

## 真机 DERP 补测

最终构建上线后，在原 HTTPS 地址加 `?texa_perf=1`，依次进入学习、切换已有会话、打开已有图片预览、打开来源（原 PDF 显式触发），点击“导出性能记录”。无须重新拍照、运行模型或提交错题/笔记。冷样本需清当前站点缓存但保留/重新输入本人 token；热样本保持同页。配合当时活跃 Tailscale ping 路径标记 DERP/direct；手机导出的 JSON 无私密 HAR。本轮没有取得真实手机导出，**DERP 前后耗时与吞吐仍待测**，不能以 Mac 访问自身 Serve 地址替代。

已更新本工作区 `frontend/dist`，保持既有旧 hash 文件。只读核对原端口59999返回 connection refused，未启动/重配真实桌面，不声称实际 HTTPS 入口已使用新构建。下一次正常桌面启动可读取当前静态构建。

## 范围外证据与最小复现

- PDF：查看 `FigurePageInspector` 或回答 Figure 来源→显式打开 PDF→`getAuthenticatedBlob` 完整 `arrayBuffer`→iframe `#page`。全量传输是已确认合同事实；本轮未读取用户 PDF，也没有真机下载字节/高频证据，暂不增加单页服务或携 token 的 URL。
- Session：切不同会话仍读分页最新页，停止/恢复/管理状态依赖原权威 API。夹具下正文仅约 3.8KB gzip，响应后显示路径明显；本轮先减少重渲染，没有增加 stale task 操作风险的快照缓存。未来 LRU 应单独满足 fresh task 与管理 revision 门槛。
- 已接受 task 前断网、final 后断网、锁屏和刷新：沿用现有连接所有权与 Session SQLite；本轮只修复前台已收到部分正文被错误覆盖的呈现问题。不添加 Submission 映射或后台所有权变更。
- 初次测量发现自动选书和历史点击的竞态会改变请求路径；既有 S1 取消迟到范围切换的守卫保留。初次试跑数据单列，不与校准后的同口径数据混合。

回滚：目录缓存、presentation/scroll、窄屏 CSS、Markdown memo、可选诊断均可独立撤销；无数据库迁移或用户数据回滚。
