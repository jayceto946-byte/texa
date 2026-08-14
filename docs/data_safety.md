# 数据安全基线

本项目的长期学习资产主要在 `data/` 下，开发和重构时优先保护这些目录：

- `data/progress/`：错题本 SQLite、学习记忆、章节缓存等用户进度。
- `data/images/`：错题图片、OCR 工作图。
- `data/books/`：用户导入的教材 PDF。
- `data/chapters/`：章节缓存。
- `data/vector_db/`：ChromaDB 向量库，可重建但成本较高。
- `mineru_output/`：MinerU 解析和知识图谱中间产物，可重建但耗时。

## 版本控制

本地学习数据、向量库、PDF、构建产物、诊断输出默认不进入 Git。源码、测试、脚本和长期文档才应纳入版本控制。

## 备份

在做依赖升级、索引格式调整、数据库结构修改、批量导入或清理前，先运行：

```powershell
cd D:\AI\agent\kaoyan-assistant
.\scripts\backup_learning_data.ps1
```

脚本会把 `data/progress`、`data/images`、`data/books`、`data/chapters` 打包到 `backups/learning_data_*.zip`。

`data/vector_db` 和 `mineru_output` 体积可能较大，默认不打包；需要保留时请单独复制整个目录。

产品重命名后的 Electron 数据目录仍使用旧兼容路径。未来切换到 Texa 独立目录时，必须遵循 [userData 目录迁移方案](user-data-migration.md)，在实现与回归门槛通过前不得移除兼容路径。

## 验证

每次改动错题、复习、教材导入、RAG 或前端构建后，至少运行：

```powershell
.\venv310\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```
