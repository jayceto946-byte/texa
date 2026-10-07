# Policy-SFT-V0 非模型迁移包（2026-10-07）

本包迁移实验定义、数据、离线 Harness 与历史记录。**不含 CUDA trainer 实现**：本次不做 Windows/CUDA 改造。Mac 冻结脚本保留供后续实现逐项对照，不能把它们当 Windows 执行入口。RTX 3060 Laptop 是否能在冻结配置下完成训练尚未验证；资源失败应停止并记录，不静默降低参数。

## committed：冻结资产

完整逐文件清单及 SHA256 见 `HANDOFF-MANIFEST.json`，路径均相对于 repo root；该清单同时锁定下列分组。冻结文件保持原始字节，包括 LF（`.gitattributes` 禁止自动换行转换）。

| 分组 | 内容 |
|---|---|
| Training assets | 本目录 `FREEZE.json`、`TRAIN-FREEZE.json`、`ACQUISITION-FREEZE.json`；960 seeds，Train 672/2688、Dev 144/576、Hidden 144/576（seeds/instances）；train/valid/hidden JSONL 及三个 metadata；balance、shortcut audit、system prompt、spec、experiment、protocol、token lengths/stats、data audit、train/smoke config、Runtime gate controls；`scripts/policy_sft_v0*.py`、phase runner、两个 report scripts 与原 simplified prompt helper |
| Benchmark assets | `evaluation/frozen/runtime-benchmark-v0/` 原冻结包完整搬入：FREEZE、300 cases、input/gold/hash、四个 split、prompts、schemas、ontology、原 scorer、release checks、原包 audit/validation/reproduction；`docs/runtime-benchmark-v0.1/` 分类 manifest/spec；此包的 train/dev/test/hidden_test **都是 downstream benchmark 分组，不是 SFT 训练分组** |
| Harness/runtime-contract assets | `evaluation/runtime_benchmark/` runner、parser/diagnostics、prompting、scoring、reporting、ModelAdapter/ProcessAdapter/FakeAdapter；`scripts/texa_bench.py`；生产 `policy_contracts.py` 的 PolicyObservation、admissible action 与严格 decision parser；冻结 Benchmark `audit/contract-source/` 内 Runtime gate/projection/contracts 快照；`runtime-gate-controls.jsonl`；Harness tests；离线 requirements |
| Historical Mac results | Raw Dev baseline 与 raw JSONL、step448/896 Dev 与 raw、checkpoint evals、train log、resource-abort、state、smoke、integrity、Final Report；`docs/validation/runtime-benchmark-v0.1/` raw requests/outputs、baseline reports、diagnostics/probes。全部是 Mac/MLX 历史观察，不能续跑或混入 CUDA learning curve |

## clone 后先验收

在 repo root 使用 Python **3.10**。Windows PowerShell：

```powershell
$env:PYTHONUTF8 = '1'
py -3.10 -X utf8 scripts/policy_sft_handoff.py verify
```

此检查只用标准库 + Git：验证迁移清单、三份 SFT freeze、Benchmark FREEZE identity 和全部 271 pins、文件已被跟踪、split/family 隔离与数量；不导入模型、不对 Hidden 做推理/评分。预期 960 seeds / 3840 instances，Train/Dev/Hidden 为 2688/576/576。先通过此检查，再配置运行环境。

离线 Harness 与 contract 的参考依赖在 `evaluation/runtime_benchmark/requirements-handoff.txt`。新机器单独创建 `venv310`（不要复制 Mac venv），设置 `PYTHONUTF8=1`，所有 subprocess 均继承 UTF-8：原冻结 scorer 有默认编码读取，不能改变其源码/hash 来解决 Windows 编码问题。

不要运行冻结脚本的 prepare/tokenize/train/monitor CLI：它们是历史 Mac 实现，可能重写本目录。`train-config.yaml` 中旧 `/Users/...` 路径、MLX scale semantics、原 source manifest 的 Mac `source_release` 是**冻结出处信息**。运行入口 `policy_sft_handoff.py` / Harness 不依赖这些旧路径；Harness 默认使用 repo 内 `evaluation/frozen/runtime-benchmark-v0`，显式 override 使用 `--benchmark <path>`、`--manifest <path>`。

需要检查本机路径投影时可使用下面命令（必须输出到新目录）：

```powershell
py -3.10 -X utf8 scripts/policy_sft_handoff.py materialize-paths --model C:\models\local-model --adapter-dir policy-sft-runs\cuda-01\adapters --out policy-sft-runs\cuda-01\path-config.yaml
```

它只替换 model/data/adapter_path；**保留 MLX 原配置语义，不是 CUDA 训练配置**。后续 CUDA 实现需保持 seed=1807、split、prompt、gold、candidate ordering/balancing、scorer、Hidden gates、rank=8、scale=16、最后8层、lr=5e-5、seq=384、microbatch=1、accumulation=8、2688 microsteps、448评估间隔等冻结合同；MLX scale 直接乘 BA，不能把16盲目当成 PyTorch alpha。目标层映射、量化/optimizer/数值差异应单独记录，不宣称与 Mac 数值等价。

## 新 Windows 实验次序和隔离

clone → integrity check → 单独实现并验收 CUDA execution → Raw Dev baseline once → CUDA training **从 step 0、全新 adapter/optimizer 开始** → 依 `acquisition-protocol.json` 的完整排序冻结 Dev-best → Train replay → Hidden once → freeze final adapter → existing Benchmark/Harness。

