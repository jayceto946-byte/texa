# MinerU 4 原生适配实施与验收

实施开始：2026-10-03；交付完成：2026-10-04（Asia/Shanghai）。依据 `mineru-native-sol-handoff-2026-10-03.md`。
代码基线：`Texa_MacOS` / `ddf7f3b8036f59f6097b459c3945617547b7fd1a`。
保留会话开始时所有其他未提交修改；未重跑 OCR、调用外部模型、改动生产数据或依赖。

## P0 检索

- generic list 优先同 section，完全没有同 section 成员才退回同 parent sibling；保留章节、前后方向、formula 排除和数量约束。
- `list_group_order=0` 也能通过列表 literal 豁免，普通 evidence 继续原 literal filtering。
- 独立负向回归证明服务器两个 hunk 会接受错误型号，因此增加本轮可信组装的组级 literal 校验；其他教材、错误 section 或输入自带 list 标记不能授权豁免。
- 每个 bug 均有独立合成 fixture 与最终 rerank → support gate → EvidencePack 测试，另保留 MAC / NK-Humirel 的 16 个固定源片段。fixture 在 `tests/fixtures/mineru4`，完整教材不提交为测试 fixture。
- 未调大 EvidencePack 配额、预算或降低 release thresholds。

## 原生 adapter 与正式入口

- 新增 `MinerUAdapter.from_structured_content()`，直接创建 Canonical，无临时 content-list bridge。
- 选择顺序：有效 structured → content-list v1 → v2 → 旧 `pdf_info` middle → Markdown。
- 损坏 native、未知 producer 主版本、多 native 文档、不同目录的混合书源、同优先级不同 JSON 均明确拒绝。新版 `pages` middle 给出诊断，不交给旧 parser；`_middle_chunks.json` 永不参与 source 选择。
- external / API / CLI 与全文抽取共享 adapter；业务 chapters 从同一个 Canonical 投影，不从另一份 Markdown 获取。
- 编号章、节优先；局部 `1.` / `(1)` 保持正文。非编号标题仅在正文章内按长度、标点和编号条件有界恢复，保留 raw level 与规则。前置可读材料保留为默认单章正文，doc_title 单独记录；header/footer/page_number/index 排除并报告数量。
- formula 的 content/text/latex 是替代表示，只保留一份正文与 equations。表格同时保留 Markdown/HTML、caption、footnotes，解析 header/rows。修复旧 Canonical reader 丢失空白表头列的问题。
- 所有 native blocks 保留原 page/block 索引、producer/adapter、物理页；bbox 明确 page / xyxy / normalized。缺 confidence 保持未知。

## 资产和兼容性

- 顶层 Canonical schema 仍为 1；新增可选 source_metadata 和 `attributes.original_visual_asset` v1。旧 Canonical 没有新字段仍可读。
- 公式／表格仍是 formula/table，不额外复制成 figure，也不扩增检索证据。
- original_crop 合同包含原路径、受控持久路径、SHA-256、实际格式、尺寸、状态、block/page/bbox 坐标。ready 合同缺损是 error；缺图/坏图保留正文并 warning。
- figure 原字段和 `materialize_figure_assets()` 兼容入口保留。所有新 crop 使用 block ID + 内容 SHA 文件名，不覆写、提前删除旧资产。源/目标越界、symlink 逃逸和错误实际格式受保护，不下载远程引用。
- 资产随现有 progress 备份恢复；不改变全局存储布局。新视觉资产未接入 LLM prompt，不提升数学验证状态，本轮没有新增原图 UI。

## 一致发布和恢复

- Canonical、报告、probes 和 crops 先写到隔离候选目录，再在现有 index_publication 边界内和 lexical / map / manifest 一起切换。
- Canonical loader 与 figure cache 参与读取 snapshot；嵌套读取可重入。并发测试证明 staging 时读旧版，publication 中 reader 等待，完成后 hash / source_block_ids / index_version 一致。
- gate 失败、取消、异常及可捕获中断恢复旧文件；仅清理本次创建的候选文件。retry 幂等。
- 新发布保留 `canonical_versions/<hash>` 和索引版本关联，回退同时恢复 IR / 报告 / probes。旧 IR 与旧 manifest 不匹配或缺版本证据时不补造关联，拒绝混合回退。
- `_middle_chunks.json` 只是非权威诊断投影；保存失败记录日志，不将已成功提交的导入错误标为 failed。
- 没有进行旧引用迁移；新 source_file / IDs / hash 与 bridge 不同，不按标题或编号自动重绑。
- 本轮验证覆盖同进程异常、取消、可捕获中断和并发读取。**未验证进程硬终止或掉电跨文件恢复，也不宣称跨进程事务隔离。** 跨机更换 progress 根目录的 retained snapshot 自动重定位未实现；应显式处理或重建。

