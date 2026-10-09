# Mobile Remote S1 学习业务闭环

日期：2026-10-09。Git 基线：`9b04c87`（Mobile Remote S0）。开始时工作区有大量既有修改，起始清单见 `baseline-status.txt`；既有 diff 已另存 `/tmp/texa-mobile-s1-existing.patch`，未提交、暂存或重置既有改动。本次不开展 S2、不改网络/鉴权、Policy Router、Runtime 决策或联合图片教材 RAG。

## 实施结果

- `backend/services/mistake_images.py` / `backend/api/mistakes.py`：现有图片流接收可选 `original_file`；分别保存原始字节与裁剪/OCR 工作图到稳定 task 目录。校验实际可解码图片、体积和 4000 万像素上限，工作图修正 EXIF 方向；错误不调用视觉模型、不创建正式学习资产。新增受既有鉴权保护的任务原图读取接口，路径限定在管理图片目录。识图/生成失败后保留已接收 task 资产。
- `backend/services/visual_session_assets.py` / `backend/services/learning_task.py` / `backend/conversation_memory.py`：图片任务投影保存完整题干、公式、选项、图形结构、手写文字、不确定项与任务关联。补充材料更新同一 user message，追加更新事件，保留同一 ID；完整答案仍由 Session SQLite 保存，不用 4000 字 task 预览替代。公开任务提供鉴权图片 URL，不用手机回传本地文件路径。
- `backend/services/mistake_chat_sources.py` / `backend/api/mistake_lifecycle.py` / `memory/mistake_lifecycle.py`：按服务端持久化 user message/turn 读取完整问题、答案与 VisualProblemIR；task 资产复制到现有草稿附件目录；保留 conversation/message/turn/task 来源关联。忽略客户端占位题干；草稿默认等待校对。原来源去重仍在 SQLite 事务内执行，重复 capture 复用草稿，重复 save 返回同一正式记录。正式记录保留完整 explanation。
- Session Notes 复用现有完整 turn 的 SQLite 单事务冻结。图片题干和视觉文字已进入该冻结来源，因此生成模型不需要读取原图。未修改现有笔记模型/Job/CAS/保存链路；新增实质回归覆盖生成、编辑、重复保存及同库重读。
- `frontend/src/pages/ChatPage.tsx`、`ChatMessage.tsx`、`contexts/ChatContext.tsx`、`features/mistakes/imageProcessing.ts`、`ProblemImageEditor.tsx`：相机入口 `capture=environment`、全图默认预览、裁剪/扫描增强/旋转、格式/空文件/超限错误；图片 multipart 沿用同一端点、鉴权和 canonical SSE 解析，XHR 提供上传百分比及上传/解答阶段错误，不自动重发；上传同时保留原件；IME composition 时 Enter 不发送。当前 turn 显示识别题干，刷新 Session 可查看原图。
- `frontend/src/pages/MistakeIntakePage.tsx`：校对状态更新移出 React updater 副作用；现有显式保存流程保持。
- `frontend/src/features/notes/notes.css`：手机笔记操作栏允许换行，编辑框 16px、底部 safe area。没有大规模 UI 重构。

## 自动与本机验证

| 项目 | 实际结果 | 证据与限制 |
|---|---|---|
| Python 3.10 后端合同回归 | 140 passed，6 warnings | `python-tests.log`；venv310，ENV_PATH=/dev/null，数据在 /tmp；真实图像字节 + 桩模型 |
| 前端 Vitest | 169 passed / 36 files | `frontend-tests.log` |
| TypeScript / Vite production build | 通过 | `build.log`；有既有大 chunk 提示 |
| 本次前端文件 ESLint | 通过 | `lint.log` |
| Electron 合同测试 | 15 passed | `desktop-tests.log` |
| 实际桌面入口 | 已拉起原数据目录开发桌面，loopback 59999 | 关闭旧孤立后端及误启动的 61472，沿用原配对 token/instance（未输出、落盘或改配）；health、remote-ready、books/list、chat/conversations 返回 200 |
| UI 隔离预览 | 390px 聊天相机入口；375/390/760/1024/1280px 笔记编辑/保存可见，无页面整体横向溢出 | In-app Browser 桩数据；不是 Android、软键盘或相机实测；390px 竖图/旋转横图、1280px 横图的 stage 与图片尺寸一致，8 个 24px 手柄均在图内 |
| git diff --check | 通过 | 既有未提交改动保留 |

