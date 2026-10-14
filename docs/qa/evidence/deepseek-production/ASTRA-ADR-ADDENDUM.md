# Astra 二审补充记录（Sol 整理）

2026-10-13。实际复现：graph 级 max_concurrency=1 使 1Model/0Tool 的 stream(messages,updates) 停滞。faulthandler 显示唯一 executor 线程在 langgraph/_internal/_queue.py:114 wait，主线程在 pregel/_runner.py:283 futures.wait。流式等待任务占用唯一工作线程，模型节点无法获得线程。测试被中断，不记为通过。

Sol 提出局部修复：撤掉 graph 级并发限制；RuntimeMiddleware 使用 run-local Condition，按整批原生 ID 顺序放行工具，FixedRunner、回执、checkpoint 全部完成后才推进 cursor。等待方周期性检查 SQL fence 与 deadline，致命异常同步 abort 并唤醒等待方。

Astra 在二审消息中明确反馈：当前版本 stream.wait 确实占用同一调度池，撤回原 ADR 的 graph 级 max_concurrency=1 建议；Condition 顺序门可行且是较小修复。要求 batch IDs 在完整校验、checkpoint、model step 成功后发布；只允许 cursor 对应调用唯一认领；执行时释放 Condition 锁，致命错误记录首个原因并 notify_all；等待及出口检查 abort/SQL/deadline。

Sol 按该反馈实施。Astra 随后触及账户额度限制，未交付自行写成的 addendum；此文件是对实际收到消息的整理，不冒称完整二审报告。没有启动第三次审查。

实施后的 1Model/0Tool、合法多工具、预算耗尽排队项、取消和 checkpoint 失败测试已通过；测试和证据以最终报告为准。
