# Issue List

2026-10-14。根因是假设，C/R/U见主报告。无截图代码风险不伪造图片；本轮未确认P0。

## M3-01 — P1

Page：教材/章节；State：populated；性质：功能/交互；证据：R/C。

Screenshot：[pages/390-books.png](evidence/pages/390-books.png)；[pages/390-highlights.png](evidence/pages/390-highlights.png)

Observed Problem：维护领先，缺本章提问及位置返回。User Impact：学生反复找书章节，规定闭环断开。

Root Cause Hypothesis：Library管理职责沿用；Highlight未接上下文往返。批次：B1。

## M3-02 — P1

Page：聊天输入；State：touch360；性质：交互；证据：R。

Screenshot：[focused/360-chat-bottom.png](evidence/focused/360-chat-bottom.png)

Observed Problem：六工具含相似图片入口，发送另起行移左。User Impact：输入区占高、主操作位置不稳定。

Root Cause Hypothesis：工具toolbar flex wrap未按手机优先级归并。批次：B2。

## M3-03 — P1

Page：笔记编辑；State：edit390；性质：交互/视觉；证据：R。

Screenshot：[focused/390-note-editor.png](evidence/focused/390-note-editor.png)

Observed Problem：顶栏标题截断、保存换行、草稿状态挤压。User Impact：辨识正式保存/草稿困难。

Root Cause Hypothesis：桌面同一行全部动作迁入窄屏。批次：B2。

## M3-04 — P1

Page：全域控件；State：touch390；性质：触控；证据：R DOM。

Screenshot：[focused/390-note-editor.png](evidence/focused/390-note-editor.png)；[pages/390-review.png](evidence/pages/390-review.png)

Observed Problem：保存62×28、排序/删除28×28、多处操作28高。User Impact：误触或需精细点按。

Root Cause Hypothesis：shared 28px desktop control未统一mobile hitbox。批次：B2。

## M3-05 — P1

Page：Session恢复；State：foreground/双端；性质：Reliability；证据：C/U。

Screenshot：NO_SCREENSHOT_CODE_AUDIT

Observed Problem：恢复事件只查网络；同会话有消息时不重读。User Impact：可能显示另一端修改前的旧任务投影。

Root Cause Hypothesis：无foreground Session/task reconcile hook。批次：B3。

## M3-06 — P1

Page：请求确认；State：pre-ack断流；性质：验收风险/API；证据：C/U。

Screenshot：NO_SCREENSHOT_CODE_AUDIT

Observed Problem：首次task确认前客户端未知taskID，request_key为服务端requestID。User Impact：结果未知时可能人工重复发问；未复现重复工具。

Root Cause Hypothesis：持久化待确认身份/查询合同待核对。批次：B3。

## M3-07 — P1

Page：取消/失败；State：interrupt failed/offline；性质：Reliability；证据：C/R/U。

Screenshot：[live-recovery-current-label/390-chat-interrupted.png](evidence/live-recovery-current-label/390-chat-interrupted.png)

Observed Problem：正常中断恢复已通过；失败只提示重开读状态。User Impact：用户可能把局部停止误认已取消。

Root Cause Hypothesis：中断失败缺就地只读对账；7态组合未跑。批次：B3。

## M3-08 — P1

Page：ChatPage；State：lint；性质：工程；证据：R。

Screenshot：NO_SCREENSHOT_ENGINEERING_LOG

Observed Problem：render写currentScopeRef触发react-hooks/refs。User Impact：工程发布门槛失败；不能据此认定数据事故。

Root Cause Hypothesis：scope ref同步位于render第242行。批次：B2。

## M3-09 — P2（不可达升P1）

Page：公式/表格；State：overflow360；性质：阅读可访问性；证据：R/C/U。

Screenshot：[focused/360-chat-bottom.png](evidence/focused/360-chat-bottom.png)

Observed Problem：长公式右端不在首视野；局部横滚源码存在。User Impact：可能读不到等号末端。

Root Cause Hypothesis：溢出提示与触摸末端验证不足。批次：B4/B2。

## M3-10 — P2

Page：章节重点；State：populated；性质：视觉/IA；证据：R。

Screenshot：[pages/390-highlights.png](evidence/pages/390-highlights.png)

Observed Problem：目录大框置身份之前；正文又框、打印突出。User Impact：学生先看导航装饰再找章节。

Root Cause Hypothesis：桌面目录列stack而非手机章节优先。批次：B1顺带。

## M3-11 — P2

Page：抽屉/返回；State：open；性质：导航；证据：R。

Screenshot：[focused/390-navigation-history.png](evidence/focused/390-navigation-history.png)

Observed Problem：业务域与历史可扫描；上下文返回弱。User Impact：跨资产返回多余开抽屉。

Root Cause Hypothesis：全局域入口代替局部位置导航。批次：B1顺带。

## M3-12 — P2

Page：错题详情；State：populated；性质：视觉/内容；证据：R。

Screenshot：[pages/390-mistake.png](evidence/pages/390-mistake.png)

Observed Problem：顶部题干摘要与正文重复。User Impact：首屏重复阅读挤掉作答反馈。

Root Cause Hypothesis：摘要身份与正文相同素材。批次：B2顺带。

## M3-13 — P2/待核真数据

Page：章节元信息；State：populated；性质：视觉；证据：C/R/U。

Screenshot：[pages/390-highlights.png](evidence/pages/390-highlights.png)

Observed Problem：bookName和ISO时间直接显示，qa-book为合成值。User Impact：来源难识别、时间阅读成本。

Root Cause Hypothesis：内部参数直接用于显示；真实书名需核对。批次：B1顺带。

## M3-14 — P2测量先行

Page：PDF资源；State：open/reopen；性质：资源；证据：C/U。

Screenshot：NO_SCREENSHOT_CODE_AUDIT

Observed Problem：完整鉴权blob后iframe，无共享资源缓存。User Impact：大书中继下载成本待量化。

Root Cause Hypothesis：useAuthenticatedBlobUrl每次创建/销毁。批次：不自动纳入。

## M3-15 — P1验收门槛

Page：Android/Tailscale；State：keyboard/background/offline；性质：验收；证据：U。

Screenshot：NO_REAL_DEVICE_EVIDENCE

Observed Problem：无本轮真机键盘/安全区/锁屏切网双端证据。User Impact：不能判RC可用。

Root Cause Hypothesis：当前工具无连接Android自动化。批次：B4。

## M3-16 — P2

Page：聊天恢复提示；State：interrupted；性质：文案；证据：R。

Screenshot：[live-recovery-current-label/390-chat-interrupted.png](evidence/live-recovery-current-label/390-chat-interrupted.png)

Observed Problem：普通文案出现checkpoint user_stopped。User Impact：内部术语增加理解成本。

Root Cause Hypothesis：checkpoint code直接显示。批次：B3顺带。