新增 `test_mobile_remote_s1.py` 验证：原始 EXIF JPEG 字节与 HTTP 原图响应一致；独立工作图方向修正；超过 4000 字的完整答案进入 Session / 错题 / Notes snapshot；完整公式、选项和视觉结构继承；草稿须校对；重复 capture/save（含另一 operation_id）不产生第二条正式错题；伪造来源和损坏/空/HEIC 上传不能进入正式资产；已正式保存草稿的旧标签不能再 PATCH 为新的草稿状态。前端 transport 回归覆盖上传进度、鉴权、完整/缺终止边界、上传/解答网络错误、HTTP 错误和超时，不重发图片。`test_session_notes.py` 新回归验证图片题文字冻结、桩模型笔记生成、人工编辑、幂等保存及重新打开同一个笔记数据库。

## Android Chrome 真机验收状态

用户确认有已通过 S0 连接的 Android 手机可协助验收。桌面已由本次工作拉起。首轮用户反馈：相机与裁剪可用，但选框略超出外框、不好操作；发送后始终只有“思考中”，没有识图执行记录。检查桌面没有对应的新图片任务；本机损坏图片 multipart 在约 0.06 秒返回 canonical 图片解码错误。因此首轮闭环失败，不能认定模型开始推理或解答成功。已修正图片 stage 尺寸、内置 24px 手柄与遮罩边界；已新增上传进度、上传与解答阶段错误提示，通过测试构建并由本次工作刷新后端，59999/原数据/原配对均保留。第二轮用户反馈仍为裁剪框越界、没有上传提示、只有“思考中”，仍失败。随后只读核对 59999 与现有 Tailscale 入口，首页与当前 index/ChatPage 资源均逐字节匹配新构建，Serve 确认仍转发到 59999；因此“手机未获得新代码”只是待核实假设，尚不能归因于缓存。用户随后确认域名路径正确、问题带照片附件、也能看到正在上传，实际问题为上传过慢。只读 Tailscale 状态与 3 次 ping 显示 Android 活跃连接没有直接地址，均经过 DERP LAX；延迟 1.049s/396ms/443ms。这不是吞吐量测量，不能独断全部慢因。本次未改网络。按用户明确要求加入上传前有损压缩：小文件保留，大照片完整画面最长边 2560、JPEG 0.82（超过目标后 0.72，必要时 2048），另保留 1800 以内的独立裁剪图；若压缩更大则保留原文件，错误不静默上传大原件。大照片的“完整图片”是完整画面压缩副本，不再是相机原文件逐字节保真承诺。In-app Browser 真实 canvas 对 4000×3000、9.8 MB 测试 JPEG 的完整帧与裁剪图合计约 0.8 MB，390px 上传体积提示可读，无横向溢出。原 Tailscale 入口已确认返回压缩版构建。Android 压缩后实际耗时、识图及保存闭环尚待复测。**以下未完成项不声明通过**。

| 步骤 | 状态 |
|---|---|
| 拍照、旋转/裁剪、上传 | 首轮相机/裁剪可用；边界操作问题已修复待复测；上传未确认成功 |
| 真实模型解答与公式显示 | 首轮卡在“思考中”，失败；更新后待复测及人工核对 |
| 刷新同一 Session，原图/完整题干/回答仍在 | 待真机 |
| Session 收录错题，校对并显式保存，重复保存 | 待真机 |
| 从 Session 生成笔记，手机编辑并保存，重复保存 | 待真机 |
| 桌面重读相同 Session/mistake_id/note_id | 待真实数据交叉确认 |
| 损坏/超限上传界面反馈与刷新重读 | 后端离线合同通过，待真机 |

## 真机操作脚本

