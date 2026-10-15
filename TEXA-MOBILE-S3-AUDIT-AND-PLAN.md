# Texa Mobile S3 — Audit and Plan

当前实施入口：[综合实施方案](TEXA-MOBILE-S3-IMPLEMENTATION-PLAN.md)。该方案已合并Redmi验收与番茄任务需求；此文保留历史审计事实和证据，旧批次取舍以综合方案为准。

2026-10-14（Asia/Shanghai）。负责人：Sol；产品设计审查：指定 gpt-6-astra agent，一次调用。

**本轮交付审计与待批准方案，没有实施 S3 产品改造。当前不具备宣布 Mobile V1.0 RC 的证据。** 现有阅读、笔记、错题与受控执行基础应保留；主要收敛点是教材往返、窄屏输入与编辑操作、可信恢复。没有本轮已证实的数据损坏或重复工具执行 P0；未验证的断网/双端场景也不能记为通过。

## 2026-10-14 Redmi 实机反馈修订（优先于下文旧方案取舍）

用户提供5张实机截图，确认顶栏错位、多层重复三点、阅读画布整体横拖、教材主体滑动困难、Goal409与侧栏优先级问题。新增M3-17–22均为P1；原M3-09提升P1，原M3-11按新反馈提升P1。旧浏览器样例“无整体溢出”仅限其样例，不代表真实长公式通过。

目标失败已只读定位：对应旧run paused/goal_changed，冻结goal_contract缺失，继续执行触发409恢复栅栏；前端按钮和错误文案需适配旧合同，不能笼统归咎模型/网络。

用户明确新增“目标拆解+番茄任务+聊天可展开计时控件”方向，**替换旧timer不纳入结论**。任务内容/时长可编辑，开始暂停/切换/用户确认完成，计时与Runtime状态区分；先补交互与持久化合同评审，数据迁移须按AGENTS取得同意，尚未实施。新增B-T设计阶段，原总工作量估算须重估。此前Astra审查保存原文作为历史判断，不伪称它审过本次新需求。

详见 [真机验收与方案修订](docs/qa/mobile-s3/REAL-DEVICE-REVIEW-AND-S3-REVISION.md)。这部分是真实Android图片/用户操作证据，但键盘、平板、完整弱网与新计时功能仍未验证。

## 1. 基线与成果归属

- 指定稳定基线及实际 `master`、fetch 后 `origin/master`：`f999e7282b59780f295eb7b5b54fa76913f9eb66`。
- 原工作区 `/Users/jichengqian/Documents/ChatGPT/texa`：开始/审计结束无未提交修改，保持 master。
- 独立管理 worktree：`/Users/jichengqian/.codex/worktrees/mobile-s3/texa`；新建用户指定 `feature/mobile-s3`，建立前同名不存在，起点为上述 master。
- origin 为 `jayceto946-byte/texa`。SSH fetch 在获准写 Git 元数据后仍被网络关闭；以进程级 HTTPS URL rewrite fetch 成功，未保存配置、未更换远端。没有使用 reset、覆盖其他分支或自动合并。
- `6a5f50c` 整合 Runtime/DeepSeek；`33d6db0` native DeepSeek、`e843b8b` 回答布局与进度、`f999e72` 回归记录均在 master。未更改默认模型或生产 Runtime。

| 分支 | master 独有 / 该分支独有提交数 | 结论 |
|---|---:|---|
| Texa_MacOS（S0） | 39 / 0 | 已包含；S0 `9b04c87` |
| checkpoint/macbook-20261009（S1） | 38 / 0 | 已包含；`4e8c3d4` |
| feature/mobile-remote | 37 / 0 | 已包含；`52cc1f5` |
| codex/mobile-s2-first-batch | 36 / 0 | 已包含；`dd91fee` |
| codex/mobile-s2-a2 | 25 / 0 | 本地 `cde805e` 全部包含；远端旧 tip `c53e78b` 也包含 |
| codex/checkpoint-remediation | 52 / 0 | 已包含 |
| codex/cross-module-remediation | 2 / 0 | 已包含 |
| codex/agent-early-output | 8 / 3 | 另一专项的时序/诊断工作，不是移动遗漏，不自动合并 |
| codex/agent-model-latency | 8 / 1 | 另一专项的审计文档，不自动合并 |

