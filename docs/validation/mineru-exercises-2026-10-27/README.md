# 教材建库结构与 MinerU 习题 ZIP 验证

本轮起点是用户端截图：目录下拉出现正文残句，选择“思考题与习题”后抽取为空。用户明确要求先修建库质量，不把逐次手工诊断/重做作为常规工作流；同时指出习题入口缺少 MinerU 包支持。

截图对应的完整来源、Canonical 与当次安装包身份不在本机。本轮使用合成结构复现机制，并另外读取一份本地既有 351 页教材回归；后者不是截图用户的教材。没有重新 OCR、调用付费模型或更改正式索引/学习数据。

## 机制与修复边界

1. 原生 Adapter 把不超过 24 字的多个 `paragraph_title` 当作同层标题；中文“节—一、—（一）”没有稳定分层。短正文残句可能进入 heading，随后被切块器跳过。v5 先用显式编号组织层级，带正文/延续信号的源标题降为正文；弱短标题即使保留结构归类，其文字也进入可检索正文，避免误判后丢字。
2. 正常摄取自动写入 `ingestion_report.json/source_metadata/structure_quality`，统计标题决策、题目单元及有习题标题但无题目的范围。未知题号同样触发空范围提示，不依赖已识别题号数量作为唯一检测依据。外部教材 ZIP 导入结果携带此报告，完成页直接提示范围缺口。
3. 切块后、打开向量库之前，校验每个可读正文/弱标题块是否进入同章候选 chunk。丢块或错章属于机械保真失败，拒绝发布；语义/OCR 不确定仍是 warning，不删除可用正文、不把未知伪装成已识别。已有生产检索与 Final EvidencePack 门槛保持原值。
4. 抽题配套支持复合习题标题和 `2-1` 等章内题号；Canonical 范围按物理页、heading ID 解析，避免旧 `_chapters.json` 印刷页误限范围。读取不改写旧 IR/向量数据。既有坏向量结构不会因更新代码自动修好。

这些规则修正一类结构错误并保全正文，不声称能仅凭正则判断所有教材的语义目录、修复 OCR 字误或证明题目正确。没有新增自动迁移/自动重建已发布索引，也没有引入目录 LLM。

## MinerU 习题 ZIP

入口：练习 → 导入 → 上传文件 / MinerU 包。题目及独立答案文件均接受 `.zip`。复用教材来源 Adapter 读取原生 structured content 和既有兼容格式，不要求先建教材库，不提交到 OCR。

压缩包采用既有路径、膨胀、文件数与磁盘检查；ZIP 单文件沿用 `MAX_OUTPUT_ZIP_BYTES`，HTTP 总量覆盖两个文件，原 Word/PDF 限制保留。上传分析等待上限为五分钟。候选继续走 v1 来源快照、服务端重放和人工校对合同。

公式、表格、题号、源物理页/坐标保留。来源图及公式/表格原图复制到既有 `PROGRESS_PATH/exercise_import_sources/assets`；图片读取绑定来源快照、题库范围、SHA-256 和受限图像格式，通过已有鉴权 blob 通道显示。上传临时解包目录在分析后清理；原 ZIP、来源快照与独立资产保留，可在进程重启后读取。

图片题的独立练习资产准入门槛沿用原合同：校对页能看到来源图片，不等于允许绕过必需图片/前例条件门槛直接入库。未扩展独立练习的图片交付合同。

无依赖、SQL 或 IR schema 迁移。Adapter v5、正文保全和学习单元识别影响新候选 fingerprint/chunk/索引版本；现有 active 保留。资产仍在既有 progress 备份根内。

## 实测

| 检查 | 结果与范围 |
| --- | --- |
| Python | `venv310` / Python 3.10.21；相关 245 项通过，6 条既有弃用提示，见 [backend.log](backend.log) |
| 前端 | 55 文件 / 256 项通过，见 [frontend.log](frontend.log)；修改组件 ESLint、TypeScript/Vite 构建通过 |
| 真实 macOS Electron | 1280×820、1024×768、760×820；38 检查 / 15 图，无 renderer 错误或横向溢出，见 [electron.json](electron.json) |
| 真实隔离建库 | 本地 ONNX FP32 + Chroma，合成两章/3 题/6 chunk；原生产检索/Final EvidencePack 及唯一公式探针 1.0/1.0 通过，见 [hybrid.json](hybrid.json)；其他专项为 not_applicable，不计作已验收 |
| 本地教材回归 | 既有 351 页来源，4925 块；新投影 111 个学习单元、2585 chunk，机械缺块/错章为 0，见 [corpus-summary.json](corpus-summary.json)；未跑整本生产检索门槛，数量增加不作为质量或正确率证明 |

Electron ZIP 选择、真实 parser/API/SQLite、原解分离、表格和来源图读取使用完整真实链路及合成内容。教材完成页的提示使用明确标记的 UI job 夹具，自动结构诊断由后端测试单独验证。截图实际查看了各桌面尺寸的来源选择、候选/原文与警告状态。没有 Windows 安装包、真实用户整本教材或 OCR/数学金标验收。

回归入口：

```sh
venv310/bin/python -m pytest tests/test_textbook_exercise_headings.py tests/test_mineru_exercise_archive.py -q
npm --prefix frontend test -- --reporter=dot
npm --prefix frontend run build
node scripts/qa-mineru-exercise-electron.mjs
```

Electron 脚本需要已安装的 Electron 与 Playwright，可通过环境的 `NODE_PATH` 指向现有依赖，不要求重装。全部 QA 数据使用独立目录；`TEXA_MINERU_EXERCISE_QA_WORK` 可指定输出目录。截图保存在该目录的 `screenshots/` 中。

源码在日常集成分支 `Texa_MacOS`；本轮未 commit/push/打包发布，其他未提交和搁置 Web 工作均保留。
