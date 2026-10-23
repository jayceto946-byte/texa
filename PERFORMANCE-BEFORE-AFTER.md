# Texa 性能与可靠性 Before / After

日期：2026-10-23。只报告本轮实际测量；合成/替身结果不等同于真实教材、网络、模型或安装包性能。问题与状态见 [审计](PERFORMANCE-RELIABILITY-AUDIT.md)，改动见 [实施](OPTIMIZATION-IMPLEMENTATION-REPORT.md)。

## 环境和可比性

- macOS 26.5.1（25F80）、arm64、Apple A18 Pro，6逻辑核、8 GiB；Node24.22.0、npm11.19.1、Python3.10.21（venv310）、Electron37.10.3、实际安装Vite8.0.16、Chroma1.5.9。
- 起点分支Texa_MacOS，HEAD `140255ad180b8076c830e5600ca4297942eee105`，另有12个既有修改文件；before应用构建来自实际初始工作树。微基准旧lexical/两个store起点没有额外差异，可直接从该Git对象加载。
- 使用既有依赖和本地ONNX资产，不下载模型。生产renderer生成到两个独立临时目录，不清空线上`frontend/dist`；SQLite/Chroma用临时数据。没有用正式学习记录作为实验数据。
- lexical两实现同一进程、同一输入、交替执行9轮；最终Electron前后依次运行且无其他审计压测并行。OS缓存和其他系统进程没有完全控制，启动不可作严格冷启动比较。
- 原始文件均在 `docs/qa/performance-reliability-2026-10-23/`。`electron-*-initial`、`local-benchmark.log`和`runtime-contention.json`为探索记录，部分有并行负载或首次import；不混用为最终配对结果。保留以便审查选择依据。
- p95为样本最近秩，不是置信区间；9轮下p95基本等于最大值。没有统计显著性或外推全用户性能的声明。

## 可测量的修复效果

### 词法检索：单次查询局部复用

600/3000片段、84重复标题，合成中文定义/列举/公式/表格。每个大小对8个查询和2个章节范围检查完整返回对象，共32组精确相等。下列每行9轮；结果、元数据与排序不变。

| 片段/查询 | Before中位 ms | After中位 ms | 中位减少 | Before p95 ms | After p95 ms |
|---|---:|---:|---:|---:|---:|
| 600 / 定义 | 34.56 | 25.46 | 26.3% | 40.24 | 38.48 |
| 600 / 列举 | 46.73 | 39.38 | 15.7% | 94.46 | 74.36 |
| 3000 / 定义 | 186.22 | 137.33 | 26.3% | 189.93 | 141.75 |
| 3000 / 列举 | 257.28 | 207.15 | 19.5% | 261.75 | 213.54 |

证据：`local-benchmark.json`及`local-benchmark-final.log`。优化降低重复标题的CPU成本；正文tokenization和语料扫描仍存在。真实教材的标题重复率、文长和候选范围不同，不能推断整体问答提速同样比例。

### SSE锁竞争：事件循环响应

真实临时SQLite持有`BEGIN IMMEDIATE`300ms，替身执行器只产生固定output，生产`stream_run`照常取snapshot与delta。独立asyncio任务每5ms唤醒；读取前已完成registry初始化。

| 指标 | Before | After |
|---|---:|---:|
| 心跳最长间隔 | 380.33 ms | 17.00 ms |
| 输出chunk数 | 3 | 3 |
| worker错误 | 0 | 0 |

证据：`runtime-contention-before.json`和`runtime-contention-after.json`。这是单次受控故障注入；证明原同步锁阻塞事件循环，以及移到线程池后的响应改善。不是全站p95，也不说明SQLite写锁等待本身缩短。新`--baseline`可在不切换工作树的情况下复现旧binding；另存`runtime-reproduce-*.json`作为重现检查，不覆盖最初配对数据。

### 可靠性见证

