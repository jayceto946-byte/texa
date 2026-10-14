# Policy-SFT-V0 Report

2026-10-07。**本轮因数据审计异常停止，未获得有效的容量结论。** 初版生成器使 topic 槽位高度关联 gold 动作；仅用 Train 标签做 topic-majority 即可达91.67%，不需要读用户请求。因此我主动中止这次无效训练，不把其loss或原始Dev对照当作语义学习证据。

没有发生OOM/NaN/Inf。旧正式run在58 microsteps / 7 optimizer updates停止，无checkpoint，无Hidden推理。旧数据、冻结合同、代码快照、原始输出和全部训练日志完整保存在同级 invalid-topic-label 目录，不覆盖、不删除、不混作修正数据的结果。修正依据仅来自Train结构审计，未使用Hidden模型结果。

## 已完成的修正数据

960 seed ×4排列=3840条chat JSONL，80个措辞家族。Train/Dev/Hidden为672/144/144 seed，即2688/576/576实例；整个模板家族和所有seed排列不跨split。覆盖tool-vs-answer、multi-intent、negation、correction、noisy wording、existing-data-vs-knowledge、tool distinction、quoted statement，二/三候选各一半。

现在同主题、同措辞模板、同候选集合/候选数有成对或三组有效请求，gold语义动作在组内均衡。候选内容和主题本身不能确定正确动作；必须根据request区分。所有split gold位置/ID严格分层平衡；Dev/Hidden的位置×ID联合格子完全相等，Train三候选格子相差至多1。

训练前主题查表上界（标签结构审计，不是模型评分）：train 36.61%, dev 38.89%, hidden 40.28%。

输入采用现有Runtime Policy IR，模型只见system/user输入，assistant为最小action_id JSON；seed/family/gold/order映射元数据不送模型。原简化Policy提示原文保持不变，没有prompt tuning。request_input在生产仅为Runtime forced singleton，另存12个控制fixture，不虚构no_action或多候选澄清。

## 修正数据 tokenizer

| Split | p50 | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| train | 340.0 | 357.0 | 358.0 | 365.0 | 371 |
| dev | 340.0 | 354.0 | 358.0 | 363.0 | 363 |
| hidden | 338.5 | 355.0 | 357.0 | 363.0 | 363 |

上限384由全量最大长度取整决定；0截断，candidate list/gold以及原生masking/generation prefix完整对齐。Hidden只做训练前长度和标签平衡检查，模型推理次数为0。

## 已实际运行的五步 smoke（归档输入）

原始5步为末4层MLP/rank4/batch1/checkpoint/Adam lr1e-5，最长384-token批次。反向成功，所有loss、gradient、adapter和optimizer状态finite。该硬件链路测量有效，但不是修正数据的smoke，也不是能力评测；memory-smoke.json以not_run明确区分并链接原始证据。

| Step | loss | wall seconds | MLX peak GiB | RSS high-water GiB |
|---|---:|---:|---:|---:|
| 1 | 2.052083 | 4.470 | 3.358 | 0.756 |
| 2 | 2.072917 | 3.322 | 3.365 | 0.756 |
| 3 | 1.916667 | 3.360 | 3.366 | 0.756 |
| 4 | 1.937500 | 3.314 | 3.366 | 0.756 |
| 5 | 1.708333 | 3.268 | 3.366 | 0.756 |

物理统一内存8 GiB。MLX active allocator峰值约3.366 GiB，高水位RSS约0.756 GiB；二者不能相加，也不代表已直接测得系统总统一内存。父进程另以250ms采样RSS，原始数据在归档监控JSON。

## 正式方案与未执行状态

train-config.yaml已建立：末8层、rank8、MLX直接scale16、dropout0、lr5e-5、batch1×accumulation8、完整长度384、checkpoint、mask_prompt，1epoch=2688 microsteps/336 updates。显式targets为MLP gate/up/down，全注意力q/k/v/o和实际linear_attn in_proj_qkv/z/a/b/out_proj；原始装配核实1,803,776个参数，不修改结构。每448 microsteps保留checkpoint并用完整Dev语义指标选模，之后同一checkpoint评完整Train，最后仅一次冻结Hidden。MLX scale直接乘BA，不误写为alpha/r。

修正版没有自动开启第二次训练。smoke/dev/hidden明确not_run；train-log记录停止与重建事件，真实旧5+58步日志留在归档。不存在可选择的checkpoint。Train、Dev、Hidden accuracy和两个gap均为null；不能将未测填成0%，也不能归因为0.8B容量不足。

预注册Hidden gate保留：accuracy>=85%、四排列consistency>=90%、binary consistency>=90%、negation/correction>=80%，候选数分层的预测位置/ID份额相对gold最大偏差<=10个百分点。指标定义、门槛、prompt、split、数据及配置均在训练前冻结；不按Hidden调参。

## 结论与完整性

**本轮只确认LoRA反向可运行；尚不能回答能否摆脱shortcut并学会语义选择。** 我修正并冻结了数据，按异常停止要求未继续训练。合成模板的主题槽位仍复用，标签未经独立人工盲审，未来通过也仅支持此合成合同下的容量可行，不能证明真实生产泛化。

既有模型文件未保存/修改，无下载、换Base或依赖安装；没有修改Runtime、旧Benchmark gold/scorer或其他任务。旧Benchmark/source release和既有raw的SHA256均未变化。准备与审计用venv310/Python3.10，GPU worker用既有已授权LM Studio Python3.11。完整spec、JSONL、metadata、tokenizer统计、配置和审计在本目录；无在后台继续运行的训练进程。