全部已登记 worktree 核对：6c0d、7617 detached 均为旧 `898bec3`；ad0b、agent-early-output、agent-model-latency 及原工作区干净。7617 中 `patch_notes.md` 与未跟踪 `docs/validation` 为 9 月 Checkpoint 验收记录，未改动、未清理。不能观察另一台电脑未推送的提交/文件；此次“无遗漏”仅限 fetch 可见 refs 与本机 worktree。

## 2. 证据口径与 S0–S2 实际情况

- **R：本轮运行确认**，注明合成 HTTP、真实隔离 API/SQLite 或原生 Electron；均不等同 Android。
- **C：本轮代码确认**，可确认实现边界，不等同使用验收。
- **H：历史报告声称/历史验收**，未重测的真机结果只记 H。
- **U：尚未验证**，包括本轮没有真实 Android、真实 DERP、付费模型、生产索引与扫描原书校验。
- **D：拟实施设计**，下文批次、规则与退出标准均不是已完成能力。

已读取 V0 Audit、S2 Experience/Performance Design、S0 guide/results、S1 results、S2/S2-A2 README/performance、Mobile Network S2、Mobile visual audit、QA Final/Cross-module final handoff。旧报告的“设置双栏”“原公式字符串”“错误伪空状态”“流式强制到底”已经有修复，不重复开发。

| 阶段 | 当前代码事实（C） | 本轮确认（R）与限制 |
|---|---|---|
| S0 接入 | 同源 API、remote sessionStorage 临时 token、401 失效、SSE offline 错误；Electron 托管单后端 | S0 鉴权测试通过；未重配 Serve、未登录手机、未读取 token |
| S1 图片与资产 | 图像压缩/完整画面、上传进度、预览、错题/笔记来源继承 | S1 合同通过；历史用户“都能”仅 H；相机、软键盘、图片入库本轮 U |
| S2 阅读与资源 | `useReadingScroll` 64px follow 阈值、回最新；lazy routes；共享教材列表30秒 TTL/single-flight/失效；chapter-count 后端缓存 | 阅读上翻与流终态截图；readCache 等前端测试通过。没有本轮真实网络性能改善比例 |
| S2-A2 历史 | 当前会话有消息/生成中可跳过重读，刷新仅存 ID 时仍读取权威消息 | C：修复保留；同会话短路会阻止用“再点当前会话”进行跨端刷新，需对账入口 |
| S2 网络诊断 | 15秒缓存/单次探测预算/60秒冷却，Auto/Prefer Direct，foreground 触发只做诊断 | Python/前端相关合同通过；历史 DERP→Direct 只记 H，不保证当前路径或锁屏保持 |
| 后续共享修复 | SQL task、ExecutionEvent、run fence、来源定位、笔记 CAS/回执、设置手机单列 | 本轮测试与截图确认部分；完整双端、首次 ack 丢失、停止失败组合 U |

## 3. 功能矩阵

状态枚举：IMPLEMENTED、PARTIAL、BROKEN、NOT_IMPLEMENTED、OUT_OF_SCOPE。IMPLEMENTED 只用于所列窄合同被运行验证的项；其余尽管有代码仍保守记 PARTIAL。没有将“能打开”当成完整通过。

