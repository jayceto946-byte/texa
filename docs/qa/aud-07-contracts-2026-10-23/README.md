# AUD-07 冻结与当前工具合同分离

日期：2026-10-23（Asia/Shanghai），起点 `2ec2c04`，分支 `Texa_MacOS`。仅评测层修复；没有修改生产工具、Policy启用状态、模型配置、依赖、数据库或索引，没有付费模型调用。

## 根因与修复

历史数据集绑定v1教材schema；当前生产v3增加可选continuation。两个旧测试错误要求历史与当前完全相同；当前Runtime有限基准的期望参数也遗漏规范绑定产生的 `continuation:null`，因此观测到两个binding_errors。这是评测合同漂移，不能据此认定线上检索失败。

保留历史审批和全部样本，新增独立 `texa.runtime-tool-contracts/v1` 固定当前metadata/schema，显式适配旧查询到v3空续读；非空续读不能映射回旧合同。当前Runtime报告标明 `current-runtime-policy-tools/v1`，不冒称旧冻结基线。CLI增加绑定、越界候选及离线调用门槛。详见 [合同](../../contracts/runtime-tools-v1.md)。

## 验证

| 检查 | 结果 |
|---|---|
| 修复前原三文件 | 227 passed / 3 failed，3.66秒，`before.log` |
| 首次修复原三文件 | 230 passed，`initial-after.log` |
| 最终定点六文件 | 295 passed，5.26秒，`focused-final.log` |
| 实际暂存源码独立导出 | 同一六文件295 passed，5.55秒，`staged-focused.log`；不加载工作区搁置实现 |
| 全量工作树 | 2199 passed，6条既有弃用warning，82.94秒，`backend-full.log` |
| 当前有限基准CLI | exit0；11/11任务轨迹通过，21/21观察覆盖、11次绑定检查/0错误、0禁止候选、0真实模型，`current-baseline.json`、`baseline-cli.log` |
| 历史冻结完整性 | 390个已跟踪历史快照/fixture/金标/基准文件与起点Git字节一致；`frozen-integrity.json` |

新增30项回归覆盖schema/metadata/manifest/source完整性、兼容映射、旧ref拒绝、非空续读不可降级、CLI拒绝无效基准，以及真实临时Canonical IR和Runtime预算。初次新增预算测试用了错误的收据字段名，纠正为实际 `tool_version` 和 `RuntimeConflict`；保留 `continuation-contracts.log` 的首次失败，最终回归通过。该失败是测试实现错误，没有据此修改生产收据或预算行为。

所有教材、SQLite和学习数据使用临时目录；全量和定点复用隔离runner。当前评测报告中的1.0只代表这些固定替身轨迹，不能当成线上答案准确率或生产Policy启用批准。此次没有UI/桌面路径改动，未重复Electron界面或安装升级验收；全量覆盖现有桌面后端相关合同。

## 复现

```sh
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q tests/test_policy_dataset_v0.py tests/test_policy_seed_v0.py tests/test_runtime_policy_v0.py tests/test_runtime_tool_contracts.py tests/test_textbook_context_expansion.py tests/test_agent_runtime_textbook.py
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q
ENV_PATH=/dev/null DATA_DIR=/private/tmp/texa-aud07-offline venv310/bin/python -m evaluation.runtime_policy_v0 --output /private/tmp/texa-aud07-current-baseline.json
```

只读adapter模块不导入执行入口，不将旧Dataset转换为新金标。回滚限定本次评测代码、测试、独立manifest与文档，不回滚生产v3，不改历史pins或用户数据。搁置差异仍留工作区，共享patch_notes只提交此次条目。原始工具日志保留尾空格/空行；代码和文档单独执行空白检查。

暂存版本通过 `git checkout-index --all --prefix=<临时目录>/` 导出，在临时目录用已有Python3.10运行；测试前后没有修改生产源码。提交前本地搁置保护及代码/文档空白检查通过，历史目录无任何暂存差异。
