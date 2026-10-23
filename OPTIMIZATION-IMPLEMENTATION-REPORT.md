# Texa 优化实施报告

日期：2026-10-23。以当前 `Texa_MacOS` 工作树为基础；起点 HEAD `140255ad180b8076c830e5600ca4297942eee105`。完整问题及优先级见 [审计报告](PERFORMANCE-RELIABILITY-AUDIT.md)，数据与命令见 [性能对照](PERFORMANCE-BEFORE-AFTER.md)。

## 实际完成

共14项发现，原审计修复7项；AUD-09、AUD-07 后续修复后共9项：P1三项、P2六项。实现保持公开HTTP合同、数据库/索引结构、模型配置、工具预算及教学事实边界。未安装依赖、迁移数据、清理正式数据、重新构建正式索引或发布安装包。

| ID | 修改文件 | 设计理由与结果 |
|---|---|---|
| AUD-01 | `frontend/src/contexts/ChatContext.tsx`、`frontend/src/pages/ChatPage.tsx` | 捕获会话读取身份，替换同ID也失效；取消旧请求并拒绝迟到响应。后续页对当前消息合并，不再通过loadConversation取消新流。纯state updater，cursor绑定会话。Electron复现前后验证 |
| AUD-02 | `backend/services/tool_orchestration.py` | bool后置条件必须为真；数值0仍合法。失败数学校验不再计入满足项。没有修改数学结果、验证算法、工具权限或教学输出 |
| AUD-03 | `backend/services/agent_runtime/chat_binding.py` | 把锁内snapshot与delta drain整体交给已有AnyIO线程池；保持原子性、序号及owner fence，消除同步等待阻塞ASGI loop。没有改Agent选路或核心决策 |
| AUD-04 | `memory/mistake_book.py`、`memory/exercise_bank.py` | 管理私有连接上下文：成功提交、异常回滚、finally关闭；pragma失败同样关闭。已检查两模块调用点，不全库替换其他raw connection工厂 |
| AUD-05 | `ingestion/lexical_index.py` | 复用单次search内相同标题的特征，移出不随chunk变化的query计数。无跨请求缓存或失效风险；32组完整返回结果与旧算法精确一致 |
| AUD-06 | `tests/test_tool_calling_audit.py` | 原生协议测试区分重复/不同表达式：真实执行1/2次，仍保持3次模型步骤和两次正确ToolMessage配对。保留并增强断言，未改生产去重行为 |
| AUD-07 | `evaluation/runtime_tool_contracts.py`、独立当前manifest、Runtime基准及相关测试 | 保留历史快照与金标，固定当前v3合同；旧参数显式加空continuation，非空续读不可降级，独立基准CLI检查绑定与候选；不启用Policy |
| AUD-09 | `scripts/build-desktop-backend-macos.sh`、`scripts/build-desktop-backend.ps1` | 每次创建独立 staging，Vite 只写新目录，PyInstaller 只收录当版资源；退出清理 staging，服务 dist 与旧手机资源保留。两版真实 Vite + 最小 PyInstaller 包清单/哈希一致，详见后续验收记录 |
| AUD-13 | `evaluation/embedding_backend/phase1_worker.py` | 按Darwin/Linux换算ru_maxrss；仅修正评测数值，不宣称生产RSS下降 |

## 验证与证据

所有证据位于 `docs/qa/performance-reliability-2026-10-23/`。后端通过隔离runner运行，不加载开发者.env；数据、SQLite和配置指向临时目录。套件主解释器禁止非回环socket连接，并移除API凭证相关环境变量；这是测试隔离措施，不是子进程网络防火墙。

| 检查 | 结果与限制 |
|---|---|
| Python完整基线 | 2131 passed / 4 failed，81.35秒 |
| 修复后的第一轮完整套件 | 2138 passed / 3 failed，88.49秒；尚未包含最后新增的两个RSS单位测试 |
| 最终完整套件 | 2139 passed / 4 failed，86.94秒；3项Policy持续失败+1项既有搁置取消测试本轮失败，详见 `backend-final.log`，不隐藏/跳过 |
| 含其他任务改动的当前树补跑 | 2163 passed / 3 failed，91.80秒；3项Policy失败；测试前后源码哈希一致 |
| 新增针对性回归 | `tests/test_audit_regressions.py` 7 passed：连接提交/回滚/关闭×2、失败布尔值、数值0、SSE线程与排序、RSS平台单位×2 |
| 其他针对性集合 | storage/tool/lexical 94 passed；native协议42 passed；stream/取消/恢复93 passed，集合有重叠，不相加当独立测试数 |
| React | 53文件251项通过；ESLint和TypeScript/Vite生产构建通过 |
| Electron壳 | 53项通过。沙箱首次监听127.0.0.1出现EPERM，允许回环监听后通过；不是产品测试失败 |
| 实际Electron | 生产renderer+内存HTTP夹具，修复后12项通过；两种跨会话竞态、正常双向分页、同ID重读、三档尺寸公式/无溢出、无renderer异常；前后截图留存并检查 |
| lexical | 32组完整对象精确相等；9轮交替配对，耗时中位下降15.7%–26.3% |
| SSE | 300ms真实SQLite写锁夹具；最长5ms心跳间隔380.33→17.00ms，3个chunk、无worker错误；不是真实模型端到端耗时 |
| 资源关闭 | 保留引用、关闭GC的100次事务退出后可用连接100→0；新增确定关闭有约0.2ms/次成本 |
| Embedding | 使用已有本地ONNX资产与冻结500文本；交互查询2.03ms中位。摄取10.11条/秒未达20门槛，脚本FAIL。原始RSS错误保留，另列单位纠正 |
| Chroma | 独立临时真实Chroma1.5.9、500个合成512D向量、20次热查询；中位0.2245ms。不包含embedding或教材事实召回 |

