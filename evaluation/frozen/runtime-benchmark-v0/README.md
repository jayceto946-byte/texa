# Texa Runtime Benchmark V0

从实际 Runtime 工作树推导的第一版离线基准：**300 cases，200 semantic-interface + 100 deterministic controls**。中文合成语料，150配对family；train150/dev60/test60/hidden_test30。

先读 [Runtime Benchmark Spec V0](Runtime-Benchmark-Spec-V0.md) 的 A 节（Current Runtime Decision Surface），再看 [审计与差异登记](audit/Runtime-Audit.md)。机器版 [ontology](decision-ontology.json)、[task schemas索引](schemas/task-index.json)、[固定task prompts](prompts/tasks.json)、[case与frozen gold](curator/cases.with-gold.jsonl) 均已包含。

## 目录与权限边界

- `datasets/`：模型输入，只有id/task/input；不包含标签、split提示或规则预测。
- `curator/`：完整case、逐split gold与独立审阅队列；**不要交给模型训练/推理流程中的test读取器**。
- `schemas/`：9组input/output schema及实际生产schema导出。
- `audit/`：source hashes、214+个相关代码/文档/测试冻结快照、函数行号、工作树状态与差异报告。
- `validation/`：分组去重、数据汇总、规则对照、真实测试结果及评分器自测。
- `tools/score.py`：离线评分，严格JSON + frozen gold，无LLM judge。
- `tools/check_release.py`：case/schema/hash/split检查与评分器变异测试。
- `reproduction/`：合成输入源与调用真实Runtime的生成脚本。复现不是重新签发gold的许可；输出必须新目录。

语义gold是**作者冻结、待独立人工裁决**；不是已获人类审批的locked test。hidden_test是保管分区，完整包接收人可见gold，不能宣称作者盲测。控制集gold来源于真实代码，不用于证明代码理解中文正确。尚未运行0.8B模型。

## 运行

需要Python3.10+与`jsonschema`（本机已验证3.10.21 / jsonschema4.26.0）。不需要导入Texa、不读取配置/密钥、不访问网络或用户数据库。可使用现有Texa venv，无需安装新依赖。

在解压后的`runtime-benchmark-v0/`目录下：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python tools/check_release.py
```

模型推理时按每条task选用`prompts/tasks.json`对应prompt和output schema，输入只取该条input。保存**未清洗**raw output，JSONL格式：

```json
{"id":"TRB0-0001","raw_output":"{\"action_id\":\"a0\"}"}
```

以上仅演示格式，不是整个split的预测文件。缺预测照常计失败，不要只提交成功项。正常评分：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python tools/score.py /path/to/predictions.jsonl --split test --output /path/to/run-report.json
```

报告必须写到发布目录外，避免覆盖冻结交付。记录模型文件hash、量化、tokenizer、prompt版本、temperature/seed、上下文长度、输出上限、首token/总延迟、峰值内存及设备；这些由实际推理runner提供，本包不捏造。建议固定greedy、每例一次，无schema修复重试；重试/grammar-constrained decoding可以作为独立实验配置，不覆盖raw首答。

Policy仅一个action_id、理解最多四维度/三实体、Goal最大384输出token可作为首轮试验配置，但截断必须记失败；不是所有任务都沿用生产understanding的384 token预算。不同任务分开报告，不把生成器模型算进0.8B推理时间。部署前另测production gate命中与端到端行为。

## 重现生成

构建脚本需要原始Texa工作树的精确source snapshot与依赖；审计快照只保留相关文件，不是完整可运行Texa仓库。先对照source-manifest验证依赖，没有匹配就终止复现，不将新代码结果覆盖旧gold。

```sh
BENCHMARK_REPO=/path/to/matching/texa BENCHMARK_OUT=/path/to/new-build PYTHONDONTWRITEBYTECODE=1 /path/to/texa/venv310/bin/python reproduction/build_benchmark.py
```

输出新生成的300条数据与production schema，不会自动复制本包评分器/完成独立review/重新签发FREEZE。split/group、source版本变化应创建V0.1/V1候选版本。

## 验证结果的含义

`validation/release-checks.json`的300/300是gold/评分器自测，**不是模型准确率**。仓库选定测试249通过、20因旧数据集source digest不匹配失败，详见`validation/repo-checks.log`；这次没有修改它们。规则对照39/80是对作者gold的诊断，不是独立审阅的证据。
