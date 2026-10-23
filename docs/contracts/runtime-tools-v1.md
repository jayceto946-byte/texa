# Current Runtime 工具合同 v1（AUD-07）

日期：2026-10-23。本版本只固定当前工具schema、metadata与离线兼容边界，不批准生产启用Policy，不替代教材/模型质量评测。

## 两个独立版本

| 层 | 身份 | 权威与范围 |
|---|---|---|
| 历史数据集 | Runtime source `runtime-source/v0.1`，Observation wire `texa.runtime-policy/v0` | 原source pins、Registry digest、canonical-tools、fixtures与金标全部保留；只证明历史快照合同 |
| 当前工具合同 | `texa.runtime-tool-contracts/v1` | `evaluation/contracts/runtime-tools-v1.json` 及代码中的固定SHA-256；覆盖当前三种只读工具的完整schema、version/hash、权限、来源、副作用、timeout、provenance与幂等metadata |
| 当前有限基准 | `current-runtime-policy-tools/v1` | 运行当前Runtime和上述工具合同，使用临时存储/固定handler/答案替身；输出独立baseline身份、manifest hash及tool refs |

当前 `search_textbook` 为v3，schema hash为 `fd3d77dd5f4fded50db6ea66ba14cadc0335692f3554c3adda0b9f57579dd5b2`；历史工具为v1，hash仍是 `9c80910bbac8b194615ded8bca1b2554abfe03d200416941a9894b5b5adcaa2d`。不能用当前版本重写旧hash，亦不能把旧评测成绩表述为当前源码完整通过。

## 唯一批准的适配

`evaluation/runtime_tool_contracts.py` 仅被评测与测试调用，生产执行入口不使用它。旧合同先按冻结schema严格验证完整绑定参数，再将教材工具的 `{query, chapter}` 映射为 `{query, chapter, continuation: null}`。进度和习题工具采用严格恒等映射。返回对象独立复制，不修改旧样本、hash或金标。

非空continuation不能降为旧合同，不静默丢弃新状态；旧参数出现额外字段、类型错误或新schema/version/metadata未匹配固定manifest时拒绝。兼容schema投影只移除明确审核过的continuation与其$defs，并再次精确比较原输入/输出schema及原hash，不能泛化为“忽略新增字段”。当前manifest本身也固定字节hash；后续漂移必须新版本审阅，不能自动重新生成后当作批准。

当前RulePolicy仍只绑定空continuation，不新增续读候选或重试。v3的非空续读继续走既有工具执行路径：绑定冻结教材及索引版本，按Canonical IR单元/章节读取，在最终EvidencePack中保留来源；不触发新的全文检索。每次续读消耗既有工具预算，保留原8秒timeout与owner/run准入，不开额外循环。

## 发布与失败边界

当前离线基准不再仅按任务轨迹成功返回exit0：binding_errors、forbidden_leaks必须为0，真实模型调用也必须为0。已有测试以“全部任务成功但绑定/候选/离线条件失败”验证CLI返回失败，防止绿灯掩盖合同问题。

回归包括当前metadata/schema/manifest漂移、旧source字节损坏、旧ref拒绝、非空续读不可降级，真实临时IR上的异教材/旧索引/错误canonical hash/unit/block，以及真实Runtime续读预算。这里的pointer校验覆盖版本、范围和结构位置，不把它当成签名令牌或宣称已证明所有可能伪造都被阻断。

生产工具实现、Policy开关、模型profile、预算、数据结构与正式教材均未修改。完整结果、历史冻结390文件对照、命令与限制见 [AUD-07验证记录](../qa/aud-07-contracts-2026-10-23/README.md)。
