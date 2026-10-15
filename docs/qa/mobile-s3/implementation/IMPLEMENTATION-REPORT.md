# Mobile S3 V1 Candidate 实施记录

2026-10-14（Asia/Shanghai）。用户最终授权：**番茄任务是唯一新增能力；其他仅精简、适配、修复已有流程。** 实施在 `feature/mobile-s3` 独立worktree；master未改代码、未自动合并或推送。已正常退出旧Electron并切换同一59999端口，Serve地址保持原值。

## 已实施

|范围|改动与证据|
|---|---|
|顶栏/侧栏|手机共线基准、单一关闭、紧凑按需功能区、显著全宽新对话、历史占主要空间；保留原会话管理/笔记动作|
|对话菜单/范围|手机移除常驻header会话菜单/大scope，既有范围入口保留在输入“学习操作”；会话管理留历史；ScopeSelector纯尺寸role按页面适配|
|输入工具|手机相机/相册/教材图/历史错题归并附件文字菜单，公式/学习操作保留，发送停止固定右侧；桌面入口保留|
|数学画布|移除旧max-content在手机/平板的强制宽度；KaTeX原子base按有效宽度排版，不改SQL正文/公式源码；不可分表达式保留局部滚动；两条完整长积分/三角等式链360/390/430全部拟合，无整画布横移，768–1280通过|
|教材|缩减分类占高，主体flex剩余空间+主滚动；保留既有管理能力。没有增加章节阅读器、阅读/学习工作流或新导航体系|
|笔记|手机header正式保存/返回/预览与草稿状态分行，44px块操作；最后固定header高度覆盖已修正；显式保存/CAS原机制不变|
|旧Goal409|服务只读投影核对当前/冻结合同，旧任务不再无效resumable；中文原因保留结果，开始新执行需用户明确确认。未补造旧hash/手改run/绕fence|
|既有恢复|回前台/online只读当前会话（流仍活跃则不替换），取消迟到读取；显式重读，不自动重发POST；隐藏Goal不持续密集轮询|
|唯一新增：番茄任务|关联现有Goal；任务内容/可调分钟、从已确认完成条件选任务、聊天/目标页开始暂停切换、手动完成；单专注权威、回执核对、刷新恢复；到期不自动完成/执行，不修改Goal/Runtime/SM-2|
|工程|修复ChatPage render写ref的lint门槛，稳定模型/权限/证据/SQL Runtime架构未改|

## 数据合同与实际部署

同一 `goals.db` schema1→2增量表：`focus_tasks`、`focus_state`、`focus_receipts`，没有新同步DB。首次Focus访问迁移前SQLite一致备份，事务创建表/版本升级；一个当前状态revision，命令operation_id+payload_hash+CAS。Receipt先于revision检查，重复同operation返回原回执，不再次执行。读/写连接明确关闭。

正式库部署前后：schema1→2、Goal数量1→1，Goal id/revision/status/snapshot hash完全相同，备份数量1。切换前SQL活跃运行0，legacy仅completed/degraded/interrupted/waiting_for_input，无运行中任务。未丢弃等待输入/中断任务，没有模型调用。

schema2不能直接用旧schema1二进制打开；回滚需保留当前v2文件/专注回执，按契约导出新增记录后再恢复v1备份，不能静默用旧快照覆盖迁移后的学习修改。隔离测试已验证备份integrity及旧Goal可读取；没有在生产库演练破坏性还原。DDL/回滚边界见 [FOCUS-DATA-CONTRACT.md](FOCUS-DATA-CONTRACT.md)。

服务health ready，embedding/retrieval ready；Tailscale网页HTTP200。桌面重启会轮换临时管理token，手机若回到连接页，需要从桌面复制新token重新配对；不在文档/日志持久化token。

## 验证

- Python3.10.21：79项相关测试通过，涵盖8项专注/旧Goal投影测试及既有Goal、恢复、S0/S1、笔记；6既有warnings。早期沙箱collection失败保留，获准正常路径后重跑通过。
- frontend：45文件203 tests通过；TypeScript、全量ESLint通过。新增模块格式整理后定点type/lint通过；Vite生产构建通过，既有大chunk提示保留。
- desktop Node合同：15通过；真实隔离Electron preload/workspace、导航→设置→Esc、正常关闭3通过。
- 既有真实API/SQL学习流程：11场景通过（错题/复习/习题、笔记、chat interrupt/resume、Goal、导入失败/取消），model/parser为合成输入。
- 新专注真实UI：创建→启动→跨页→暂停响应丢失→原operation回执→刷新恢复→用户完成且Goal不变通过。后台时间/到期/切换/双端CAS由存储状态测试通过，不声称Android锁屏实测。
- 最终长公式7视口：360/390/430/768/820/1024/1280，正文scrollWidth==clientWidth，手机两条display链scrollWidth==公式clientWidth。实际读390最终图；长矩阵/图像真机另列待验收。
- 页面框架：初轮119检查；最终关键页58检查，unhandled=0，仅有意503console；笔记header最后定点复测4项通过，errors/unhandled均0；人工检查390px草稿图，正文与操作无重叠。早期focus-reading样例仅inline/随后display局部横滚的图仅诊断，不作最终拟合通过证据。最终依据reading-final-results与*-reading-final.png。

证据按本目录 `evidence/` 分目录保留。本轮未获取真实模型输出、未新增付费调用、未优化或更改Tailscale路径。

## 仍需真机验收 / 明确延期

- Redmi实际软键盘、安全区、浏览器栏变化、锁屏5/30分钟、切网/DERP与双端，需用户按同一网页复测；真平板未验证。模拟viewport不等同Android/平板。
- 首task ack前丢失、真实SQL native chat工具链的断网/结果未知组合，本轮没有全面生产故障注入；保留现有门槛和不自动重放，不能凭正常legacy聊天恢复宣布全链路可靠性完成。
- 只修已有教材入口/返回，不新增教材章节提问/阅读器链路；原审计中未实现能力仍未实现，按用户候选发布范围延期。
- 番茄任务V1限制：最多100个持久化任务；时间到不自动开新番茄；只有应用内状态，无系统通知/PWA；内容和时长在创建前编辑；客户端只读缓存不是离线学习库。
- 复杂LaTeX/矩阵保持原结构，无法自然断行时局部横滚；正文不整体横移。没有把“所有数学一定无横滚”当保证。

**本次已完成上述Candidate实现并上线同一入口，不声明V1 RC真机签收。**
