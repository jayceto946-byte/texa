# Policy-SFT-V0

2026-10-07。唯一问题：既有 Qwen3.5-0.8B MLX 8bit 是否能以少量 SFT 学会语义候选选择，并摆脱位置/ID 捷径。离线实验不修改 Runtime、不执行工具、不下载模型、不切 Base、不涉及其他模型任务。

## 数据与标签

960 个合成 semantic seed，80 个措辞模板家族，每家族 12 个反事实语义实例，每 seed 四个候选变体，共 3840 实例。Train/Dev/Hidden 为 672/144/144 seed（2688/576/576 实例），按整个措辞家族先分配，之后才派生主题和排列。相同 seed、模板及其全部排列不跨 split。八个类别：tool-vs-answer、multi-intent、negation、correction、noisy wording、existing-data-vs-knowledge、tool distinction、quoted statement。

模型数据只含 messages，assistant content 严格为 `{"action_id":"候选ID"}`。元数据单独保存 seed_id、semantic_family、family_id、gold_semantic_action、surface_variant、candidate_order、action_id_mapping、split 与 gold_basis；这些字段不送模型。Gold 来自显式有效操作、撤回/否定/先后/引用语义的确定性合成配方，不使用旧 Benchmark 的 gold，不声称人工金标。seed 的真正独立性低于种子数量：80 个模板家族才是更保守的泛化单元，topic 槽位复用必须在报告披露。

每 seed：A 基础排列、B 仅换顺序、C 仅换 ID、D 同时更换。候选内容/参数及请求不变，标签由稳定语义候选身份重新映射。二候选和三候选各占一半。各 split 在候选数分层内 gold 位置及 ID 严格均衡；Dev/Hidden 的位置×ID 联合分布也严格均衡，Train 三候选联合格子相差至多 1。

当前 Runtime IR 支持 generate_answer/call_tool/request_input，无 no_action。生产投影在 blocking missing_inputs 时仅产生一个 request_input，由 Runtime 强制选择、不调用 Policy；所以另存 12 个 gate controls，不虚构多候选澄清竞争，也不混入 SFT 或语义选择分母。本实验允许候选集重排作为去偏压力测试，不表示修改生产候选投影。

使用现有 `exposed-dev-minimal-existing-fields/2026-10-06/1` 的 Policy system prompt 原文，Train/Dev/Hidden/原始模型对照保持一致。无 prompt 搜索、无 constrained decoding、无重试、无答案修复、无 Rule 仲裁。模型只生成 raw JSON；解码 greedy、thinking=false、最多 64 个新 token。输入候选存在性及 strict JSON 用现有 Policy parse_decision 验证。

## 反捷径审计与本轮停止状态

初版生成器按 topic 槽位确定 gold，仅用 Train 标签做 topic-majority 即达91.67%，足以使容量结论失真。发现后主动停止，完整保留于同级 invalid-topic-label 目录；未读取任何旧 Hidden 模型结果，也未产生旧 Hidden 推理。旧正式 run 完成58 microsteps / 7 updates，无checkpoint；旧五步smoke反向通过，但不复用其权重或当作修正数据的训练结果。

本修正版按同主题、同措辞家族、同候选集合及候选数构造两种/三种相反有效请求，使所有可用gold语义候选在条件组内均衡。新增训练前结构门槛：family/topic/candidate-set条件下至少两个gold、各gold计数相等；topic-only label-majority上界<=55%。这些是预注册数据结构审计，不是Hidden模型成绩。不能仅平衡位置/ID而忽略候选内容或主题标签捷径。

修正版没有开始新的smoke或正式训练。memory-smoke.json为not_run并链接旧测量；train-log.jsonl只记录停止与重建事件，旧5+58步日志留在归档。Dev/Hidden为not_run/null，不能回答容量问题。此轮按“异常停止报告”结束执行，不自动继续第二次训练，不自动缩配置。

## 冻结、tokenizer 与 smoke

FREEZE.json 在训练前绑定数据、split、prompt 和 gate，TRAIN-FREEZE.json 绑定 token 统计与配置；同时保存旧 Benchmark/scorer/结果文件 SHA256。Hidden 仅允许训练前统计长度，不允许跑原始模型 Hidden 或用于调参。Dev 最优 checkpoint 路径/hash 先落盘，之后一次性 Hidden 推理，不依据 Hidden 重跑或改配置。