| 功能 | 状态 | 证据 / 实际边界 | 问题性质 |
|---|---|---|---|
| Home 快速开始/空状态 | PARTIAL | C/R：主聊天是首页；空态“从一个问题开始”可输入，非独立 Home | 学习入口/信息架构 |
| 当前教材与最近 Session | PARTIAL | C/R：范围选择器、抽屉历史可达；没有就地继续章节入口 | 交互发现成本 |
| 教材列表与切换 | PARTIAL | C/R：教材列表、状态、范围动作存在；本轮未写生产教材切换 | 管理与学习优先级 |
| 章节浏览与定位 | PARTIAL | C：现有 `/books/{book}/chapters` 与 highlights；R：重点页目录；教材列表没有明确章节学习入口 | 缺少连贯路径 |
| 教材正文/原页阅读 | PARTIAL | C：Figure/PDF、已生成重点；R：重点页；不等于完整教材阅读器，真实大 PDF 未测 | 资源/API与入口 |
| 教材→问答→原位置 | NOT_IMPLEMENTED | C：HighlightPage 无直接本章提问/上下文返回；没有统一往返书签合同 | 功能缺口 |
| 章节范围可信展示 | PARTIAL | C：Chat DTO 有 target_chapters；前端主 send 未提供章节级连续性合同 | 范围与界面合同 |
| 教材长公式/表格/图片 | PARTIAL | R：合成公式与表格；C：鉴权图片；U：矩阵末端、原图、PDF真机 | 阅读可访问性 |
| 新建/历史 Session | PARTIAL | C/R：新会话、分页历史、选择入口；U：双端持续对账 | 状态/可靠性 |
| 消息阅读/上翻 | IMPLEMENTED | R：390 touch 合成长文，上翻后终态保持前文并有回最新；C：独立 follow policy | 保留 |
| Streaming/工具展示 | PARTIAL | R：真实 React 消费合成 canonical SSE、工具进度展开、正文/终态；不证明真实计算/模型执行 | 需真实链路验收 |
| 阶段与最终正文 | PARTIAL | C/R：ExecutionEvent 聚合、后置终态；203前端测试；U：真机断流组合 | 保留合同 |
| 停止生成 | PARTIAL | C：先 abort，再按 task/run 中断，失败明确未确认；R：确认中断→同task恢复→终态→仅一个用户问题通过；失败组合U | 真机/失败组合 U |
| 失败重试/恢复 Session | PARTIAL | C：没有自动重发；原任务显式 resume，服务端确认门槛；U：首次 ack 前丢失 | 可靠性缺口 |
| 输入框/键盘 | PARTIAL | R：390→480高度模拟仍有输入区；360触控发送换行；真实键盘 U | 交互 P1 |
| 笔记列表/筛选/阅读 | IMPLEMENTED | R：夹具筛选、阅读、503→重新读取成功；阅读不要求模型在线 | 保留 |
| 笔记编辑/正式保存 | PARTIAL | C：autosave/CAS/immutable revisions；R：编辑视图；R：冻结来源→生成失败→手动编辑→跨页autosave→明确发布→刷新revision1通过；生成成功分支本轮U | 编辑顶栏/触控 |
| Session↔笔记来源 | PARTIAL | C：冻结来源、live_locator、note_path 白名单/消息定位；本轮夹具ID非正式来源契约 | 返回路径 U |
| 错题列表/筛选/详情 | PARTIAL | R：列表/分类/详情显示；真实创建保存单项通过；筛选组合及来源跳转 U | 触控/内容重复 |
| 手动错题保存与恢复 | IMPLEMENTED | R：隔离真实 API：草稿保存→刷新→恢复→正式保存→GET相同ID | 已通过窄合同 |
| 错题复习 | IMPLEMENTED | R：草稿刷新恢复、反馈→自评→完成→刷新；不代表SM-2长期效果 | 已通过窄合同 |
| 手动习题录入 | IMPLEMENTED | R：必填验证→保存→刷新确认存在 | 已通过窄合同 |
| 模型选择/连接状态 | PARTIAL | C/R：单列设置、模式/模型字段；保存真实profile/真实provider连接 U，不变默认 | 配置对象状态 U |
| 设置导航/字段保留 | IMPLEMENTED | R：返回设置焦点、未保存解析字段往返保留、关闭；Electron回归 | 保留 |
| 主机离线/移动连接 | PARTIAL | C：RemoteConnectionGate/401/SSE中断提示/诊断；未注入真实主机睡眠 | 恢复入口 P1 |
| 独立手机 Agent/PWA/离线后台生成 | OUT_OF_SCOPE | 未开发；不作为 S3 缺失 | 不扩范围 |

## 4. 实际截图与交互审计

构建源为原干净 master，与独立 S3 worktree 相同。输出 `/tmp/texa-mobile-s3-dist`，没有覆盖正在运行的 `frontend/dist`。npm 不在 PATH，使用已安装 bundled Node 执行现有 tsc/Vite，没有安装依赖。Vite 大 chunk 警告保留。

- 复用 `scripts/qa-pages.mjs`：1280×820、1024×768、760×820、390×844，19 routes，119检查；没有 fallback FAIL、无未处理fixture端点。11条console503为有意错误注入，不能称零console错误。笔记/复习503→重试成功，设置往返/字段/焦点通过。
- 补充脚本复用同一夹具服务/路由；360/390/430×844 touch/isMobile，58图/29几何记录。局部目录、笔记底部、抽屉、长文、工具摘要/展开、生成/终态；不是 Android。
- Sol 实际用图片工具查看44张常规手机图（8组）、58张focused（10组）及桌面学习/教材两图；另查看真实API恢复测试失败图。完整清单与哈希见 [Screenshot Inventory](docs/qa/mobile-s3/SCREENSHOT-INVENTORY.md)。Astra 读取8张原尺寸对照组，不以文字代替图片。
- focused 的430聊天是未载入历史的空态，模型设置是骨架加载，均保留并标非目标场景，不能证明430历史载入故障/模型详情通过。模型详情以常规 `390-settings-models.png` 为准；loading图多为路由级骨架，不夸大成全部API局部加载验收。
- 没有完整 Android 相机、原生键盘、Safe Area、旋转、真实图片/超大矩阵、真实索引/PDF验收。高度模拟不能签收键盘。

