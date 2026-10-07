# Policy-SFT-V0 Final Report

2026-10-07。状态：**因系统资源异常停止**。仅测试本地 Qwen3.5-0.8B-MLX-8bit 在当前冻结合成 Policy 合同下的task-acquisition。无下载、换Base、Runtime改动或其他模型任务。

## 实验身份与执行

修正版数据960 seeds、80个措辞家族、每seed四排列；Train/Dev/Hidden为672/144/144 seeds（2688/576/576实例）。同主题/模板/候选集合下有反事实有效请求，gold语义条件组均衡。所有位置/ID分层均衡，family与seed不跨split。初版topic-label异常run留在独立归档，本报告不混入其baseline、smoke、更新或结果。

原有数据、split、prom# Policy-SFT-V0 Final Report

2026-10-07。状态：**因系统资源异常停止**。仅测试本地 Qwen3.5-0.8B-MLX-8bit 在当前冻结合成 Policy 合同下的task-acquisition。无下载、换Base、Runtime改动或其他模型任务。

## 实验身份与执行

修正版数据960 seeds、80个措辞家族、每seed四排列；Train/Dev/Hidden为672/144/144 seeds（2688/576/576实例）。同主题/模板/候选集合下有反事实有效请求，gold语义条件组均衡。所有位置/ID分层均衡，family与seed不跨split。初版topic-label异常run留在独立归档，本报告不混入其baseline、smoke、更新或结果。

原有数据、split、prompt、gold、评分函数、训练目标与Hidden gate哈希保持不变。执行入口为policy_sft_v0_acquisition.py；新增执行协议单独冻结，不修改旧scorer。只忽略与实验无关的macOS .DS_Store元数据。模型推理输入不包含gold/family元数据；raw首答严格解析、不修复、不重试、不用受约束解码。

正式配置：末8层，rank8，MLX直接scale16，dropout0，lr5e-5，batch1×accumulation8，max_seq_length384，checkpointing、mask_prompt；实际MLP和全/线性attention投影，不改模型结构。使用原生MLX-LM loss与compiled stateful accumulation；固定padding384，按原始长度mask，不截断，保持原有seed1807 shuffle完整epoch。

唯一原始模型对照仅评完整Dev。正式配置smoke只做5 microsteps，因此累计梯度但**0 optimizer update**；optimizer状态已初始化并检查finite，不声称这5步验证了Adam更新后的状态。正式训练另起干净模型、适配器、Adam和梯度累积；预注册2688 microsteps / 336 updates完整epoch，不按质量early-stop，实际完成数量见下文。每448步checkpoint后评完整Dev，按accuracy、四排列consistency、binary consistency、negation/correction、最低position/ID偏差排序，最早step仅作完全平局规则。

冻结身份：

- FREEZE.json: `33f40846ebeecb0c52204ea646262153d615e96ab747799676a4003376891394`
- TRAIN-FREEZE.json: `69d4c225b8acfc54d00d39ffb853f6c448ce8208fa517d7a390be476618a268a`
- ACQUISITION-FREEZE.json: `e15286761868892fc66b7ec2e1f69f9a7cb6cd8a98e000725b1221267c542570`
- train-config.yaml: `be535f18063b71b61ab885b6b6435d1f696f3b01ab4c08347026d5cebd2b0405`

## 修正版 Raw Dev baseline

| 指标 | Raw Dev |
|---|---:|
| semantic_accuracy | 58.16% |
| permutation_consistency | 11.81% |
| four_permutation_consistency | 11.81% |
| binary_consistency | 20.83% |
| negation_correction_accuracy | 57.64% |
| tool_vs_answer_accuracy | 46.88% |
| multi_intent_accuracy | 47.92% |
| contract_validity | 100.00% |

N=576，seed=144。原有permutation_consistency定义已是全部四排列一致，four_permutation_consistency是同义字段，不是第二套提高分数的定义。位置及ID分布见raw-dev-baseline.json，按二/三候选分层，非法输出保留在分母。

## 正式配置 corrected smoke

状态：passed，完成5/5 microsteps。