| 检查 | Before | After | 限制 |
|---|---|---|---|
| Electron earlier迟到返回 | A消息进入B | 忽略 | 内存HTTP夹具，真实生产renderer |
| Electron later迟到返回 | A消息进入B且切回A | 忽略 | 未把此问题声称为持久化数据损坏 |
| 失败数学验证 | pack sufficient=True | False且缺verified_math | 最终答案验证另有保护，未证实错误最终答案被verified |
| 两类store，100次退出后可用连接 | 各100 | 各0 | 保持连接引用、GC关闭，测确定关闭，不是正常进程无限泄漏证明 |
| ExerciseBank上述100次耗时 | 10.35 ms | 32.87 ms | 关闭有成本，不声称提速 |
| MistakeBook上述100次耗时 | 11.18 ms | 30.59 ms | 确定性释放优先 |

证据：`witnesses-before.log`、`final-regressions.log`、`local-benchmark.json`、`electron-*/results.json`。UI修复后另有正常双向分页、当前消息去重和同ID重载失效检查。

## 未测出明确收益的桌面指标

同一Electron壳、两套干净production renderer、固定内存HTTP响应、新建临时userData。测量从automation调用到composer/目标会话文本可见，含Playwright调度开销；没有真实后端启动或模型请求。

| 指标 | Before | After | 结论 |
|---|---:|---:|---|
| launch到composer，1次 | 2706.36 ms | 1724.93 ms | 样本不足、存在顺序/缓存影响；不宣称启动提速 |
| reload，5次中位 | 881.36 ms | 925.77 ms | 未测出收益，略慢约5%；未隔离为代码回归 |
| 切换会话，20次中位 | 25.77 ms | 25.93 ms | 基本相同，未测出提速 |
| 切换会话，20次最大 | 31.71 ms | 31.20 ms | 仅短时样本 |
| renderer工作集：切换前→20次后 | 328880→342784 KiB | 305056→316432 KiB | 不同进程内存快照，不能宣称节省内存/证明无泄漏 |
| 主进程工作集：前→后 | 140288→140656 KiB | 141120→141584 KiB | 短时增长不代表长时趋势 |
| 干净输出总字节 | 42,844,349 | 42,845,254 | +905 bytes，未优化体积 |
| 干净JS总字节 | 2,143,160 | 2,144,065 | 都为55文件；不含实际传输压缩推断 |

CPU与GPU/Utility内存原始快照留在JSON；瞬时CPU百分比不作为长期负载或节能证据。最终Electron前12项验证通过，三尺寸1280×820、1024×768、760×820，截图保留。未改变排版、颜色或交互设计。

现有dist为112,717,031字节/3921文件，独立干净输出约42.84MB/395文件。此差异支持发布目录受历史产物影响（AUD-09），但没有实际安装包before/after，也没有删除旧hash资源。

## 新建的组件基线（没有生产优化对照）

### 真实本地ONNX Embedding

使用既有`benchmark_phase3_embedding.py`及冻结500文本，FP32；交互线程2/1，摄取3/1，batch16。先交互预热5次、摄取预热一批；交互20次、摄取5批、摄取并发查询20次。执行是本地离线推理，无付费API。

| 指标 | 本次值 | Before/After |
|---|---:|---|
| 交互query中位 / p95 | 2.03 / 2.20 ms | N/A，未调参 |
| 摄取500文本中位 | 49,449.85 ms | N/A |
| 摄取吞吐 | 10.11文本/秒 | N/A |
| 并发query中位 / p95 | 4.45 / 10.02 ms | N/A |
| 并发摄取吞吐 | 10.46文本/秒 | N/A |

**现有脚本FAIL（exit1）**：`ingestion_gte_20_texts_per_second`失败，其余4门槛通过；历史Torch比较值来自既有脚本，并非本机当前Torch对照。没有降低门槛。详见`embedding-baseline.json`和`.log`。