### 4.1 Design Inventory

| 角色 | 当前系统 / 渲染 | 分类及 S3 方向（D） |
|---|---|---|
| Typography | 16px reading、24px文档标题、13px界面、12/11px元信息，reading leading1.9；正文与标题分工清楚 | A保留。手机正文16px；新规则先比较真机，不全局改字体；标题/元信息按上下文精简 |
| Spacing | 阅读40px/管理32px基准，手机约16–22px gutter | A保留对齐轴；C：顶栏/分类占高要按任务重排 |
| Color/Surface | theme aliases、暖中性阅读面、蓝操作；仍有white/red局部样式 | A保留身份；B：状态风格统一、不只用色 |
| Border/Radius | register分隔线，小控件4/5px/menu6px；文章/目录独立框 | B/P2：章节去重复框，保持阅读文章流 |
| Navigation | 手机抽屉业务+历史；无底部栏；设置单列目录→详情→返回 | A保留设置；D：补上下文返回，抽屉数量降P2，不新增底部栏 |
| Buttons | shared control28px、composer44px；测量编辑保存62×28、排序删除28×28、侧栏30×30 | C/P1：手机实际命中区≥44×44，不扩大桌面控件 |
| Inputs | 36px管理字段，聊天focus16px；360发送另起行 | C/P1：附件归并、固定发送/停止位置，键盘验收 |
| Empty | 笔记说明→回学习；错题说明→练习/录入 | A保留；结合未成功读取抑制空态 |
| Loading | shared skeleton、长等待20秒刷新提示 | A保留；场景身份/局部状态补验 |
| Error | note左色条、mistake红框、review文字error、goal状态页 | B：统一语义/层级，保留部分成功和重试 |
| Cards/Lists | chat/note文章、错题register；editor块卡与highlight双框 | A保留文章；B/C：控制编辑信息，不全站重画 |

### 4.2 具体问题（Sol + Astra 整合）

R/C/U 标记与根因假设分开；截图可见现象不自动证明后端故障。详细 Issue List 位于 [ISSUE-LIST.md](docs/qa/mobile-s3/ISSUE-LIST.md)。

| ID | 优先级 / 性质 | 观察、影响、证据 | 修改方向 |
|---|---|---|---|
| M3-01 | P1 功能/交互 | 教材管理动作领先；重点页无本章提问/返回，无法连续完成规定闭环。R/C：books/highlights | 复用章节/PDF/Figure/重点能力补学习入口与往返定位，不新造阅读器 |
| M3-02 | P1 交互 | touch360六个输入工具，拍照/图片相似图标，发送换到左侧第二行。R | 归并附件菜单；主发送/停止固定右侧 |
| M3-03 | P1 交互/视觉 | 笔记编辑标题截断，草稿状态/预览/保存挤换行。R | 顶栏返回+标题+正式保存；草稿独立状态行，预览次级 |
| M3-04 | P1 触控 | 保存/重做/复习等28px，块排序删除28×28。R DOM测量 | 手机关键区44px、独立操作间距≥8px；逐控件验证 |
| M3-05 | P1 Reliability | foreground只触发网络诊断；当前Session有消息时点同项不读取，跨端更新可滞留。C，跨端实际 U | 回前台/在线读一次SQL当前会话/task，显式重新读取，旧响应generation fence，不自动重发 |
| M3-06 | P1 验收风险 | 首task ack前断流不能可靠通过客户端已有task ID对账；server request_id作为request_key。C/U | 先故障注入定位；保存客户端待确认身份，复用已有查询/回执。若缺API合同，独立小提案，不直接重构Runtime |
| M3-07 | P1 验收/状态 | 停止先abort，interrupt失败仅文字要求重开；离线/已取消/可恢复需7态组合测试。C/U | 显式未确认+只读对账入口；SQL确认后恢复，检测迟到run |
| M3-08 | P1 工程 | 全量lint在ChatPage242 render写ref报react-hooks/refs。R | 后续最小修复并验证book switch stale response，不在本轮改业务 |
| M3-09 | P2，不可读升P1 | 窄屏长等式右端出视野；有overflow-x源码，未证明末端触摸可达。R/C/U | 容器局部横滑/提示/矩阵+表格末端实测，不整体缩小字号 |
| M3-10 | P2 视觉/IA | 章节目录大框先于书/章身份，正文又框；打印是突出主动作。R | 身份→折叠目录→文章，打印更多菜单 |
| M3-11 | P2 导航 | 抽屉7域+历史入口可扫描，但局部返回弱。R | 先修上下文返回；不因数量新增底部栏 |
| M3-12 | P2 错题 | 顶部摘要题干与正文重复，首屏多读同题。R | 顶部保留来源/定位，完整题干只作为正文主内容 |
| M3-13 | P2/待验证 元数据 | 重点页直接显示bookName和ISO生成时间，fixture是qa-book。C/R | 核对真实数据，再显示书名/本地日期，不把fixture ID当线上bug |
| M3-14 | P2 资1源 | 鉴权PDF先完整blob，重开不共享有界缓存。C，实际网络代价U | S3先保留片段/显式原页加载；先测体积，再决定局部缓存，不新增同步协议 |
| M3-15 | P1 真机验收门槛 | Android键盘、安全区、锁屏/切网/主机离线/双端未验证。U | 批次4人工验收，不用390px缩屏替代 |

