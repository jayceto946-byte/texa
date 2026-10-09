# 教材 A/B/C 修复与开发版验证

日期：2026-10-04。基准 HEAD：d36767f32690506b3697340bb6eaa948395dbcf0，包含本轮未提交修复。

## 实际运行版本

最初按应用名打开了 release/mac-arm64/Texa.app 的旧打包版。该窗口没有用于判定修复通过。用户指出后，改用当前仓库 Electron 开发入口；由于桌面上同时有其他 Electron 实例，验证 runtime 使用独立 bundle 标识 Texa Dev Validation，以便准确绑定窗口。复制的是仓库已有 Electron runtime，运行入口仍为当前 desktop/main.cjs，没有运行 release 中的 app.asar。

最终后端地址 http://127.0.0.1:58127。启动日志确认 isPackaged=false、appPath=/Users/jichengqian/Documents/ChatGPT/texa/desktop、前端为当前 frontend/dist，Python 为本仓库 venv310/bin/python（3.10.21）。前端在本轮修改后通过 TypeScript 并重新构建。数据使用 /private/tmp/texa-dev-abc-20261004 内的桌面数据副本，不写原有教材、索引或学习资产。

证据：validation/textbook-abc-2026-10-04/development-runtime-proof.log、development-ui-validation.json。

## 代码修复与实测

| 范围 | 修复 | 实测 |
|---|---|---|
| A 可选概念任务 | 导入正文成功与概念任务单独展示；关联子任务继续读取状态，失败不否定正文，不自动重试模型 | 状态读取代码及构建通过；未重新付费跑概念抽取 |
| B01 目录与范围 | Canonical 共享目录只读补全，保留 heading ID、父级、level、block 范围；小节按 ID 选择，防同名与同页串范围 | 原教材恢复 258 个小节；开发版下拉可见 1.1、1.1.1；同页范围、重复层级不重复正文回归通过 |
| B04 组合图 | 同页同范围连续 a/b 标签及单公共图号保守分组；保留原子图接口，展示、视觉输入与选区裁剪使用同一组合；缺成员门槛进入 waiting_for_input | 图 1.21 物理页 29，两成员均纳入 provenance，组合尺寸 1068×331；最终开发版搜索并显示幅频/相频两张子图。没有提交识图模型请求 |
| B05 无 PDF 抽题 | 根据真实 has_pdf 展示可选 PDF 入口，页码失焦不再弹窗；不存在 PDF 返回 404，预览拒绝非 PDF 响应；直接从 Canonical 学习单元抽取 | 开发版无 PDF 按钮，原教材习题节直接得到 16 道待校对候选，附表与小问保留 |
| B05 完整题目 | 统一括号例题识别，按范围/下题/局部标题形成单元；题干、解答、公式、附表共享身份，支持跨章每题来源；同文件按 resolved path 去重 | 全书 14 道例题，第 1 章 6 道；例 1.3 带表格与解答；题 15 的标题型 (2) 小问也保留。候选仅待人工校对，未点击入库 |
| 页码 | structured adapter 保留独立 page_number block 的印刷页及来源；界面明确物理页 | 从原始输出重新解析候选时，物理页 29 所有块的印刷标签均为 19；不回写旧 IR，不猜测固定页差 |
| C 例题覆盖漏洞 | 生成探针复用完整单元和成员来源；源端清点与生成数同时进入发布门槛，避免源有例题却判不适用 | 原教材只读生成的 example inventory 与 source_inventory 均为 14；发布合同回归通过 |
| OCR 审阅 | 对重复文本和解析器拒识文字生成定位 warning，保留原文 | 只读探测发现物理页 5 的 3 个审阅信号；语义离题文本仍需原页人工核对，没有自动改写或删除 |

新 native parser 版本为 mineru-structured-content-v2。新候选会标记学习单元并补齐目录；既有正式 IR/manifest 不原地迁移。正式活跃索引仍为 c8b6947edb7858f2，本轮没有声称其旧例题门槛记录已经更新。

## 验证记录

- 后端相关 11 组回归 97 passed，6 条既有弃用警告；之后增加印刷页来源字段及共享 parent ID 断言，受影响的 2 组复验 20 passed；组合图来源 hash 元数据明确保留成员 hash、不冒充组合图片 hash 后，Figure 组复验 22 passed。计数重叠，不相加。
- 前端相关 4 文件 / 28 tests passed；TypeScript、变更文件 ESLint、Vite build、git diff --check 通过。Vite 保留既有分块提示。
- 桌面端 14 tests passed。回环端口测试在允许本机监听的执行环境复验，沙箱内 EPERM 不判为代码失败。
- macOS 原生开发版实际检查：1280×820、1024×820、760×820；窄窗口转为上下布局，新增控件无横向溢出。拖动窗口未成功获得精确 1024×768，未将其记为通过。
- 真实教材只读结果：validation/textbook-abc-2026-10-04/repair-data-probe.json；测试日志同目录。

## 尚未验收的边界

C01 原历史阻塞原因仍无请求/预期证据。C02–C04 的完整列表、精确型号、范围边界和错误前提，不能由本轮结构回归或候选计数证明模型答案正确；没有运行新的付费真实模型 Answer Eval。原页 OCR 人工校正、重新构建候选索引并通过生产混合检索/最终 EvidencePack 后激活，仍是后续独立数据变更。本轮代码已修复上述确定性缺口，没有改动数据库结构、依赖或正式教材版本。Windows 与安装包未验收。