## 固定完整语料验收

归档原件保留在 `/Users/jichengqian/Downloads/texa-mineru-handoff.tar.gz`，SHA-256
`09c6f3bbd9f442f72f6d7554575a476cca6eabab4f9d2134a1160a5b5f974b21`。
仅在 `/private/tmp/texa-mineru-native-*` 运行正式 importer 和本地 ONNX/Chroma。

| 指标 | bridge 冻结基线 | native 实测 |
|---|---:|---:|
| blocks | 4911 | 4925 |
| paragraph / heading | 3430 / 268 | 3442 / 270 |
| formula / table / figure | 522 / 28 / 663 | 522 / 28 / 663 |
| paragraph / formula / table chunks | 1266 / 522 / 36 | 1268 / 522 / 36 |
| 文本入库 chunks | 1824 | 1826 |
| figure assets ready | 663 | 663 |
| formula/table original crops ready | 未保存 | 550 |
| intake errors / warnings | 0 / 5512 | 0 / 5529 |

差异依据：native 没有丢弃 bridge 未提升为 heading 的 14 个可读标题片段，12 个保留为正文、2 个按有界规则保留为非编号标题。12 章和 243 个编号节保持；默认单章前置正文使业务章节投影共 13 项。最终表格行数为 218，与 bridge 相同；table chunks 仍为 36。源 OCR 文本不做正确性背书，边界标题仍需人工审阅。warnings 是摄取质量提示，不等同于 OCR 失败。

原生最终 fingerprint：
`53dfd8207fcfdf27abecf48c0231edd366454358ab33d2b5bdec2af4d961772b`。
index_version：`4497a92056459a81`。
正式 production hybrid retrieval + EvidencePack gate 24 项通过；formula/list/table 各 8 项，recall 和 point recall 均为 1.0，阈值不变。
example=0 是缺覆盖；例题路径由其他通用 fixture 验证，不能称本语料例题验收通过。
这不是 OCR 人工金标或真实模型答案准确率。

证据：`docs/validation/mineru-native-2026-10-03/native-corpus-report.json`，包含 manifest、Canonical fingerprint 与 specialty gate 明细；`checksums.json` 保存归档、native source、片段与测试 ZIP 的 checksum。未补造旧服务器缺失的最终 manifest。

## Electron 和离线验证

- 使用安装的 Electron dev runtime，独立 userData 托管真实后端和已构建前端。
- 使用既有 `/api/books/import-mineru-output` 上传 5 个保存的原始 OCR 页面及图片制作的 ZIP；不新增 tar.gz 产品入口。实际 job 经过 extract / indexing / completed，34 chunks、13 个原始 crop ready，章节可读，`used_mineru=true`、`has_pdf=false`、`concept_job_id` 为空。
- native GUI 自动化按 bundle ID 解析到用户既有 Electron 进程，无法可靠定位独立进程；为保护既有窗口，未点击它。**本次是 Electron 托管后端链路验收，未完成独立窗口点击上传的 GUI 验收。** 证据 `electron-hosted-api-smoke.json`。
- 全量 Python 3.10 离线 1313 tests、desktop 14 tests、frontend 31 文件 / 140 tests、TypeScript 和 Vite build 通过。桌面端口绑定测试在沙箱 EPERM 后于允许本地监听的环境复核通过。Vite 仍报告既有 Markdown 动态导入与较大 chunk 警告。Windows 打包未运行。
- 原生直接 ZIP 操作已可用，legacy 支持及原始 bridge/归档保留。因 GUI 上传、硬终止恢复尚未验证，本报告不宣布所有 bridge 退役条件或生产同名更新放行条件全部完成。