新增 R/P2 M3-16：确认中断截图把内部checkpoint `user_stopped` 暴露给普通学生；后续只映射显示文案，诊断保留原code，不改任务状态。

## 5. Reliability 边界

SQL Runtime task/run/ExecutionEvent 为执行权威；ChatContext 是显示投影，不新建 Session 存储。`useChat` request sequence、lifecycle run/seq rejection、中断POST run_id、最终SQL projection 保留。不要把局部“停止”显示当后端已取消；不要在未确认时开启 resume。

`api/client.ts` POST fetch SSE 不自动重连/replay；断网给出未完成提示；terminal缺失报错。`networkDiagnostics.ts` online/pageshow/visibilitychange只处理链路诊断，不能当Session恢复。`PersistentRouteOutlet` 保留访问页及effects，notes共用槽；列表/详情大量缓存路径的内存上界是P2测量项，禁止先改保活把流中断。

教材缓存为非权威展示快照；Session/task/receipt不可用缓存宣布完成。不同设备的会话mutation事件不会自动跨浏览器传播；需读取已有API。断开后读conversation终态正文与task，不把content-free telemetry当token回放。

可靠性场景矩阵见 [Acceptance Matrix](docs/qa/mobile-s3/ACCEPTANCE-MATRIX.md)：高RTT、断SSE、首ack丢失、停止失败、页面切换/后台、快速换会话、双端、写回执丢失。发现风险不等于已复现事故。Tailscale不保证Direct；本轮不改Serve/ACL/DERP，不要求中继达到Direct速度。

## 6. Astra 独立审查与采纳

完整报告：[ASTRA-REVIEW.md](docs/qa/mobile-s3/ASTRA-REVIEW.md)，8组原尺寸材料：[review](docs/qa/mobile-s3/review/)。已直接看图，非文字转述；无重复调用。

采纳：保留文章流/来源检查/错题先作答/设置单列；P1集中教材往返、输入栏、笔记顶栏、实际触控区。Astra把抽屉七域从Sol候选P1下调P2，明确不新增底部导航；章节双框、日期元信息P2顺带处理。公式末端先实测，不可访问才升P1。可靠性不能由截图宣布事故或通过。行高等规则是候选，先在真机与既有阅读身份对照。

## 7. 当前实施批次（统一入口，尚未实施）

以 [TEXA-MOBILE-S3-IMPLEMENTATION-PLAN.md](TEXA-MOBILE-S3-IMPLEMENTATION-PLAN.md) 第6节为准。已替换原四批及B-T追加方案：B1真机阻断/基础布局 → B2核心学习闭环 → B3学习任务与番茄（先数据合同评审） → B4可靠性 → B5真机/RC。

总条件性参考17–27工程日，包含timer合同核对及条件性实现，不含设备等待；原11–17日不再作为当前范围估算。B3数据库迁移必须另提供具体方案并获同意；当前没有执行迁移或产品开发。

## 8. 测试计划与当前结果