构建保留现有MathLive大chunk警告；已存在动态加载，不以警告本身为理由重写公式输入。UI导航没有测出明确收益，启动单样本不可用于提速声明。

## 补充工具

- `scripts/qa-audit-history-electron.mjs`：复现迟到分页并检查真实Electron；接受明确的before/after生产构建目录。
- `scripts/benchmark-audit-local.py`：从固定Git基线加载旧lexical与两个store，合成语料配对及连接生命周期见证。
- `scripts/audit-runtime-contention.py`：真实临时SQLite锁竞争+生产SSE，`--baseline`只加载固定Git版本的binding，不切换工作树。
- `scripts/benchmark-audit-chroma.py`：临时Chroma向量查询基线；不用正式向量库。
- `docs/qa/performance-reliability-2026-10-23/run_pytest.py`：隔离后端测试入口。

未引入监控系统或运行时依赖。单独保留初次/最终测试及探索样本；最终性能对照明确选择相同条件下的最终配对，不删除不利结果。

## 未解决项及下一步方案

1. **AUD-14（P2）**：本机摄取吞吐门槛失败。先控制batch、线程、文本长度试验，同时守住交互p95、RSS和向量/检索质量；不直接改生产配置。
2. **AUD-08（P2）**：其他SQLite模块调用者对连接所有权不同。逐模块审阅并补异常/事务测试后再修，不能统一换contextmanager。
3. **AUD-10（P2）**：Notes不同job缺全局并发准入；设计有限队列、取消、claim与重启语义后实施。
4. **AUD-11（P3）**：共享Context render可能增加开销，但未有profiler证据；不进行Context重写或长列表虚拟化。
5. **AUD-12（P3）**：兼容工具软超时线程会继续执行，已有slot限制；按慢handler补deadline/协作取消，不开放任意工具并行。

剩余合同和后台调度方案仅记录，尚未实施。AUD-09 发布输入隔离已按用户要求完成；完整安装升级仍未验收。已有ContextPack、EvidencePack、有界Runtime、staged索引发布、独立学习资产库与按需加载继续保留。

## 变更边界与回滚

开始时存在12个未提交文件，包含搁置功能及既有patch_notes内容。未提交、暂存、合并或push。`chat_binding.py`与`patch_notes.md`是共享文件，仅加入审计SSE调度hunk与本报告版本记录；搁置差异及开关未调整。保存核对结果见 `preservation-check.json`。

回滚应按上述文件审阅并撤销**本次审计hunk**，配套撤销相应回归或基准预期；不要对共享文件执行整文件checkout/reset。没有数据迁移，所以无需数据回滚。可独立回滚lexical优化或RSS测量修正；ChatContext与ChatPage两处需一起回滚。正式数据和已运行的任务状态不在回滚范围内。

最终全量另有既有搁置功能取消测试失败（前两轮通过、最后一轮失败），根因未判定；只保留完整套件观察，不扩展为搁置功能实验/修复。当前有明确的离线合同与Embedding吞吐验证阻断；没有发现未修复的已复现P0/P1，不代表可无条件发布。真实模型答案/Token、正式教材事实覆盖、Windows安装升级、真实手机断网恢复和长期负载仍需各自发布验收。

## 收尾期间的其他工作树改动

收尾时检测到另一组图片识别恢复/错题API修改：`backend/api/mistakes.py`、`backend/services/multimodal_bridge.py`、`tests/test_mistakes_api.py`、新`tests/test_visual_recognition_recovery.py`及独立patch_notes条目。它们不属于本轮7项修复，已原样保留；没有把其他任务成果计入本次性能收益。为避免用旧结果代表新树，另跑当前工作树完整测试，记录在`docs/qa/performance-reliability-2026-10-23/backend-current-tree.log`，运行前后源码哈希核对记录在同目录。原审计各轮日志和样本不覆盖。

此次当前工作树补跑为 **2163 passed / 3 failed，91.80秒**，仍为同3项Policy合同失败；此前那项搁置取消测试此次通过，保留其失败观察且不认定根因。运行前后源码哈希一致（`test-source-stability.json`）；新增用例属于另一任务，不能计入本轮修复数量。其他任务的暂存操作亦不属于本轮；本任务没有暂存、提交或推送。

## AUD-09 后续修复与合并提交

后续实现及验证见 `docs/qa/aud-09-release-2026-10-23/README.md`。此次按用户授权将两平台构建脚本、构建回归与原七项审计修复纳入同一提交；原审计中“未暂存/提交”的描述是当时状态。图片识别恢复已有提交 `e870e3b`；搁置差异保持未提交。完整原审计最终日志中包含范围外功能 traceback，该原始文件保留本地，仓库发布其 hash 与失败摘要 `backend-final-summary.md`，不将范围外实现片段纳入提交。

后续全量工作树2166通过/3失败；独立导出的暂存源码31项定点后端、249项前端、lint/build及真实macOS Electron12项通过。后者不加载工作区未暂存的其他实现，日志与三尺寸截图见上述后续QA目录。

## AUD-07 后续合同修复

当前历史/生产工具合同已分离，原3项失败消除，六文件295通过、全量2199通过。历史390文件字节不变，旧审计失败记录保留。新基准11/11轨迹、11绑定检查/0错误，不代表线上模型准确率，不批准生产启用Policy。变更、复现、负例与限制见 `docs/qa/aud-07-contracts-2026-10-23/README.md`。
