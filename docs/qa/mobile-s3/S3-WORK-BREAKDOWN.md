# S3 Work Breakdown（综合版，未实施）

范围、实现合同与退出门槛以[综合实施方案](../../../TEXA-MOBILE-S3-IMPLEMENTATION-PLAN.md)为准。已合并Redmi反馈，timer正式纳入设计范围；本表替换旧四批+B-T追加列表。

|批次|修改模块|核心工作|问题映射/依赖|估算|
|---|---|---|---|---|
|B1 真机阻断/基础布局|MainLayout/AppRail/Sidebar、ScopeSelector、Chat header、Markdown/mathText/CSS、LibraryWorkbench、Goal服务/投影|统一顶栏、历史优先抽屉、画布宽度/公式、教材主滚动、旧Goal409与lint|M3-17–22、09/11/08；先复现再改，不绕恢复栅栏|4–6日|
|B2 核心闭环/操作|教材章节/来源往返、chat navigation、composer、notes toolbar/locator、mobile controls|本章提问回原位置、附件归并、固定发送停止、笔记草稿/正式保存分层、44px命中区|M3-01–04、10/12/13/16、18；依赖B1骨架|3–5日|
|B3 学习任务/番茄|Goal/focus领域服务+hooks、任务工作区、FocusBar、既有goals.db增量合同|任务内容/时长确认；开始暂停切换/手动完成；单活动计时/回执CAS；迁移/备份/回滚|用户新增；先具体数据合同审核，再获准迁移；依赖B1/B2|合同1–2日；实现条件性4–6日，冻结后重估|
|B4 可靠性|chat/focus reconcile、API客户端、现有真实SQL QA|foreground有界对账、首ack丢失、停止失败、迟到run、双端、结果未知|M3-05–07，14先测；故障测试可提前，接线依赖B2/B3|3–5日|
|B5 真机/RC|现有QA与Electron、人工Redmi/平板步骤|22项必需矩阵，键盘/安全区/公式首尾、锁屏切网、双端、桌面/迁移回归|M3-15、A01–A22；依赖B1–B4|2–3日+设备窗口|

合计条件性17–27工程日；不是日期承诺，原11–17日估算失效。数据/付费/真机门槛缺失时明确停在对应步骤，不扩成同步平台或开放Agent。普通布局与交互由Sol实施；复杂设计取舍先整理具体截图再定点审查，不为流程反复调用Astra。