Mac 在 microstep1161因资源异常停止；step448/896 不是最终 Dev-best。`hidden-eval.json` 记录模型推理数为0，train replay未完成。不得读取 Mac checkpoint 继续跑，也不得沿用 Mac started/monitor/state 作为新 run authority。所有新输出放 `policy-sft-runs/<unique-run>/`，不能覆盖历史目录；学习曲线按 backend/run 分开。

Hidden 仅在 Dev-best 被持久冻结后允许一次模型推理；不跑 Raw Hidden baseline、不选 checkpoint、不失败自动重试。出现资源失败或尚未达到门槛时保留 not_run/degraded，不能跳过流程去 benchmark。

Benchmark gold/cases 永不进入 SFT 数据，不用于调参、checkpoint 选择，不允许根据其结果重新改 prompt/训练数据/模型参数。只有 Dev-best、Train replay、Hidden 流程结束并冻结最终 adapter 后，才可运行旧 Benchmark/Harness；结果仅为独立 downstream validation。离线 hash/schema 自检不构成模型验证。

Harness 的 `ModelAdapter.load(config) → generate(messages, generation_config) → close()` 是后续新 adapter 的接入界面；`runner.run(..., adapter=instance)` 可传入执行环境实现，不需把 gold 传给模型。`adapter_path` 是显式本机配置；已有 MLX adapter 会加载它，后续 CUDA 实现须在 load 中加载被冻结的本机 adapter 并记录 model/adapter identity、实际库与设备、模板与 raw token/time。此迁移没有实现 CUDA backend。CLI 当前真实推理仍是 MLX；Windows 不应调用默认 MLX run。真实注入 adapter 标记 downstream_validation，FakeAdapter 单独标记 self-test。

评分、replay、日志与 frozen Benchmark 校验可独立于模型运行。正常 runner 只传 task/input，保留首答原文，不把诊断恢复写回官方预测，不重试、不 best-of；replay 复用旧 raw，不重新推理。真实 benchmark 的运行配置须声明 `texa_trained=true`，并如实填写 exposure；不能冒称 untouched。

## intentionally excluded

Qwen 权重、HF/LM Studio caches、MLX model/cache、全部 LoRA/checkpoints/optimizer state、venv/site-packages、Python caches、`.DS_Store`、临时 monitor/started/pid/lock、console/inference 临时日志、已失效的 `policy-sft-v0-20261007-invalid-topic-label/` 本地实验目录。原 frozen Benchmark 内 pinned 文本审计文件必须保留。Mac train-log（约470KB）有资源/有限性审计价值，保留。

冻结文档与历史 JSON 中可能有 Mac 绝对路径、历史 PID/checkpoint 引用；它们作为出处保留并纳入 hashes，不代表复制文件或运行依赖。禁止全局替换它们以致改变 freezes/replay identity。`HANDOFF-MANIFEST.json` 列出每个包含这类路径的资产，非历史可执行路径依赖已切断。无密钥/模型文件允许进入包。

## needs to be recreated on Windows

Python3.10 venv、CUDA兼容 PyTorch/训练库、NVIDIA 驱动与 CUDA执行实现及依赖锁、独立取得的模型/可核对 tokenizer、与冻结 semantics 对齐的 CUDA trainer/adapter loader、step0 optimizer/adapter、全新 run authority/日志目录、Raw Dev baseline/CUDA learning curve、Dev-best冻结回执、Train replay、Hidden一次回执、最终 adapter hash与downstream benchmark结果。模型必须在新机器单独获取，GitHub不迁移模型。

仓库原有 `assets/embedding-runtime/.../model.onnx` 为 Texa 的约90.45 MiB embedding 发布资产，已在既有历史中；本迁移清单不含它，未改动或新增它。普通全量 clone 会包含这个既有模型。若 Windows 仅复现实验而不运行 Texa 桌面端，可使用 Git sparse checkout（按 HANDOFF-MANIFEST 的分组目录，包含 backend/services/decision、evaluation、scripts、tests、docs/runtime-benchmark-v0.1、两个 validation 目录和根属性文件），配合 `clone --filter=blob:none --no-checkout` 避免取出该资产；不为本次迁移删除桌面端原依赖或重写 Git 历史。

本次验收记录见 `HANDOFF-INTEGRITY.json`；任何新依赖/后端改造另行提交。迁移 commit 不包含当前工作区其他业务/UI/架构修改。

仅实验资产的 clone 示例（URL 替换为本仓库地址）：

```powershell
git clone --branch Texa_MacOS --filter=blob:none --sparse --no-checkout <repo-url> texa-policy
cd texa-policy
git sparse-checkout set backend/services/decision evaluation scripts tests docs/runtime-benchmark-v0.1 docs/validation/runtime-benchmark-v0.1 docs/validation/policy-sft-v0-20261007
git checkout Texa_MacOS
$env:PYTHONUTF8 = '1'
py -3.10 -X utf8 scripts/policy_sft_handoff.py verify
```

这也适用于保留既有 Git 历史但只取出非模型工作树；离线依赖来自新建环境，不来自 sparse checkout 外的本机文件。由于 blob:none 是按需获取，不要随后全量 checkout 或打开原 embedding 资产路径。
