# Minimal Runtime Benchmark Harness V0.1

实现入口：`evaluation/runtime_benchmark/`；CLI：`venv310/bin/python scripts/texa_bench.py`（等价于 `venv310/bin/python -m evaluation.runtime_benchmark`）。模型加载、工具执行与 Texa 生产 Runtime 分离；不修改模型、教材索引或学习数据。

## 冻结包与运行环境

默认使用仓库内 `evaluation/frozen/runtime-benchmark-v0/`；同目录 `case-scope-manifest.json` 保留原始 `source_release` 作为历史出处，不作为默认运行路径。迁移到另一台机器时，通过 `--benchmark /path/to/runtime-benchmark-v0` 指定**原冻结包**，通过 `--manifest /path/to/case-scope-manifest.json` 指定分类。首次执行前校验 FREEZE 本身 SHA256、271 个 pinned 文件、case/input/gold hash 与分类 identity，再 import 原 scorer；不复制或修改评分逻辑。

评分与测试固定使用项目 `venv310` / Python 3.10。真实推理可直接使用相同解释器；本机复用经用户确认的 LM Studio 现有 Python 3.11 环境，只有 MLX adapter 在子进程运行，JSONL 通信不含 gold。该小桥接是兼容既有解释器，不是模型服务或权限隔离平台。不安装/重装依赖，不下载模型。

`local-qwen35-8bit.config.json` 为本机配置：既有 LM Studio snapshot 路径、MLX/MLX-LM/Transformers 精确版本、greedy、seed=0、thinking=false、128/384/384/256 预算。`running_alone=false` 如实表示未保证机器仅运行该推理进程。`tuned_on_v0`、`v0_failure_exposed`、`texa_trained` 必须显式声明；有任一 true 则不能标 untouched。开始用 V0 failure 调整配置后，必须新目录并更新这些声明。

8bit 身份来自 snapshot config 和实际加载模块；记录 group_size、mode、packed/nonquantized dtypes 和 text config。目录名不构成验证。revision 无可验证信息则 null；MLX-LM 只加载文本模型，sanitizer 排除 vision weights。本机可能需要沙箱外执行才能访问 Metal，不能通过换 CPU 或模型冒称同一次实验。

## P0–P3 命令

所有推理和 replay 输出目录必须不存在，不能覆盖旧实验。以下命令使用示意的新目录；本次已生成的目录不可重复使用。

```sh
venv310/bin/python scripts/texa_bench.py sanity --out /tmp/texa-bench-new-sanity.json

venv310/bin/python scripts/texa_bench.py run \
  --scope primary_semantic --smoke \
  --config docs/runtime-benchmark-v0.1/local-qwen35-8bit.config.json \
  --out /tmp/texa-bench-new-smoke

venv310/bin/python scripts/texa_bench.py run \
  --scope primary_semantic \
  --config docs/runtime-benchmark-v0.1/local-qwen35-8bit.config.json \
  --out /tmp/texa-bench-new-primary

venv310/bin/python scripts/texa_bench.py run \
  --scope secondary_semantic \
  --config docs/runtime-benchmark-v0.1/local-qwen35-8bit.config.json \
  --out /tmp/texa-bench-new-secondary

venv310/bin/python scripts/texa_bench.py replay \
  --runs /tmp/texa-bench-new-primary /tmp/texa-bench-new-secondary \
  --scope semantic_all --out /tmp/texa-bench-new-semantic-all
```

P0 为 evaluator self-test：原 sanity、300 gold round-trip、10 mutation、四完整 split 和 all 的 wrapper/API/CLI 一致性。不是模型成绩或 gold 独立语义裁决。P1 只运行独立合成 Policy case，不计质量 N；合法但错误的选择仍保留，不以 smoke 结果调整正式 prompt。每个正式 run 另有一次同样的独立 warmup；不计质量与稳态 latency。