| 检查 | 本轮结果 | 不能替代 |
|---|---|---|
| Python3.10.21 venv310 6相关文件 | 92 passed，6既有warnings | 真机/生产索引/模型 |
| frontend全部 | 45文件203 tests passed | 软键盘、完整可用性 |
| TypeScript / production Vite | PASS；大chunk警告 | 生产打包升级 |
| ESLint全量 | FAIL：ChatPage242 render ref | 需后续关闭的工程门槛 |
| qa-pages | 119 PASS检查，503注入console，0unhandled | Android和所有交互 |
| focused | 58截图/29记录，0page errors；有非目标空态/加载图 | 完整E2E或真机 |
| real API390 | 5窄闭环通过 | 笔记正式生成保存、聊天网络与双端 |
| desktop Node合同 | 15项通过（首次沙箱端口EPERM，获准loopback后重跑） | 真实网络与打包 |
| native Electron | preload/workspace、导航设置Esc、正常关闭3项通过 | 完整桌面回归/Windows |

日志与机器结果在 `docs/qa/mobile-s3/evidence/`。补充回执测试11项通过：作答响应丢失→刷新→同operation恢复且practice_count=1、候选校对/显式收录、笔记明确发布、聊天确认中断→同task恢复且用户问题仅1条、导入取消失败不发布、Goal跨页暂停。聊天本轮返回legacy task_身份；SQL Goal为rtask_，不能据此宣布SQL native chat断网通过。旧脚本因按钮“提交并查看解析”已变为“查看参考答案”失配；临时副本仅修选择器后重跑，原失败保留，不纳入通过数。

后续仅跑必要现有合同和新增有意义的故障用例：SQL任务/恢复/取消、事件消费者、请求identity、notes CAS/来源、错题/练习回执、readCache/连接失效；前端lint/type/build；desktop已有单元与原生Electron三宽度。不为样式微调新增镜像实现测试。

## 9. 可执行 Exit Criteria / Acceptance Matrix

每项必须带build+runtime身份、设备/浏览器、操作时刻、同一Session/task/run/资产ID、截图或回执；密钥不得进入记录。详表含当前状态与复现步骤，不以总均分抵消关键失败。

1. Android实际手机独立完成：教材→选择章节→本章提问→正文及工具状态→回原教材位置→整理/查看笔记→来源会话。缺少章节材料时明确缺失，不把重点当全文。
2. 所有纳入S3的P1修复；无P0交互阻断/状态损坏/重复执行；无依据的风险项经故障注入关闭或独立记录阻断。
3. 360/390/430长公式/矩阵/图片/表格/回答末端可访问；正文无整体横向溢出，局部横滚有提示；最后内容能滚到composer上方。
4. Android软键盘打开、输入多行、附件、关闭键盘、安全区与浏览器工具栏变化，发送/停止/返回可触控，不互遮。主要触控区≥44×44且不重叠。
5. 连接中、正在生成、已完成、已取消、已失败、可恢复、无法恢复7态可明确区分；取消未确认属于等待对账，不显示取消成功。
6. 首ack前/工具中/正文中/terminal后各断一次流；恢复只读对账；不重复用户问题/模型请求/工具/保存；后台5/30分钟、切网、主机睡眠恢复验证同identity。
7. 快速会话A→B→A、页面切换、旧run迟到、桌面和手机同会话的读取与操作，SQL权威及resume fence不被旧投影覆盖。
8. notes明确保存、CAS冲突、错题候选校对、作答回执未知恢复都保持原权限/幂等合同。、
9. 前端全量测试/lint/type/build、相关Python与桌面合同通过；Electron1280/1024/760主要聊天、教材、笔记、错题流程正常。
10. 真机Android/Tailscale签收；没真机能力则人工操作并保存记录，U不得升级PASS。记录路径/采样时间及HTTP耗时、首事件/首正文、恢复耗时、字节/请求数；不制定脱离现实DERP的绝对延迟门槛。

## 10. V1.0 前必解与范围外

必解：M3-01–08纳入范围的实现/风险关闭，以及M3-15真机门槛；M3-09若末端不可读提升为必解。当前RC判断为**未满足**，原因是连续教材链路、手机关键操作及可信恢复/真机证据仍有缺口，不是因为所有页面都需要重做。

不纳入：Runtime架构迁移、新默认模型、模型路由、第二套SQL/同步DB、权限/工具合同改变、开放Agent Loop、Tailscale线路强制/新协议、移动全新首页/底部栏、通用PDF选文阅读器、桌面全站换肤、手机PWA/推送、离线付费自动重跑、大规模新产品功能。

**此处停止。本轮方案待用户审阅批准后再实施，不因审计完成自动进入B1。**