| Microstep | loss | wall s | gradient/adapter/optimizer finite | MLX peak GiB | RSS high-water GiB |
|---|---:|---:|---|---:|---:|
| 1 | 0.159091 | 15.158 | True | 3.432 | 1.173 |
| 2 | 0.056818 | 12.303 | True | 3.442 | 1.173 |
| 3 | 0.204545 | 8.117 | True | 3.442 | 1.173 |
| 4 | 0.068182 | 8.159 | True | 3.442 | 1.173 |
| 5 | 0.045455 | 10.175 | True | 3.442 | 1.173 |

RSS高水位与MLX GPU分配器均使用共享统一内存，不能相加，也不等同于系统总占用。父进程采样250ms保存RSS，worker硬退出时缺失的MLX指标标未知。smoke不作能力判断、不复用权重。

## 预注册一epoch learning curve（以实际完成状态为准）

已完成1161/2688 microsteps，145/336 optimizer updates。

| Step | loss window | Dev accuracy | 四排列一致 | binary一致 | neg/correction | tool/answer | multi-intent | max bias pp | validity | paired Δ accuracy pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 448 | 0.077415 | 74.13% | 40.97% | 54.17% | 69.44% | 63.54% | 60.42% | 21.88 | 100.00% | +15.97 |
| 896 | 0.037490 | 84.55% | 80.56% | 91.67% | 81.94% | 72.92% | 58.33% | 5.56 | 100.00% | +26.39 |

每个checkpoint都保留，paired比较使用同一576个实例的strict语义正确性，包含raw-only/trained-only/both-correct/both-wrong计数。排列相关性不作为独立样本证据。完整位置/ID分布、类别分母和raw输出另存JSON。

运行错误：

- train: `resource anomaly: macOS memory pressure critical (kern.memorystatus_vm_pressure_level=4); worker SIGTERM; no retry or configuration reduction`。停止，未降低配置或重试。

系统级只读检查记录到 `kern.memorystatus_vm_pressure_level=4`（critical），swap 3.482 GiB / 4.0 GiB；按资源异常停止规则向worker发SIGTERM，退出码−15。最后完整microstep=1161，更新=145。这些已完成步骤全部finite；没有检测到OOM、NaN/Inf、shape或截断错误。系统压力是整机指标，不能将全部swap归因于本训练。终止后压力level恢复1，swap约1.781GiB。

正式训练实际MLX peak 3.444 GiB，worker RSS高水位 1.920 GiB。单步wall time p50=10.718s，max=37.987s。5-step smoke通过没有证明整轮训练的系统资源余量足够。详细记录见resource-abort.json。

仅保留step448和896两个完整checkpoint；step1344/1792/2240/2688未完成。没有以部分learning curve冻结Dev-best，没有Train replay，没有加载Hidden样本进行评估，没有续训、缩配置或替换checkpoint。

## 七个结论问题

以下仅引用最后已完成的step896，**不是正式Dev-best或一epoch最终结果**。

1. **Raw → trained**：已观测Dev 58.16% → 84.55%，提升+26.39 pp。paired计数 `{"both_wrong": 52, "both_correct": 298, "raw_only_correct": 37, "trained_only_correct": 189}`。
2. **捷径是否消失**：Dev位置/ID最大份额偏差 39.24 → 5.56 pp，低于10pp；有去偏迹象，但不能据此证明捷径真正消失，缺乏冻结选模后的Hidden验证。
3. **排列同步提升**：Dev四排列一致 11.81% → 80.56%；binary 20.83% → 91.67%。A固定布局accuracy 49.31% → 84.03%。提升确实包含全部排列的稳定性，四排列一致仍未达90%。
4. **Train/Dev/Hidden gap**：Train未测，部分checkpoint Dev见上表，Hidden未测；Train−Dev及Dev−Hidden未知。
5. **规则还是模板/family记忆**：在family隔离Dev与反事实、排列评估上有学习信号，不能仅以topic/position/ID查表解释全部提升；没有完整epoch、Train replay与Hidden，尚不能区分完整task acquisition和残留模板/家族捷径。
6. **Hidden gate**：**NOT EVALUATED**，没有GO/NO-GO能力判定；Hidden零次推理，不以未测冒充失败或通过。
7. **0.8B容量足够？**：部分learning curve支持可学习性，但实验因资源异常未完成，不能支持所要求的完整容量命题；同样不能据此否定0.8B容量。

