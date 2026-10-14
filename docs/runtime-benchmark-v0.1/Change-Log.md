# Runtime Benchmark V0 → V0.1 Change Log

2026-10-06。本次在原交付上做测量政策与实施范围修订；未改原300 cases、gold、schemas、prompts、scorer或FREEZE，未改生产代码。交付为 [Spec V0.1](Runtime-Benchmark-Spec-V0.1.md)、[Minimal Harness Plan V0.1](Minimal-Harness-Implementation-Plan-V0.1.md)，附逐case分类和sanity记录。

| 设计项 | 处置 | 原因 / V0.1 结果 |
|---|---|---|
| Runtime源码→语义接口→benchmark | 保留 | 不用方便测量的新IR替代真实责任边界 |
| frozen gold、strict scorer、raw首答 | 保留 | 不因精简降低语义真实性或抬分；原 official report 不动 |
| ModelAdapter、一次generation、无retry/fallback | 保留 | 同数据可横比8bit/4bit/BF16，能追溯首答 |
| 200 semantic同权总体主成绩 | 删除其主成绩地位 | 161 primary、39 secondary；100 control独立，case级标签在外部manifest |
| 原 `primary_semantic_without_upstream_conflicts` | 保留原输出，废止其主分解释 | 全集198仍混有secondary；V0.1显式按161重聚合，不能覆盖原字段 |
| Semantic recoverability | 新增独立诊断 | 仅移除外部包装恢复唯一完整JSON，不修schema、不挑gold；S/F/T/U分桶防止将无法判断算语义错误 |
| train/dev/test/hidden provenance | 保留 | 首次untouched可报semantic_all200，仍按split报告；不称盲测或held-out |
| dev调参→test最终评估主流程 | 替换 | P1独立smoke，P2 primary，P3只补secondary；避免首个foundation baseline先被调优 |
| 人工逐条adjudication/review workflow | 删除当前必需项 | internal screening不需平台；human_adjudicated=false；可独立模型交叉检查，分歧隔离、改gold另发版本 |
| 教材/历史reference覆盖暗示 | 更正并列gap | Policy没有search_textbook；primary understanding没有reference/clarify正例，旧resolver不能顶替 |
| 固定95%/生产接管阈值 | 不采用 | 约80%和可训练错误可能值得投入，按task与缺口判断，不证明上线安全 |
| 模型ID、真实量化、prompt/generation、benchmark身份 | 保留并合并记录 | run.json+requests/raw足以支持本机实验与离线重评分 |
| 每shard SHA256、tokenizer全文件hash | 降为future extension | 非当前筛选所需，不影响原benchmark已有FREEZE校验 |
| input-bundle强隔离、独立权限scorer/inference、socket blocking、PYTHONDONTWRITEBYTECODE安全措施 | 删除V0实施项；仅未来确有隔离需求再评估 | 本机内部实验维持prompt不含gold的数据边界即可 |
| crash tail recovery、复杂resume/interrupted语义 | 降为future extension | 逐条保存，错误终止并标incomplete；新run不掩盖旧失败 |
| 完整atomic artifacts、artifact signing、dirty patch provenance链 | 降为future extension | 不为内部筛选建设发布平台；仍拒覆盖输出目录 |
| sophisticated per-case RNG、环境forensics | 删除当前要求 | 固定顺序、一次seed与有效配置足够；不承诺bitwise复现 |
| TTFT、decode-only、allocator精细核算 | 降为optional | load、p50/p95、实际tokens/sec、可靠peak memory即可，缺测注明 |
| 分类F1、context-set指标、control基础设施 | 降为optional/future | task准确率、severity、失败语料更直接服务当前判断 |
| P0–P4与多进程CLI流程 | 压缩为P0–P3 | sanity→真实8bit单例→primary→semantic_all，停止于screening |
| LoRA、shadow、生产接管、dashboard/公开平台 | 保持排除 | 先回答foundation值不值得训练，本轮不继续扩展 |

## 本次实测与未做事项

使用项目 venv310 / Python 3.10.21：271个冻结文件校验通过；300个input/gold合同及gold round-trip通过；原10个scorer mutation检查通过；216个源码/规范/测试快照与工作树一致（文档修订前）。60条understanding重新生成request、重算gate，均匹配原数据；41条eligible，19条non-gated。分类清单覆盖300个唯一ID，primary/secondary/control为161/39/100。

记录见 [scope audit](scope-audit.json)、[frozen sanity](frozen-sanity.json)、[case scope manifest](case-scope-manifest.json)。Gold round-trip是评分器自检，不是gold语义正确率或Qwen成绩。独立模型语义交叉审核尚未做；没有人工裁决，不伪造该状态。

未下载或运行Qwen，未实现recoverability parser/MLX Harness，未开展LoRA或业务/Electron验收。因此当前交付回答的是“该怎样缩小范围并正确测量”，模型是否值得训练要由后续P2/P3真实结果回答。

## 后续实施：2026-10-06

Minimal Harness 已完成，并复用 LM Studio 现有本地 snapshot 实测 P0–P3；无原包/生产 Runtime 修改。实施与首次结果见 [Harness 使用说明](Harness-Usage.md)、[Screening 记录](Screening-Results-2026-10-06.md)。上述“未实现/未运行”描述保留为原设计交付的历史状态，不代表后续实施结果。