tokenizer 对最终全部实例（包括模板控制 token）计算 p50/p90/p95/p99/max，并核对原生 ChatDataset 的 masking 与 generation prefix 对齐。max_seq_length 为全部完整实例的最大长度向上取整至 32 倍数；不截断、不按百分位丢尾部。candidate list 与 assistant gold 必须完整保留。

仅一次 5 步 smoke：末 4 层 MLP、rank4、scale8、物理 batch1、gradient checkpoint、Adam lr1e-5。选最长的 5 个不同 Train seed，验证真实反向、loss/gradient/adapter/optimizer 的 finite、实际 RSS 和 MLX peak、每步同步 wall time。无 smoke checkpoint 复用，不据 smoke loss 判断能力。任一异常/OOM/硬退出停止，不缩小配置重试，不进入正式训练。父进程每 250ms 监测 RSS，硬退出时 MLX peak 可能无法读取，必须标为缺失。

## 条件性正式训练

smoke 正常才启动。重新加载原始 8bit 底座：末 8 层、rank8、MLX scale16、dropout0、lr5e-5、物理 batch1、梯度累积8（effective batch8）、checkpointing、mask_prompt。明确选择 MLP 三投影、全注意力 q/k/v/o 投影，以及线性注意力 in_proj_qkv/z/a/b/out_proj；不存在的模块不伪造，实际逐层目标清单另存。MLX 的 scale 直接乘 BA，不是 Hugging Face alpha/r；配置不混淆二者。

固定一次完整 shuffled epoch，共 2688 microsteps / 336 optimizer updates。iters 在本版 MLX-LM 中表示 microstep，不将累积步误算成 optimizer update。独立 instrumented loop 复用 mlx-lm 的 ChatDataset、default_loss、LoRA 转换与 grad_checkpoint；只增加 finite/memory/time 日志和语义评估，不修改模型结构或安装包。每 448 microsteps 保留一个 checkpoint，并在完整 Dev permutation set 上评估，不以训练 loss 排名。以 Dev semantic accuracy 最大、consistency 次之、最早 checkpoint 再次之选择。隐藏评估前对同一 checkpoint 计算完整 Train accuracy。

原始模型只在 Dev 上做一次冻结 prompt 对照，用于区分专项训练增益；不以此修改配置。

## 指标与预注册 gate

semantic accuracy 是实例级 strict-valid 且稳定语义候选正确的比例，非法/缺失计错。permutation consistency 是 seed 的全部四个 valid 预测选同一语义候选比例，稳定错误也可一致，因此和 accuracy/all-correct 一起报告。binary consistency 为二候选 seed 的同样指标；three-variant all-correct 单独看 A/B/C，four-variant all-correct 含 D。按类别报告 tool-vs-answer、multi-intent、negation/correction 等正确率及分母。报告候选数分层的位置和 ID 选择直方图，避免三候选整体比例被二候选污染。

Hidden gate：semantic accuracy >=85%；permutation consistency >=90%；binary consistency >=90%；negation/correction accuracy >=80%；每个候选数分层中，预测位置/ID 份额相对均衡 gold 份额的最大绝对偏差 <=10 个百分点。非法输出留在分母。该偏差门槛训练前固定，用以操作化“无明显 bias”。所有阈值同时通过才 go。

报告同一 dev-selected checkpoint 的 Train/Dev/Hidden accuracy、Train-Dev gap、Dev-Hidden gap；指标按 seed/family 分层，不把排列当成独立样本。Train 高而 Hidden 低支持模板过拟合；均低仅说明本次配置未学会；Hidden 通过支持此合成合同下容量可行，不证明真实生产或开放措辞泛化，更不能证明所有 raw 模型缺陷只有训练不足。

## 环境与产物

准备/结构验证使用 Texa venv310/Python3.10；既有 MLX worker 使用已授权的 LM Studio Python3.11、mlx0.32.0、mlx-lm0.31.3、transformers5.14.1。无环境重装或项目依赖更改。数据/统计/配置/raw/适配器全部隔离在本目录，不接生产。

必须产物：本 Spec、tokenizer-stats.json、memory-smoke.json、train-config.yaml、train-log.jsonl、dev-eval.json、hidden-eval.json、Policy-SFT-V0-Report.md。smoke 阻断时正式 train/dev/hidden 状态明确为 not_run，不以 0% 冒充模型结果。