**结论边界：即使Hidden通过，也只能证明当前冻结合成Policy合同下的task-acquisition能力，不能直接外推真实生产泛化。** 数据是确定性合成标签，主题和操作词复用，未做独立人工盲审；有效泛化单元是80个模板家族，不能把3840排列当3840个独立语义问题。实验没有生产接入。

## 交付文件

- [raw-dev-baseline.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/raw-dev-baseline.json)
- [corrected-memory-smoke.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/corrected-memory-smoke.json)
- [train-log.jsonl](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/train-log.jsonl)
- [checkpoint-dev-evals.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/checkpoint-dev-evals.json)
- [train-replay.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/train-replay.json)
- [hidden-eval.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/hidden-eval.json)
- [resource-abort.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/resource-abort.json)
- [acquisition-integrity.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/acquisition-integrity.json)
pt、gold、评分函数、训练目标与Hidden gate哈希保持不变。执行入口为policy_sft_v0_acquisition.py；新增执行协议单独冻结，不修改旧scorer。只忽略与实验无关的macOS .DS_Store元数据。模型推理输入不包含gold/family元数据；raw首答严格解析、不修复、不重试、不用受约束解码。

正式配置：末8层，rank8，MLX直接scale16，dropout0，lr5e-5，batch1×accumulation8，max_seq_length384，checkpointing、mask_prompt；实际MLP和全/线性attention投影，不改模型结构。使用原生MLX-LM loss与compiled stateful accumulation；固定padding384，按原始长度mask，不截断，保持原有seed1807 shuffle完整epoch。

唯一原始模型对照仅评完整Dev。正式配置smoke只做5 microsteps，因此累计梯度但**0 optimizer update**；optimizer状态已初始化并检查finite，不声称这5步验证了Adam更新后的状态。正式训练另起干净模型、适配器、Adam和梯度累积；预注册2688 microsteps / 336 updates完整epoch，不按质量early-stop，实际完成数量见下文。每448步checkpoint后评完整Dev，按accuracy、四排列consistency、binary consistency、negation/correction、最低position/ID偏差排序，最早step仅作完全平局规则。

冻结身份：

- FREEZE.json: `33f40846ebeecb0c52204ea646262153d615e96ab747799676a4003376891394`
- TRAIN-FREEZE.json: `69d4c225b8acfc54d00d39ffb853f6c448ce8208fa517d7a390be476618a268a`
- ACQUISITION-FREEZE.json: `e15286761868892fc66b7ec2e1f69f9a7cb6cd8a98e000725b1221267c542570`
- train-config.yaml: `be535f18063b71b61ab885b6b6435d1f696f3b01ab4c08347026d5cebd2b0405`

## 修正版 Raw Dev baseline

| 指标 | Raw Dev |
|---|---:|
| semantic_accuracy | 58.16% |
| permutation_consistency | 11.81% |
| four_permutation_consistency | 11.81% |
| binary_consistency | 20.83% |
| negation_correction_accuracy | 57.64% |
| tool_vs_answer_accuracy | 46.88% |
| multi_intent_accuracy | 47.92% |
| contract_validity | 100.00% |

N=576，seed=144。原有permutation_consistency定义已是全部四排列一致，four_permutation_consistency是同义字段，不是第二套提高分数的定义。位置及ID分布见raw-dev-baseline.json，按二/三候选分层，非法输出保留在分母。

## 正式配置 corrected smoke

状态：passed，完成5/5 microsteps。

| Microstep | loss | wall s | gradient/adapter/optimizer finite | MLX peak GiB | RSS high-water GiB |
|---|---:|---:|---|---:|---:|
| 1 | 0.159091 | 15.158 | True | 3.432 | 1.173 |
| 2 | 0.056818 | 12.303 | True | 3.442 | 1.173 |
| 3 | 0.204545 | 8.117 | True | 3.442 | 1.173 |
| 4 | 0.068182 | 8.159 | True | 3.442 | 1.173 |
| 5 | 0.045455 | 10.175 | True | 3.442 | 1.173 |

RSS高水位与MLX GPU分配器均使用共享统一内存，不能相加，也不等同于系统总占用。父进程采样250ms保存RSS，worker硬退出时缺失的MLX指标标未知。smoke不作能力判断、不复用权重。

## 预注册一epoch learning curve（以实际完成状态为准）

已完成1161/2688 microsteps，145/336 optimizer updates。

