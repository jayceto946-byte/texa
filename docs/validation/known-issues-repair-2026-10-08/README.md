# 2026-10-08 已知问题修复与复验

后续更新：用户要求审阅后，K02 已完成 [V0.1 基准审阅与默认切换](../runtime-policy-evaluation-dataset-v0_1/README.md)，全量 1470 passed。下文测试数量及待审批状态是首次修复时记录；材料/完整业务验收仍待完成。

首次修复结论：K01 的已复现证据假阳性已修复，K03 的 9 项失败已处理，K05 已形成当前代码的 macOS ZIP/DMG 候选并验证原生启动、退出。**仍为 NO-GO**：K02 冻结基准未获新版批准；真实教材材料题仍只有部分证据，L2/L3、升级恢复及人工原页校正未完成。

## 实现与验证

- 短材料问题恢复主题、“两种材料”、“特点”和“应用场景”三个独立交付项；同书/原章节的材料分类补召回在规则路径即可运行，比较意图也保留分类锚点及各材料解释。最终检查以实际截断正文为事实来源，章节位置只用于主题归属，不能替代缺失特点/场景。
- 两类材料的特点、场景须分别有材料正文支持；不能以分类句或一般应用说明代替。完整正例、缺一类解释、标题独有事实、事实超出截断范围及错学科片段均有回归。
- 真实传感器索引副本：材料问从旧 `supported` 且无材料事实，变为 `partial`，最终 Pack 含金属/半导体应变片分类，仍缺完整特点与场景。缺失市场规模未被标完整支持。证据详见 `real-retrieval-summary.json`。这未证明 OCR 事实正确或模型回答准确率，也未通过全部 L1。
- 型号 literal gate 识别 `DEMO-X1` 等连字符字母段，继续区分 `DEMO-X10`，不把 `k1=16` 等计算输入当型号。5 项旧列表测试通过；没有放松错误型号门槛。
- 图片引用校验读取图注正文，但资产 ID/URL 本身不提供事实支持。2 项图片题测试原来的任意占位回答不能获得通过，改用图注实际支持的结构示意图回答；视觉在线评估的合成来源补齐其预期组成事实。新增测试确保空图片元数据和不相关图注不能验证结论。没有以图注宣称验证任意视觉事实。
- 检索枚举评分保留 0.85：声明七种及两个结构信号不是七个成员已完整覆盖的证明；修改该项精确期望，保留排序断言。
- Python 3.10.21 隔离离线全量：**1407 passed / 47 failed**，21.06s。剩余失败全部为 Policy 冻结源码漂移。此后新增图注边界回归，`test_answer_verification.py` **12 passed**。K01/EvidencePack/教材边界/验证定向回归 **48 passed**；K03 初次相关回归 **73 passed**。完整日志见 `backend-tests.log`。

## K02 新版基准审阅候选

旧 source pins、fixture gold、manifest 均未修改。已定位三个漂移源，且这三个文件的 HEAD 字节分别与旧 approved pins 完全一致：

1. `policy.py`：规则选择接收通过验证的问题理解提示。
2. `policy_projection.py`：将有界意图/维度提示投影进 constraints；不带实体原文与密钥。
3. `router.py`：提示可增加只读 `exercise.inspect`，不添加写权限；显式规则优先，读动作不跳过 Runtime。

`policy-current-changes.patch` 与 `policy-candidate-source-manifest.json` 是供审阅的实际差异和候选源码身份。27 个合成比较中，18 个 off/shadow 初始 Observation 与 bindings 保持一致；9 个 fallback 的 payload 发生预期变化。见 `policy-comparison.json`。范围仅初始候选/选择，不覆盖真实模型、完整生命周期或人工金标。

建议新版本采用独立的 V0.1 baseline 目录，审阅并绑定这些变更，以及新增的传递依赖 `graph/question_understanding.py`、变更的 `decision/contracts.py`；保留 V0 与旧数据的可复现身份。当前候选**不构成新版批准**，不能仅把新 hash 填进旧 manifest。当前 47 项失败继续作为发布阻断，待新版源码和合同审阅后再发布其数据版本并重跑。

## K05 离线打包与原生验证

新增 `scripts/pack-desktop-macos-offline.cjs`，使用安装好的 Electron、electron-builder 与已有纯 JS 依赖，依赖树由 builder 的 traversal collector 读取。仅临时 staging manifest 标记 traversal；不重装依赖、不修改 desktop package.json 或 lockfile、不联网发布。缺后端/本地 Electron/缓存的 dmgbuild helper 或非空输出目录会拒绝运行；DMG helper 可通过 CUSTOM_DMGBUILD_PATH 指向已有文件，不自动下载。

```sh
node scripts/pack-desktop-macos-offline.cjs --backend /path/to/prebuilt/backend --output /path/to/empty/candidates
# 可用 --target zip 或 --target dmg 单独构建。
```

先从当前代码重新构建隔离 PyInstaller 后端；前端使用本日整体验收已验证、且本轮未再改动的构建。后端 `validate_standard_release.py` PASS，依赖/embedding hash/动态导入检查有效。

ZIP 已形成。DMG 首次在沙箱内因 `hdiutil: create failed - 设备未配置` 失败；沙箱外同配置重试成功。DMG `hdiutil verify` 校验有效。候选保存在 `release/known-issues-2026-10-08/`，SHA-256 与大小见 `package-artifacts.json`；未经发布批准，未签名/公证，未上传。

原生打包 Texa.app 使用 `/private/tmp/texa-known-issues-repair/native-profile` 空 profile：首次配置界面可见、后端就绪、ONNX embedding 就绪；Command-Q 后主进程退出码 0，后端接受 graceful shutdown 并退出码 0，无窗口销毁异常。见 `native-start-quit.log`。截图工具超时，未获得本轮截图；本轮测试的是首次配置及正常退出，不是全部 UI/窗口关闭按钮/正式安装/升级/数据恢复验收。

## 剩余条件

- K04/K07：原 PDF/完整原页、第二本可信真书、独立人工校对和 Windows 主机仍缺失。保留 pending_review/not_run；不自动改教材 IR、活动索引或正式习题库。
- K06：没有基于文档中所述旧授权发起模型请求；本轮模型请求 0、费用 0。Policy 冻结门槛与完整 L1 尚未通过，未启动 L2。
- K08：没有把定向测试或启动成功当作作答→错题→SM-2、笔记正式保存、Goal 和三个窗口尺寸的业务签收。

本轮未激活正式索引、未修改正式会话/笔记/错题/Goal 数据，原有未提交工作树继续保留。原 2026-10-08 整体验收记录是修复前历史，不改写其首次失败。
