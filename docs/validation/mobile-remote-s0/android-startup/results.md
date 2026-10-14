# S0 Android Chrome 启动诊断与修复

2026-10-08。保持当前工作区已有修改，不改 Tailscale、代理、鉴权、数据库或 Runtime。

## 真机证据与当前结论

用户提供 Redmi Turbo 4 Pro / Chrome **154.0.8037.57** 诊断：

```text
build=2026-10-08T06:07:00.278Z
chrome=154
secure=true
localStorage=ok
sessionStorage=ok
stage=asset-load
error=unknown
asset=vendor-markdown-CYlHEDRF.css
```

已确认 Android 浏览器的 stylesheet 加载发生失败；Storage 正常，不能把此故障归因于 Storage 拒绝。Chrome154 高于 Vite8 默认 Chrome111 构建基线，没有降低目标或安装 polyfill。[Vite8 兼容说明](https://v8.vite.dev/guide/build)。

第二次用户真机报告：主 CSS `index-Dfy-zSwV.css` 失败，`phase=html`、`appMounted=false`、`probeStatus=200`、`probeType=text/css`、`probeError=timeout`。这确认手机已收到响应头，但10秒内未读完正文，尚未执行入口；故障在启动资源传输阶段，不能归因于Token、React状态或Storage。仍未确定底层网络/浏览器传输原因。

本机文件存在，28,835 字节。对**当前运行的**用户桌面 loopback 59999 和现有 HTTPS Serve 域名进行无 token 的只读资源检查，均返回 200、`text/css; charset=utf-8`、28,835 字节、无重定向。排除本次检查时的文件缺失/MIME错误；Mac 的请求成功不能代替 Android 网络响应。`asset-load` 本身不能提供 Android HTTP 状态或 Chrome 内部网络错误码，**尚未确认该设备 CSS 加载失败的底层原因，不能宣称白屏已解决**。

后续构建的页面会在首次资源失败时，从手机自动 fetch 同源的该静态资源：显示 `probeStatus`、`probeType`、`probeBytes` 或 `probeError`，以及 `phase` / `appMounted`。不携带 API token/cookie、不请求外部 origin、不上传诊断、不回显 raw error/message/stack/URL query/hash。

## 已确认并修复的代码缺陷

1. `frontend/index.html` 原本 root 为空、没有模块加载前的提示。现在提供独立于 React/CSS 的启动状态、超时、资源错误、未捕获异常/Promise拒绝提示，以及脱敏诊断。
2. `frontend/src/main.tsx` 原本先静态导入整个 App，模块求值或主题初始化失败时无法捕获。现在使用 caught dynamic import 启动 `bootstrap.tsx`；`StartupBoundary.tsx` 覆盖根级 React 渲染错误，挂载完成通知 HTML guard。
3. `theme.ts` 原本 default argument 中读取 localStorage；getter 的 SecurityError 发生在 try/catch 之前。bootstrap/client 与 SessionProvider 初始偏好读取也未保护。在原代码上通过抛错的 Storage getter **复现**了主题和 client 导入失败，然后修复并做回归。
4. `utils/browserStorage.ts` 保护 getter 与读写；主题读取回退默认值，主题应用不依赖持久化；`api/client.ts` token 在 Storage 拒绝时仅保留当前页面内存，仍加入鉴权 header，不关闭 token 校验。`ChatContext.tsx` 与主 `ChatPage.tsx` 初始偏好访问也保护。正常 SessionStorage 行为不变。
5. `backend/static_assets.py`、`backend/main.py`：仅 GET `/assets/*.js` 与 `*.css` 启用现有 Starlette gzip，范围请求、HEAD、页面、API 和 SSE 不变。原服务在 `Accept-Encoding:gzip` 下仍返回未压缩资源，已实际验证。这一缺口放大手机资源传输耗时；补丁降低传输体积，不冒充底层网络原因已定位。无新增依赖；已在原59999端口重启用户开发桌面，实际响应已启用gzip。
6. `vite.config.ts` 仅增加构建身份到 HTML；未修改 target、引入依赖或改变 RAG/业务状态机。
7. `desktop/main.cjs` / `runtime.cjs`：开发版原先仅凭 `/health` 就接管同端口旧后端，且就绪检查跳过实例身份。用户按固定端口重启后，日志确认接管旧实例，旧后端进程已孤立（PPID1），新桌面token与旧服务不匹配，因而无法读取本地配置。现在开发版也校验instance_id，显式匹配实例复用时还验证鉴权；不匹配则明确报端口占用，不接管或覆盖配置。显式SKIP_BACKEND模式保留。

Storage 防护修复的是可确定的代码问题，不作为本次 Redmi 故障根因。未知传输问题没有用猜测性的网络/代理变更处理。

## 验证

- 原 Storage getter 故障复现：1 项测试通过，确认旧代码确实抛错；日志 `storage-before.log`。
- 全前端测试：156 passed（含鉴权 bootstrap、SSE、Storage拒绝、资源诊断脱敏、资源 probe 和主题回归）。
- 后端静态 gzip / SPA / S0鉴权 / SSE合同回归：48 passed。实际隔离Electron gzip响应：主CSS 110060→19233字节、KaTeX CSS 28835→7954字节，解压内容逐字节匹配构建。
- TypeScript、Vite production build、相关文件 ESLint、git diff --check：通过。保留现有 chunk 大小 / mixed import 警告。
- 桌面 Node 回归：15 passed（含开发版实例错配拒绝回归）。
- 隔离 Electron：`/tmp/texa-android-startup-desktop` 独立数据目录，动态端口62056、loopback、服务 Ready，主脚本/新 bootstrap 及 CSS 200。未配置模型、未问答或修改用户学习数据。
- **Mac Chrome 实际首屏**：新建测试标签访问隔离 loopback62056，成功加载新版 React，显示原首次设置页；由于未提供 token，出现配置接口不可用提示符合 API401。没有以此宣称 Mac 远程鉴权或问答通过。
- **用户开发桌面恢复**：确认旧项目孤立后端后正常SIGTERM退出旧服务与桌面，再用原数据目录及59999端口启动。Ready；桌面实际 `/api/system/settings`、subjects、教材列表、会话列表均200，未重置配置。原服务CSS gzip已实际生效（KaTeX传输7954字节）。Tailscale配置未改；桌面保持运行。
- Android 真机结果来自用户提供的上述报告；未能直接控制手机或读取其 DevTools。尚未验收手机进入工作区、真实问答与引用。

## 最小后续诊断

当前开发版 `frontend/dist` 已更新，用户开发桌面已在原59999端口恢复且压缩已生效，无需再次重启或修改Serve。Redmi刷新原地址；若进入连接页，从当前桌面重新复制新的token。若仍失败，等待10秒，提交新 `build/phase/appMounted/probe*` 文本；最新诊断包含 `probeEncoding`，不要提供token。

- `probeStatus=404`：核对该手机看到的 HTML build 与实际 dist/Serve实例，确认是否混用了旧HTML和新资源；不得盲目覆盖索引或数据。
- `probeStatus=200, probeType=text/css, probeBytes=28835`：该手机 fetch 已成功，但原 stylesheet 加载失败；结合 `phase/appMounted` 判断是否仍有模块加载缺口，需要查看具体 stylesheet request 的浏览器错误或安全策略。
- `probeError=network-or-body-read` / `timeout`：是该设备请求或读取响应失败，不能解释成 API鉴权或 React错误。
- `phase=html`：入口模块尚未执行；`entry-loaded` 后才进入 App import；`theme-applied` 表示已到 React 渲染前；`appMounted=true` 表示 React 已提交首屏，仍不表示问答成功。

若仍无法确定，通过 Chrome官方 Android远程调试仅读取该资源请求的错误码/HTTP状态/响应MIME即可，不需提供 Token、请求头、HAR 或完整业务日志。系统调试授权由用户自行完成；本次未修改任何系统网络设置。
