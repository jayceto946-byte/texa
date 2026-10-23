# 原审计最终后端回归摘要

原始日志 `backend-final.log` 保留本地，SHA-256：`76245b748c6e20bb590a1b9bea614f2d0db351604eec0863f6ebd3de71958e6d`。日志含范围外搁置模块的 traceback，实现片段未纳入本次提交；此摘要不改写失败结果。

- 2139 passed / 4 failed，86.94 秒。
- 三项持续失败：`test_frozen_schema_matches_existing_canonical_models[search_textbook]`、`test_snapshot_binding_matches_canonical_runtime_models`、`test_finite_offline_baseline`。
- 另一项为搁置模块的 `test_network_work_is_cancelled_on_deadline_or_stop[True]`：约 35ms 后取消已返回，但 finally 标记为空。前两轮通过，根因未判定；不开展其专项修复或实验。
- 后续同树加图片恢复后的补跑为 2163 passed / 3 failed，AUD-09 新回归后的补跑为 2166 passed / 3 failed；不能用后来的通过抹去此项失败观察。