原脚本在Darwin将ru_maxrss错误乘1024；原始interactive峰值234448 MiB、ingestion960544 MiB不能用作实际内存。本轮修复单位，按同一原始样本推导的lifetime峰值分别228.95/938.03 MiB；`embedding-rss-correction.json`明确记录换算，不是重新跑完整推理。修正helper独立进程返回约27.67 MiB，仅证明读数尺度合理，不和加载模型后的峰值比较。POSIX线程字段只统计Python线程，不能推断ONNX native线程数量。

### 真实隔离Chroma

Chroma1.5.9临时持久目录，500个固定随机种子的归一化512D向量，top10；每个查询验证自身向量首位。5次预热后20次热查询。

- 初始化110.17ms，写入50.54ms，查询中位0.2245ms/p950.2393ms。
- 数据：`chroma-baseline.json`。不包括Embedding、文本解析、混合召回、rerank和EvidencePack；不能用于宣称真实教材召回延迟或质量。

## 测试结果与失败透明度

| 集合 | Before | After |
|---|---|---|
| React | 251 passed | 251 passed |
| Electron单元 | 53 passed（允许回环监听后） | 壳源未改；同轮回归有效 |
| 后端首轮完整 | 2131 passed / 4 failed，81.35s | 2138 passed / 3 failed，88.49s |
| 后端最终完整（含2个RSS新例） | — | 2139 passed / 4 failed，86.94s |
| 收尾含其他任务新增用例的当前树 | — | 2163 passed / 3 failed，91.80s；源码稳定 |
| 审计新增回归 | 原见证4失败 | 7 passed |
| lint / TypeScript / Vite | 构建通过 | lint与构建通过 |

3项持续失败为Policy冻结schema/model绑定。原native工具协议错误断言已修正。最终额外失败来自既有搁置的`test_network_work_is_cancelled_on_deadline_or_stop[True]`（搁置模块）：返回取消结果约35ms后，测试断言的finally标记为空；前两轮完整套件此项通过，根因未判定。遵守搁置边界，本轮不修改或开展该功能专项实验，也不将它隐藏成全量通过。详见`backend-final.log`。该项作为范围外既有工作树测试观察记录，不计入14项审计修复清单，也不推定由本次修改导致。

套件数量变化来自新增7个审计用例（其中最后新增2个）和协议测试增加1个参数case；时间仅为测试运行耗时，不能充当产品性能指标。

## 复现命令

从仓库根目录执行。无需安装新依赖；Electron自动化需要已有Playwright路径及回环端口18192/18193可用。各性能场景应串行，避免与整套测试/模型工作争抢CPU。重跑会覆盖同名结果，审阅前可另存原结果。

```sh
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q
venv310/bin/python docs/qa/performance-reliability-2026-10-23/run_pytest.py -q tests/test_audit_regressions.py tests/test_tool_calling_audit.py
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix desktop test
npm --prefix frontend run build -- --outDir /private/tmp/texa-audit-build-after

venv310/bin/python scripts/benchmark-audit-local.py
venv310/bin/python scripts/audit-runtime-contention.py --baseline
venv310/bin/python scripts/audit-runtime-contention.py
venv310/bin/python scripts/benchmark-audit-chroma.py

NODE_PATH=/Users/jichengqian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/qa-audit-history-electron.mjs before /private/tmp/texa-audit-build-before
NODE_PATH=/Users/jichengqian/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules node scripts/qa-audit-history-electron.mjs after /private/tmp/texa-audit-build-after

ENV_PATH=/dev/null DATA_DIR=/private/tmp/texa-audit-embedding-data TEXA_EMBEDDING_ASSET_DIR="$PWD/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1" HF_HUB_OFFLINE=1 ANONYMIZED_TELEMETRY=False venv310/bin/python scripts/benchmark_phase3_embedding.py --output docs/qa/performance-reliability-2026-10-23/embedding-baseline.json
```

