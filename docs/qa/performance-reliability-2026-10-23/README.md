# 2026-10-23 工程审计原始证据

汇总入口：[问题清单](../../../PERFORMANCE-RELIABILITY-AUDIT.md)、[实施报告](../../../OPTIMIZATION-IMPLEMENTATION-REPORT.md)、[性能方法与命令](../../../PERFORMANCE-BEFORE-AFTER.md)。仅合成/冻结测试数据及统计，无正式教材或学习记录。源码身份见source-manifest.json；原工作树保护核对见preservation-check.json。

- `backend-before.log`：2131通过/4失败；`backend-after.log`：2138通过/3失败；`backend-final.log`：2139通过/4失败，含最后新增的RSS测试及搁置取消测试本轮失败。三个日志都保留，不以较有利的一轮替换最终结论。
- `frontend-before.log`、`frontend-after.log`：各251通过；`desktop-before-permitted.log`：53通过；`desktop-before.log`保留首次沙箱监听EPERM；lint/build结果同名文件。
- `witnesses-before.log`：4个预期失败的缺陷见证；`final-regressions.log`：新增7回归通过；focused/protocol/stream集合日志用于局部验收，彼此有重叠。
- `electron-before/`与`electron-after/`：最终生产renderer夹具结果及三尺寸截图，前后无其他审计CPU任务并行；after12项通过。`*-initial/`保留探索记录，不用于最终延迟对照。
- `local-benchmark.json`及`local-benchmark-final.log`：最终9轮交替lexical/连接对照；`local-benchmark.log`为早先采样。
- `runtime-contention-before.json`与`runtime-contention-after.json`：300ms真实写锁下生产SSE心跳；`runtime-contention.json`为未预热import探索。`runtime-reproduce-*.json`为新增--baseline入口复核，388.92→12.77ms，同样3chunk无错误，不覆盖原样本。
- `embedding-baseline.json`与`.log`：真实本地ONNX，20/5/20次，吞吐门槛FAIL；RSS原字段错误。`embedding-rss-correction.json`单独明确单位纠正，不能当推理重跑或内存优化。
- `chroma-baseline.json`与`.log`：独立真实Chroma合成向量；不含embedding和教材召回。
- `build-sizes.json`：旧dist/两个干净构建数量，非安装包体积；没有清理在线旧hash资源。

截图仅用于分页与公式/布局回归；实际模型、正式大教材、手机、安装升级和长期负载未在本轮验收。重新执行脚本可能覆盖输出，先另存需保留的样本。环境及完整命令以性能报告为准。

最新当前树补跑：`backend-current-tree.log`为2163通过/3失败（91.80秒），含另一任务图片恢复新增用例；`test-source-start.json`与`test-source-stability.json`记录运行前后源码一致。原审计最终出现过的搁置取消测试此次通过，前一轮失败不删除。另一任务已暂存其独立修改，本任务未暂存/提交。

AUD-09 后续已实现发布输入隔离，新的真实构建及回归证据见 `../aud-09-release-2026-10-23/README.md`。原始 `backend-final.log` 含范围外traceback，保持本地原文件；提交中的 `backend-final-summary.md` 记录hash和完整失败计数/摘要。历史“未提交”描述只记录当时状态；本次按用户授权一起提交相关修复。
