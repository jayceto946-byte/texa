# S3 Work Breakdown（未实施）

主报告第7节是批次合同。总参考11–17工程日，不含设备等待；接口缺口独立评估，不自动扩Runtime。

|工作|模块|输出/可审阅内容|依赖/验收|估算|
|---|---|---|---|---|
|B1.1能力核对|books chapters/highlights/PDF/Figure公开接口|可用章节和阅读入口清单；无内容时明确状态|无需付费生成；先确认原能力|0.5–1日|
|B1.2上下文往返|LibraryWorkbench/Highlight/chat navigation|书/章/锚点/来源返回；深链上级；不新增索引|A01/A02；传递真实scope，不只标题|2.5–4日|
|B2.1手机输入|ChatPage/composer tools|附件文字菜单、发送停止固定位置|B1接线确定；A03/A04|1日|
|B2.2编辑操作|note feature toolbar/shared UI|返回+标题+正式保存，草稿状态行|A02/A13，不改CAS|1日|
|B2.3命中区与校准|mobile shared CSS|44px无重叠、轻视觉；章节/错题顺带去重|A03/A05/A15；desktop不变|1–2日|
|B3.1故障证据|existing real API harness|首ack丢失/中断失败/旧run/双端确切复现|不能凭猜测改权威合同|1–2日|
|B3.2显示对账|chat feature hook/API客户端|foreground coalesced read、显式重读、generation fence|A06–A11；不自动POST|2–3日|
|B4.1真实手机|Android现有浏览器/Tailscale|完整学习+键盘+公式+后台/切网脱敏记录|B1–B3；A01–A16|1–2日+设备窗口|
|B4.2最终收敛|既有tests/QA/Electron|P0/P1关闭账本、RC判定与剩余限制|lint/type/build/Python/Desktop，三桌面宽度|1日|

先保留任务与状态合同，再处理局部视觉。P2只随相关改动顺带；没有证据时不立新reader、底部栏或同步项目。Phase0–4方案完成后暂停，以上均等待实施批准。


## 真机反馈修订

B1增加顶栏/侧栏/教材主滚动和scope各页面尺寸适配；B2长公式手机/平板canvas；B3旧Goal恢复409；新增B-T番茄任务/计时小控件的原型与最小持久化合同评审（1–2工程日设计，实施待核对）；B4真机新增门槛。原11–17日不包含新timer，不能当扩展后承诺。详见[实机修订](REAL-DEVICE-REVIEW-AND-S3-REVISION.md)。