1. 手机刷新原 S0 地址，新建独立会话并拍摄一道完整、清晰、可人工核对的题；发送“请完整讲解这道题”。确认公式、步骤及实际答案；刷新会话确认完整识别题干、原图入口和回答。
2. 在该用户问题的“更多”中选择收录错题。核对原图、完整题干和继承解答，填写实际作答/卡住位置，勾选已校对，显式保存。返回该问题再次收录，应打开同一正式错题；刷新应仍能读到附件和正文。
3. 会话更多中整理笔记。生成完成后进入逐块编辑，添加“S1 手机编辑验收”一段并保存。刷新笔记；桌面打开同一笔记核对新增文字，记录相同 note_id。再进入笔记编辑保存属于新 revision，不应误计为重复记录。
4. 桌面查看同一会话和错题，核对原图/文字/解答及资产 ID。提供 ID 或页面路径即可，不提供 token/模型密钥。
5. 选择不支持格式、损坏或超限图片，确认明确报错且无正式记录；生成期间异常断线的通用恢复矩阵属于 S2，本次不宣布已覆盖。

## 遗留与边界

- 真机首轮闭环失败，更新后结果仍待补录；离线桩模型通过不证明 OCR 质量或数学准确率。视觉识别文字必须由用户校对。
- HEIC/HEIF 提供 JPEG 转换指引，没有新增转换依赖；不能声称支持 HEIC 解码。
- API 保留收到的完整图片字节；按用户后续要求，手机大照片上传完整画面有损压缩副本与裁剪图，不保证相机原件字节/像素不变。小图可保留原件；历史 task 只有工作图时只能提供已有图，无法恢复此前已丢失的原件。
- 原图是用户视觉输入，书籍范围标签不代表图片题已做教材联合 RAG。本次按用户范围明确排除该功能。
- 不提供锁屏持续生成、弱网首次事件丢失找回、跨端实时广播或离线同步；仍沿用既有恢复能力，S2 未开展。
- Windows 和打包发行版未实测；macOS 当前开发桌面与既有 Electron 合同通过。


## 2026-10-09 真机后续反馈：模型耗时与历史超时

- 用户确认 Android 实际将约 8 MB 照片压缩到约 1 MB；压缩在真机已生效。用户报告识图/解答等候约 2 分钟无结果，历史记录读取随后在等待响应头 20 秒超时，完整闭环仍未通过。
- 最新桌面任务 `task_9c7b8ad469064330bed5a9872ecd831d` 已 `degraded`，视觉 IR 已生成，终态约 67.3 秒，识图约 15.5 秒；完整回答 1732 字，outcome `projected=true`，保存的 user 463 字、assistant 1732 字。通过当前桌面实际 GET 重读同一 turn，user/assistant 均关联同一 task，user 含完整识别题干；真实手机上传的完整帧 1,027,626 字节、工作图 226,893 字节，鉴权原图接口与保存完整帧 SHA-256 一致。此为真实上传数据的服务端保存核对，不替代 Android 刷新/桌面 UI 验收。未重跑模型。人工检查保存的极限题求解给出 -1/2，核心推导正确；内部验证仍 failed，未修改验证状态，不能据此声明 Android 展示/数学普遍准确率通过。
- 本机 health/该会话读取分别约 0/10 ms，原入口在 Mac 上读取约 50 ms；Mac 访问自身 Tailscale URL 不代表 Android→Mac 的中继路径。手机状态仍经 DERP LAX、无直接地址，因此远程传输为疑点，尚未证明历史超时的全部根因。
- 该回答对应约 279 个执行事件。沿用既有图片 SSE 生成链路合并正文小片段：首个正文立即发出，后续按 96 字或有新片段时 250 ms 合并，heartbeat 和正常结束刷新剩余正文；完整答案累积、验证、来源和持久化不变。新增回归验证小 token 合并后全文/末尾/顺序不丢以及 heartbeat 前刷新；Python 140 项通过。不将离线事件数量减少冒充真机耗时改善。
- 图片解答提示按原项目解释密度约束调整：简单题默认一种直接方法，保留推导/答案，用户要求多方法时仍展开。未改模型 profile、thinking 设置、Policy/Runtime 或网络。
- 上述修改已由原桌面载入，数据/59999/配对保留。历史读取、返回流显示及新提示耗时仍待 Android 复测；正在确认两端 Wi-Fi/蜂窝网络环境。

