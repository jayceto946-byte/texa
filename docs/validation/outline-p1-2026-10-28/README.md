# P1：共享目录恢复与示例校准

2026-10-28。在 `Texa_MacOS` 当前工作区实现。生产代码不包含教材书名、题材专用分支或单书 adapter。

## 用户能得到什么

新教材从 MinerU、文字 PDF、Word 等来源进入同一个目录恢复阶段。教材浏览、章节向量与词法检索、习题范围使用这份结构；不再只修章节下拉框。

教材管理页新增“目录不符？校准”。用户选择一个代表章节，为少量文字指定层级或习题区，预览全书后应用。同类编号、重复标题及可用的真实字体样式会推广到其他章节。选择“正文”会把同类小项移出目录，原文仍进入索引。目录深度只影响导航显示，隐藏的习题范围仍可用于抽题。

应用通过 JobManager 和既有 staged index publication 执行，更新 Canonical、章节检索与习题范围，不重新 OCR。旧版本继续可读、可回滚；预览后教材版本变化会要求重新预览。关闭面板不取消已开始的任务，重新打开可读取任务状态。

## 自动恢复的具体方法

`ingestion/outline_recovery.py` 是共享实现，过程为：

1. 保留来源文字和 block ID；把原始分类/路径留作结构解释的输入。
2. 从密集条目、编号、页码、目录标签寻找候选目录。在后文按归一化标题和先后顺序查找正文，页码偏移仅辅助定位。只有多个条目得到正文支持才采用；未匹配条目留在报告中。纯数字密集不构成目录证明。
3. 原 PDF 可用时读取全部书签层级，用标题和物理页核对正文位置。MinerU 包没有 PDF 时仍可独立完成目录/正文匹配。
4. 结合中英文章/节、分篇、小数编号、来源标题和整份文档实际字体统计建立层级。缺失父级时不凭空补标题；没有字体信息时不从包围框高度伪造字体。
5. 顺序建立章节路径及范围，重新组织学习单元。校准示例覆盖自动判断，例题/习题用途与导航显示分开。

已确认的目录文字留在 Canonical，并明确标记为目录，不作为正文检索块；混有未解析正文的块保持可检索。前言等前置正文也保留检索，不冒充一章。

正常文字 PDF 导入改为逐页保留文本/位置/字体，进入共享恢复，普通导入不再为了找目录自动调用视觉模型。旧 PDFParser 的兼容识别能力保留。没有新增 LLM、OCR 调用或依赖。

## 验证及边界

- [相关回归记录](backend-regression.log)：124 项通过，覆盖原摄取、分块、抽题、来源保全、发布与回滚。针对后续新增/修正的 PDF 书签、字体、前置正文、目录显示深度和版本变化另做了局部检查，见 [目录场景](outline-cases.log)、[显示深度](navigation-depth.log)、[版本检查](version-check.log)。未反复运行全项目测试。
- 独立预期写在 [test_outline_recovery.py](../../../tests/test_outline_recovery.py)，包含中文、英文、小数编号、上游漏标标题、真实目录/正文偏移、伪目录、示例推广、自定义习题区、PDF 多级书签、字体与前言。它们是人为编写预期的合成场景，不是由解析器自身生成的验收题，也不冒充跨教材整书金标。
- [前端构建](frontend-build.log)与修改组件 ESLint 通过；构建仍有原有大 chunk 提示。
- macOS Electron 使用真实 MinerU ZIP 上传、books API、JobManager、ONNX FP32/Chroma 和生产混合检索/Final EvidencePack 发布。在第一章指定两个示例，第二章同步生效；[结果](live-verification.json)确认两个章节各有一道习题，限定第二章只得到第二章题目，向量检索没有扩大章节范围，降级为正文的文字仍在索引中。
- Electron 在 1280×820、1024×768、760×820 的预览和完成状态已逐图检查。书本相关 API 为真实链路，其他页面辅助 API 为 UI 夹具。[UI 执行记录](electron-result.json)保留原始结果：界面操作和发布完成后，后置检查最初被向量库 stdout 日志干扰，JSON 读取失败；修正检查程序输出后单独验证成功，未把这次脚本错误改写为“零错误”。
- 既有 351 页材料仅作只读兼容检查：自动定位到目录中的 262/268 个条目，6 个未匹配；正文中的一组数字表候选被拒绝。该材料不是用户截图教材，也没有因这次检查重建索引；条目匹配数不等于章节树准确率。

尚无足够的、整本书留出的独立人工金标，不能声称已测得“绝大多数教材”的准确率。OCR 错字、目录标题与正文差异很大、缺页、阅读顺序错误、同书多套不一致编排仍可能需要校准。示例主要推广相同编号/文字/可用样式；不能从任意一个章节可靠推断所有特殊编排。

本轮没有迁移旧教材、学习记录或 SQL。新增 `outline_recovery` 元数据和可选 block 属性，沿用 Canonical schema 1/index schema 6；PDF 文本来源版本为 `pdf-text-layout-v2`。只有新导入或用户明确应用校准时发布新索引。未发布 Windows 安装包，未在 Windows 上实机验证。

## 复现

```sh
venv310/bin/python -m pytest tests/test_outline_recovery.py -q
npm --prefix frontend run build
TEXA_INDEX_QA_WORK=/tmp/texa-outline-p1 node scripts/qa-outline-electron.mjs
```

Electron 验证需要本地现有 ONNX 资产、Electron/Playwright 与回环端口权限；本次通过 `NODE_PATH` 使用系统工作运行时提供的 Playwright。所有运行数据写入隔离临时目录，不读取或覆盖用户的 active 索引。

截图：[1280 预览](screenshots/1280-calibration-preview.png)、[1024 预览](screenshots/1024-calibration-preview.png)、[760 预览](screenshots/760-calibration-preview.png)、[应用完成](screenshots/760-calibration-applied.png)。