P2 仅 primary 161；P3 仅 secondary 39，随后 replay 合并原首答，不重跑 primary。run 不提供 control/semantic_all 推理选项。replay 可加 `--split train|dev|test|hidden_test` 生成报告，源 run 预定并集仍须完整覆盖指定 scope。读取损坏 JSONL、重复/未知 ID、重叠病例、配置/模型/prompt/benchmark/库版本差异均明确报错。replay 不加载 MLX，不重新测时，不改源记录。

## 产物和测量边界

- `run.json`：锁定配置、预定 IDs 顺序、实际加载身份、版本、设备、load_ms、warmup、peak memory、complete/incomplete 与 exposure 声明。
- `requests.jsonl`：实际 messages/rendered prompt/模板设置/有效预算；模板 prefix 留在 rendered prompt，不混入 continuation。
- `outputs.jsonl`：adapter 原始 continuation、状态、finish_reason、实际 stream token 数和 request_ms，逐条 flush 后才评分；不去 think/fence/prose。
- `predictions.jsonl`：仅 `{id,raw_output}`，没有 raw 则缺省，不伪造文本。
- `official-report.json`：原 scorer 输出**原样**；`official-scope.json` 单列 scope/N/missing，不覆盖 frozen 原字段。
- `diagnostics.json`：固定 parser、source_range/transform_log、S/F/T/U、primary/secondary/semantic_all、task/split、taxonomy 和性能；恢复结果永不写回官方 predictions。
- `failures.jsonl`：官方失败、format-only 以及 operational failure；原 input/gold/raw、severity/reason、字段差异、tier/family/pair/group、源 run 引用。官方 S1 match 算成功，不把 U 当已证实语义错误。
- `report.md`：阅读版汇总；仅供 screening 和分析，不导出训练对，不启动训练或接入生产。

OOM/异常结束后已有 raw 保留，剩余预定病例以 missing 留在 N，run 标 incomplete，CLI exit=1。无 retry/fallback/resume/best-of。突然被 kill 导致无结束记录时不能宣称 complete；损坏 JSONL 不自动截尾。

`request_ms` 包含模板、tokenization、prefill、generation 和设备同步，排除 IPC、评分与落盘。p50/p95 为成功请求 nearest-rank，n<20 标不足。tok/s 使用同一有可靠 token/time 的成功样本集合，stream token 数在 stop 时含 EOS。RSS 与 MLX allocator peak 分列，不可相加，含 load/warmup；不等于与 Electron/Chroma/embedding 共存验收。

## 测试

```sh
venv310/bin/python -m pytest -q tests/test_runtime_benchmark_harness.py
```

集成测试依赖原外部冻结包；缺失时明确 skip，不能把 skip 当通过的 P0。FakeAdapter 只测接口解耦与测量合同，run purpose 会标 self-test。真实模型评分不使用 FakeAdapter 或 gold。原包与 classification 文件保持不变。

## 本次实施与实测

已完成 P0–P3：31 项测试通过，复用实际本地 8bit 模型生成 primary 161 + secondary 39 首答，无 missing/operational failure。见 [首次 Screening 结果与边界](Screening-Results-2026-10-06.md) 和 [最终合并报告](../validation/runtime-benchmark-v0.1/p3-semantic-all-verified/report.md)。旧 Spec/Plan/Change Log 中“尚未实现/未跑模型”是设计交付当时的历史状态，实施状态以本节和结果记录为准。

## Windows 非模型迁移

参见 [Windows/CUDA Handoff](../validation/policy-sft-v0-20261007/WINDOWS-CUDA-HANDOFF.md)。离线评分/replay 不导入 MLX 或 Unix resource；Windows 设置 `PYTHONUTF8=1` 并使用 Python3.10。真实推理 CLI 当前仍使用 MLX，CUDA 执行实现不在迁移范围。最终 adapter 的本机路径使用 `adapter_path`，注入其他执行实现使用 `runner.run(..., adapter=instance)` / `ModelAdapter`；模型侧不读取 gold。冻结最终 adapter 后才运行 downstream validation，不能反向调参。