`/private/tmp/texa-audit-build-before`是修改前本轮已生成的构建，未永久归档整个二进制目录。目录丢失后应在独立副本恢复初始工作树再构建，不能在当前修复代码上运行`before`就称为旧版本。不得用整文件回退共享工作树来重现，特别是包含搁置改动的文件。上述SSE的`--baseline`只替换模块代码，其他依赖取当前工作树；原始before则是在本次修改前实际运行。

## N/A矩阵与发布含义

| 指标/场景 | 状态与原因 |
|---|---|
| 完整桌面冷启动，含真实后端与模型初始化 | N/A；只有renderer+夹具启动 |
| 正式教材端到端检索与大书导入 | N/A；不触碰生产索引；只做合成lexical/Chroma和冻结embedding组件测量 |
| OCR/MinerU长PDF | N/A；未运行外部OCR服务/人工校对 |
| 真实Agent端到端、Token与工具次数统计 | N/A；未获得本轮付费模型/数据出境许可；协议替身不充当质量/费用评测 |
| 实际模型取消与远端供应商工作停止 | N/A；本地停止、run fence、恢复和SSE顺序通过离线回归 |
| 数小时CPU/内存趋势、多设备并发 | N/A；只有短时Electron快照和受控SQLite竞争 |
| 真实手机断网/重连、tailnet与锁屏 | N/A；仅本地Remote合同测试 |
| Windows、安装包升级/回滚 | N/A；本次macOS源运行环境 |
| 真实教学正确率/任务完成率 | N/A；没有减少事实、证据或校验能力，离线通过不等于模型准确率 |

现有Policy测试与批量Embedding基准门槛未通过，加上最后一轮搁置测试失败，当前不能宣称全部发布验证通过。没有测到收益的项目如实保留，不以删除功能、降低门槛或移除错误处理换取漂亮数据。

## 收尾期间的其他工作树改动

收尾时检测到另一组图片识别恢复/错题API修改：`backend/api/mistakes.py`、`backend/services/multimodal_bridge.py`、`tests/test_mistakes_api.py`、新`tests/test_visual_recognition_recovery.py`及独立patch_notes条目。它们不属于本轮7项修复，已原样保留；没有把其他任务成果计入本次性能收益。为避免用旧结果代表新树，另跑当前工作树完整测试，记录在`docs/qa/performance-reliability-2026-10-23/backend-current-tree.log`，运行前后源码哈希核对记录在同目录。原审计各轮日志和样本不覆盖。

此次当前工作树补跑为 **2163 passed / 3 failed，91.80秒**，仍为同3项Policy合同失败；此前那项搁置取消测试此次通过，保留其失败观察且不认定根因。运行前后源码哈希一致（`test-source-stability.json`）；新增用例属于另一任务，不能计入本轮修复数量。其他任务的暂存操作亦不属于本轮；本任务没有暂存、提交或推送。

## AUD-09 后续：发布资源输入隔离

两次真实 Vite 构建均为 395 文件 / 42,845,254 bytes；各自作为最小真实 PyInstaller 程序的 `frontend/dist` 数据源，冻结后文件清单和 SHA-256 逐项一致，探针可启动。原服务 dist 的 3,921 文件 / 112,717,031 bytes 全量哈希不变。macOS 脚本替身工具回归另验证连续两版、路径含空格及前/后端失败清理。证据见 `docs/qa/aud-09-release-2026-10-23/`。

这是打包资源输入验证，不是完整 Texa 安装包 before/after；不能据此推断压缩包减少的字节、构建耗时或升级成功率。原审计最终失败日志保留本地，因包含范围外 traceback，提交中以 `docs/qa/performance-reliability-2026-10-23/backend-final-summary.md` 记录 hash、计数与失败摘要；不隐去原失败结论。

后续工作树全量2166通过/3失败。实际暂存源码另行导出验证：定点后端31、前端249、真实Electron12项通过，lint及TypeScript/Vite生产构建通过；工作树251项含其他未提交用例。新Electron数据只作功能回归，不与原审计样本拼接为性能提升。