- 用户说明两端原网络为 Redmi 蜂窝热点：Mac 接 Redmi 热点，Redmi 自用蜂窝。Mac `tailscale netcheck` 实测 UDP/IPv4 可用、IPv6 不可用、MappingVariesByDestIP=false、无 UPnP/PMP/PCP；不能归因为 Mac UDP 被封锁或 hard NAT。手机直连仍未建立。只读诊断摘要见 `network-check.json`，未保存公网 IP 或凭证。
- 用户已同意两端接入可用的普通 Wi-Fi，保持原 Tailscale HTTPS 地址，只读已有历史做对照；未确认切换或对照结果，未启动新模型调用，未修改网络/Serve/鉴权。

## 2026-10-09 历史会话闪退修复

- 普通 Wi-Fi 对照时，只读 Tailscale ping 已建立 direct，约 79 ms；用户实际反馈历史记录“闪一下解答的页面，然后回到问答界面”。直连不是页面业务验收通过，先前 20 秒响应头超时的全部根因仍未证明。
- 已确认独立前端错误：图片题 Session 的存储命名空间 `book_name=default` 被恢复为教材选择；ChatPage 在教材列表完成后自动清除无效教材，通过显式范围切换 API 新建空会话，导致刚读出的答案消失。未删除或修改历史持久化数据。
- ChatContext 将恢复来源的 `default` 转为无教材选择；ChatPage 对有消息、已加载历史页或正在问答的会话禁止后台教材自动切换；自动选择尚未完成时，历史加载/问答开始会取消迟到响应的应用。用户显式切换范围仍沿用原有新会话行为。
- In-app Browser 隔离 React fixture 使用同一 `default` 历史输入，改动前显示“从一个问题开始”，改动后持续显示已保存的问题、完整解答和 KaTeX 公式；390×844 与 1280×820 均核对。此为浏览器桩数据回放，不是 Android 真机通过；临时 probe 已删除，原有 preview 文件保留。
- 最新前端 169 项/36 文件通过，修改文件 ESLint、TypeScript、Vite 构建通过。原桌面 59999 与原 Tailscale HTTPS 入口的 index、ChatPage、ChatContext 均与当前构建逐字节相同，记录见 `history-fix-serving.json`。未改后端、原端口、配对或 Serve；未重跑模型。
- 已请用户只刷新并重读原极限题会话，检查持续显示、完整题干、回答和完整图片入口。结果待回报，错题与笔记的真实闭环仍待验收。

## 2026-10-09 真机反馈：图片入口、题干与页面加载

- 用户确认解答暂无问题，但完整图片不显示，题干暴露 OCR 实体/关系/标注/用户标记的 JSON 数组且字号过大，公式行右侧出现滚动条；教材、错题、笔记、目标与任务仍显示“正在加载页面”。因此图片浏览与多页面验收失败，不能称完整闭环通过。
- 完整图片入口此前只有鉴权 Blob 下载成功才出现，下载过程不可见。本轮改为立即显示按钮、点击后按需下载，提供加载、失败、重试与收起状态。服务端/原 HTTPS 入口实际重读已有极限题完整帧，均为 HTTP 200、image/jpeg、1,027,626 字节，SHA-256 相同；见 `photo-page-followup.json`。这是服务端实际图片可达性，不替代 Android 图片解码/浏览验收。
- 新图片 Session 冻结的正文改为可读题干、图形说明、公式、选项、图注、手写作答、标记、不确定项与图形条件/待补充材料的描述，不把实体/关系对象作为 JSON 正文。完整 VisualProblemIR 保持独立继承；未修改旧持久化记录。前端为旧图片 Session 提供呈现转换，隐藏实体对象，关系仅呈现文字描述，字符串数组转正文；新增回归保留完整题干、选项、条件与用户标记并验证转换幂等。
- 图片问题使用正文大小，手机问题 16px；公式容器添加上下空间和 overflow-y:hidden，超宽公式仅在公式自身区域横向滚动，手机不展示该容器滚动条。隔离浏览器 390×844 实测 body scrollWidth=390、题干字号16px，长独立公式容器 width365/scrollWidth376，未造成页面整体横向溢出。实际截图检查题干/公式；不是 Android 软键盘/滑动真机检查。
- 保留已构建的哈希模块，避免更新时删除仍被已打开页面引用的旧模块；为 React 路由分块添加错误边界，加载超过20秒显示明确下载缓慢文字及刷新入口。旧版分块消失是风险路径，本轮未得到手机网络日志证明它就是用户所有页面加载失败的原因。未改网络/鉴权，也未进行大规模布局重构。
- 隔离浏览器390px以 lazy import 回放教材、错题、笔记、目标页面，均从加载状态进入页面内容（桩数据）。原 HTTPS 入口检查当前入口所引用的47个 JavaScript模块全部HTTP200、逐字节匹配当前构建，主要页面返回gzip；见 `page-resource-check.json`。Mac读取自身入口不能证明Android下载性能，未检查全部字体/图片资源，页面仍须真机复测。
- Python141项、前端171项/37文件通过，TypeScript、修改文件ESLint、Vite构建通过。原桌面自动恢复载入新后端，原数据、59999、配对保留；当前HTML已核对更新。已请用户刷新原地址，只读已有题与各页面，不重拍、不重跑模型。复测待回报。