| Step | loss window | Dev accuracy | 四排列一致 | binary一致 | neg/correction | tool/answer | multi-intent | max bias pp | validity | paired Δ accuracy pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 448 | 0.077415 | 74.13% | 40.97% | 54.17% | 69.44% | 63.54% | 60.42% | 21.88 | 100.00% | +15.97 |
| 896 | 0.037490 | 84.55% | 80.56% | 91.67% | 81.94% | 72.92% | 58.33% | 5.56 | 100.00% | +26.39 |

每个checkpoint都保留，paired比较使用同一576个实例的strict语义正确性，包含raw-only/trained-only/both-correct/both-wrong计数。排列相关性不作为独立样本证据。完整位置/ID分布、类别分母和raw输出另存JSON。

运行错误：

- train: `resource anomaly: macOS memory pressure critical (kern.memorystatus_vm_pressure_level=4); worker SIGTERM; no retry or configuration reduction`。停止，未降低配置或重试。

系统级只读检查记录到 `kern.memorystatus_vm_pressure_level=4`（critical），swap 3.482 GiB / 4.0 GiB；按资源异常停止规则向worker发SIGTERM，退出码−15。最后完整microstep=1161，更新=145。这些已完成步骤全部finite；没有检测到OOM、NaN/Inf、shape或截断错误。系统压力是整机指标，不能将全部swap归因于本训练。终止后压力level恢复1，swap约1.781GiB。

正式训练实际MLX peak 3.444 GiB，worker RSS高水位 1.920 GiB。单步wall time p50=10.718s，max=37.987s。5-step smoke通过没有证明整轮训练的系统资源余量足够。详细记录见resource-abort.json。

仅保留step448和896两个完整checkpoint；step1344/1792/2240/2688未完成。没有以部分learning curve冻结Dev-best，没有Train replay，没有加载Hidden样本进行评估，没有续训、缩配置或替换checkpoint。

## 七个结论问题

以下仅引用最后已完成的step896，**不是正式Dev-best或一epoch最终结果**。

1. **Raw → trained**：已观测Dev 58.16% → 84.55%，提升+26.39 pp。paired计数 `{"both_wrong": 52, "both_correct": 298, "raw_only_correct": 37, "trained_only_correct": 189}`。
2. **捷径是否消失**：Dev位置/ID最大份额偏差 39.24 → 5.56 pp，低于10pp；有去偏迹象，但不能据此证明捷径真正消失，缺乏冻结选模后的Hidden验证。
3. **排列同步提升**：Dev四排列一致 11.81% → 80.56%；binary 20.83% → 91.67%。A固定布局accuracy 49.31% → 84.03%。提升确实包含全部排列的稳定性，四排列一致仍未达90%。
4. **Train/Dev/Hidden gap**：Train未测，部分checkpoint Dev见上表，Hidden未测；Train−Dev及Dev−Hidden未知。
5. **规则还是模板/family记忆**：在family隔离Dev与反事实、排列评估上有学习信号，不能仅以topic/position/ID查表解释全部提升；没有完整epoch、Train replay与Hidden，尚不能区分完整task acquisition和残留模板/家族捷径。
6. **Hidden gate**：**NOT EVALUATED**，没有GO/NO-GO能力判定；Hidden零次推理，不以未测冒充失败或通过。
7. **0.8B容量足够？**：部分learning curve支持可学习性，但实验因资源异常未完成，不能支持所要求的完整容量命题；同样不能据此否定0.8B容量。

**结论边界：即使Hidden通过，也只能证明当前冻结合成Policy合同下的task-acquisition能力，不能直接外推真实生产泛化。** 数据是确定性合成标签，主题和操作词复用，未做独立人工盲审；有效泛化单元是80个模板家族，不能把3840排列当3840个独立语义问题。实验没有生产接入。

## 交付文件

- [raw-dev-baseline.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/raw-dev-baseline.json)
- [corrected-memory-smoke.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/corrected-memory-smoke.json)
- [train-log.jsonl](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/train-log.jsonl)
- [checkpoint-dev-evals.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/checkpoint-dev-evals.json)
- [train-replay.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/train-replay.json)
- [hidden-eval.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/hidden-eval.json)
- [resource-abort.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/resource-abort.json)
- [acquisition-integrity.json](/Users/jichengqian/Documents/ChatGPT/texa/docs/validation/policy-sft-v0-20261007/acquisition-integrity.json)
