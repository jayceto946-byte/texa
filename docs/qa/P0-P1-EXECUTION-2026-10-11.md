# P0/P1 整改执行记录 · 2026-10-11

本轮执行了 P0 数据一致性和离线学习闭环验收，以及全路由视觉初筛和第一批跨页设计整改。**A4 已修复；P1 的本批共同问题已关闭，但全部子状态/复杂交互及真实教材、模型质量尚未全部验收。** 本记录补充首轮报告，不把历史测试结果改写为本轮结果。

## P0：A4 持久作答身份与恢复

直接练习在发送前把 operation_id 与原始作答持久化到客户端；后端在现有习题 SQLite 的 history JSON 中同事务提交主作答及回执。相同身份和相同请求重放不增加次数；身份绑定不同作答拒绝写入。候选、错题 occurrence、学习事件使用稳定键，关联失败保留 partial/unconfirmed，原请求重试后转 complete/confirmed。教材题干来源冻结，内容编辑不能覆盖已提交回执。空科目查询与显式 default 查询归一为同一客户端 scope；聊天习题卡和题库共用恢复入口。

未新增表或迁移数据库。**接口兼容变化：POST /api/exercises/practice 必须提供非空 operation_id，否则拒绝写入并提示更新客户端**；两处现有调用已同步，旧记录保持可读。新增只读 GET /api/exercises/practice/{exercise_id}/operations/{operation_id}。跨库采用持久回执与幂等恢复，不宣称跨库原子事务；尚未确认操作不会被 UI 显示为完整成功。

[12 项真实 SQLite 故障回归](../../tests/test_legacy_practice_partial_result.py)覆盖响应丢失、参数冲突、真实新作答、并发12次重试、occurrence/candidate/event 写入前后失败、主事务失败、重新实例化服务及陈旧内容编辑。[前端身份回归](../../frontend/src/features/exercises/directPractice.test.ts)覆盖持久重放、作用域归一、未确认作答不可换答案及只清理对应确认身份。

## 核心闭环实测

|层/范围|结果与边界|证据|
|---|---|---|
|完整后端离线回归|1540 PASS；6 项既有 warning|[backend.log](evidence/latest/backend/backend.log)|
|前端回归|43 文件、195 PASS|[frontend.log](evidence/latest/frontend/frontend.log)|
|Electron 单元|15 PASS；回环端口测试使用所需执行权限|[desktop.log](evidence/latest/desktop/desktop.log)|
|类型/lint/构建|PASS；已有大 bundle warning 保留|[build](evidence/latest/build)|
|真实 FastAPI/SQLite 浏览器|11 旅程 × 1280/390 两视口 = 22 PASS，模型/解析输入离线夹具|[results](evidence/p0-p1/extended-e2e/results.json)|
|实际 macOS Electron 开发壳|11 旅程 PASS，隔离 userData，真实本地 API/存储，外部 QA 后端|[results](evidence/p0-p1/electron-final/results.json)|
|后端重启持久核对|14 项已提交资产/回执/运行状态 PASS；9 个 SQLite integrity/foreign key PASS|[restart](evidence/p0-p1/restart-persistence.json)|

旅程包括错题草稿恢复、明确保存、复习草稿恢复、自评完成、手工题库输入、直接作答丢响应后恢复且只计一次、人工校对候选→确认入错题→复习完成、冻结会话来源→生成失败→手动编辑→跨页自动草稿→明确发布笔记、聊天确认中断→同任务恢复→用户问题只记一次、教材真实 Job 取消/失败→可重试且未发布、目标整理确认→启用→后台运行跨页→精确选中目标并暂停栅栏→刷新保留。

教材解析函数使用有检查点的失败夹具；取消走真实 JobManager。聊天/Goal 仅替换模型输入，保留 Runtime、事件、验证和持久流程。**没有把教材成功发布、OCR 正确性或模型答案准确率登记为这些 E2E 的 PASS。** 本次增加了教材取消 UI，等待后台 cancelled 确认后才显示已取消；cancelling 单独显示，运行中不允许重选文件或切换来源。

## P1：覆盖、决策与标准校准

复用 Inventory 和 qa-pages：19 URLs × 4 视口及主题/空/加载/错误/重试，共119项渲染检查与7个编辑/设置补图。Sol 阅读按路由和状态生成的联系表并在不确定处读取原图；其结论为初筛，不独立作为最终审美验收。初次新诊断/备份端点 fixture 缺口已补齐，最终设置补拍无未处理端点。503 为主动失败场景，另行记录，不算页面脚本异常。

Astra 共 **3 次调用、15 张原图（6+6+3）**，每批围绕表单/管理层级和响应式导航；直接读取成熟参考、待审子页和必要细节。统一决策与实际素材详见 [Visual Review Board](VISUAL-REVIEW-BOARD.md)。

已整改：普通布局底部操作区（非覆盖式悬浮）、唯一草稿保存入口、无图录入单列和字段分组、共享返回控件、24px 对象标题/18px 分组标题、目标启用与任务运行语义、导入步骤18px/参数16px、≤480px 设置单栏分类→详情且保留字段/选项/焦点。Astra 抽查还选入 Sol 初筛通过的教材列表和390设置，发现设置宽度漏检；修正后3图复查关闭。实际测试验证设置返回/进入焦点、未保存字段保留、隐藏导航不参与Tab、关闭、导入滚到底可达与长文件名。

[路由覆盖映射](evidence/p0-p1/visual-coverage.json)、[全路由检查](evidence/p0-p1/pages/results.json)、[最终设置/导入检查](evidence/p0-p1/pages-accepted/results.json)。全路由静态初筛完成；动态导入进度/模型连接失败/长笔记冲突等未逐一通过截图审美复查，其他浮层和复杂交互仍按原 Inventory 保留待审条目。渲染无溢出不能替代可读性判断。

## 数据安全与后续边界

一次未通过隔离入口的测试误写了11条测试学习事件。已向用户披露，并在用户明确授权后按 /tmp 测试资产 ID 与精确运行时间匹配清理；保留196条其他事件，清理前 SQLite 备份位于 /tmp/texa-before-test-event-cleanup.db，完整性通过。[清理记录](evidence/p0-p1/test-event-cleanup.json)。后续全部写入测试使用 /tmp 隔离配置。未安装依赖、付费调用或覆盖正式教材索引；既有 Mobile S2 改动保留。

真实教材索引成功发布/黄金集、OCR 公式表格人工质量、真实模型回答与恢复仍需独立验收；没有当前授权的付费/出境调用。真实 Tailscale 设备和正式安装包生命周期明确保留至后续阶段，本轮未执行。P1 全部异常组合与浮层仍未穷举，不宣布 S3 清关。