## 2026-10-09 真机复测：页面已打开，图片正文超时补齐

- 用户确认错题、教材、笔记、目标与任务页面均可正常打开，记录为四页面真实打开通过；不代表各页面领域操作及正式保存验收通过。用户指出题目层级降为正文，完整图片一直显示“正在读取完整图片”；图片查看仍失败。
- 确认客户端代码漏洞：fetchWithTimeout此前只给响应头及JSON正文设置deadline，图片/文本返回Response后已解除计时与源取消监听，随后的blob正文读取可无限等待。现明确把有限图片/文本正文读取纳入同一个60秒deadline及源取消，超时说明等待头/读取正文及HTTP状态，关闭图片会取消正文读取；SSE保持既有流路径。新增回归为停滞图片正文超时、读正文时取消以及字节/MIME不变。
- 同一鉴权任务图片接口新增preview=true，服务端按需生成并缓存完整画面1280以内JPEG78预览，原尺寸不覆盖；应用层文件能力放在MistakeImageStore。手机点击图片默认轻量预览，可主动读取原尺寸/返回预览。已有极限题原尺寸1920×2560、1,027,626字节，预览960×1280、138,891字节；本机及原HTTPS入口均200/image/jpeg，原尺寸SHA-256与此前一致，见image-preview-check.json。测量是Mac读取自身入口，不是手机吞吐量。
- 恢复问题标题层级：首段18px/600，较长识别内容16px/400。390px隔离浏览器实测，JPEG桩图解码成功，预览及原尺寸切换可用，body宽390无整页溢出；不是Android图片验收。临时probe已删除，原fixture保留。
- 当前只读ping三次经DERP lax，438/444/428ms；未得到直连。正在询问两端是否仍处于同一普通Wi-Fi；不能沿用此前直连79ms结论。客户端空闲时status的Relay字段本身不足以证明活跃中继，本结论依据实际ping。
- 其他中继路线已核对Tailscale官方文档：Peer Relay可由tailnet中UDP可达的第三台常在线机器承担，参与端至少1.86，需要管理员配置relay grant；也可自建DERP。官方在频繁DERP性能不满足时优先建议Peer Relay。官方DERP自动选择，无Texa内线路选择。仅说明可行选项，未部署服务器、改ACL/端口/Serve/鉴权；用户原S1网络范围保持。来源：https://tailscale.com/docs/features/peer-relay 和 https://tailscale.com/docs/reference/derp-servers 。
- Python141、前端174/37文件、TypeScript、相关ESLint及Vite通过。原桌面已载入预览后端，原数据/59999/配对保留，HTML已核对当前构建。已请用户仅刷新重读原题预览及标题，不重拍或调用模型。图片真机结果与错题/笔记真实保存仍待回报。
