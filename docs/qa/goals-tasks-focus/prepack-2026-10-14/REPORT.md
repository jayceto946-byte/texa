# 打包前全量检查 · 2026-10-14

测试对象：`8003dae`，分支 `codex/goals-tasks-focus`，基于 mobile-s3 `af861ba`。从这个提交生成全新临时检出，不读取 .env 凭证；测试数据使用临时目录。未打包、未发布、未打 tag、未迁移正式学习库。

结论：macOS arm64 本地候选的源码检查通过，可在单独授权后开始构建包；Windows 和公开发布尚未通过全部门槛。新包本身的启动、资源内容、离线/升级恢复和签名验收只能在实际打包后验证，不能用本报告替代。

## 全量结果

| 检查 | 结果 |
|---|---|
| Python 3.10 全部后端测试 | 1688 passed，6 条既有依赖弃用告警 |
| 全部前端测试 | 214 passed / 48 files |
| 全部桌面 Node 测试 | 24 passed |
| 总测试数 | 1926 passed |
| 完整 TypeScript、ESLint、Vite 生产构建 | PASS；mathlive 大 chunk 提示保留 |
| 桌面/构建脚本语法 | 30 文件 PASS |
| VERSION / frontend / desktop / lock 版本 | 一致，1.0.0 |
| Python 依赖锁 | exact pin 检查 PASS；26 个 release pin 与当前环境一致 |
| 安装依赖兼容性 | 无冲突；venv 没有 pip，使用 importlib.metadata + packaging 只读核对替代 pip check，没有安装/重装 |
| ONNX 嵌入资源 | 完整 manifest/hash PASS，512 维；onnxruntime 1.23.2、tokenizers 0.22.2 |
| macOS 构建前提 | Darwin arm64、Python 3.10.21、PyInstaller 6.21.0、现有 Electron 分发及缓存 dmgbuild 可用 |
| 样例内容清单 | sample_data 和 macOS standard_seed 检查均 PASS，0 个随包教材文件；不代表已经验证正式学习数据 |
| 编码 | 1810 文件可解码；本次改动无新增 BOM/可疑编码。既有 18 个 BOM 和 3 个启发式提示保留，词表汉字和测试中的问号不自动当作乱码修复 |

第一轮后端 1687 passed / 1 failed。唯一失败是 `test_spa_fallback` 要求 frontend/dist 存在，而干净检出中尚未生成。先从同一提交生成前端产物，再完整复跑后端，1688 项通过。保留首次日志，未修改断言或跳过测试。现有 qa-check.py all 先跑后端、后跑构建；在干净检出执行全量时须先生成前端，Windows CI 的检查顺序也应相应调整。

复现：在干净临时检出绑定已有依赖，用项目 Python 3.10。先执行前端生产构建生成 frontend/dist，然后运行 `scripts/qa-check.py all`。检查脚本移除凭证并设置临时 DATA_DIR / PROGRESS_PATH / VECTOR_DB_PATH / BOOKS_PATH。构建前端属于源码检查，没有执行 PyInstaller 或 electron-builder 打包。

## 明确阻断与未测边界

1. **Windows 专注历史时区数据缺失**：新代码使用 ZoneInfo；当前 release 依赖没有 tzdata。模拟无系统时区目录后，UTC 和 Asia/Shanghai 都返回“无效展示时区”。macOS 使用系统时区数据，当前测试通过；Windows 打包前须补齐可分发时区数据、锁定依赖并验证冻结包。未擅自安装依赖。
2. **公开发布缺 LICENSE**：现有 GitHub release workflow 明确要求 LICENSE；当前仓库没有该文件。许可选择须由项目所有者决定，不生成未经确认的许可。版本仍 1.0.0；正式升级发布的版本号、签名和升级路径应在发布准备中确定。
3. **正式库迁移未授权/未执行**：v1/v2→v3 已有临时备份/迁移证据，正式部署仍需确定真实库路径、关闭旧读取器并按 migration.md 执行。打包授权不自动视为正式数据迁移授权。
4. **真实设备验收**：macOS 物理休眠、Windows、双端设备、脏笔记取消退出、Inspector/长输入全状态、AI 等待确认仍按上次报告的边界待验收；1926 项自动测试不等同这些实机结果。
5. **包后门槛**：没有当前提交的 backend 冻结产物，因此尚不能跑 validate_standard_release 的真实产物扫描。打包后必须验证 Torch-free / ONNX 动态导入、资源 hashes、启动与恢复、包身份，以及实际平台签名结果。

## Git 与授权

实现已本地提交 `8003dae`。推送 `git@github.com:jayceto946-byte/texa.git` 被自动审批拒绝，理由是此前 push 授权没有明确该具体目的地；已向用户请求仓库确认，未绕过。此报告与日志作为单独 QA 文档提交。打包等待用户另行授权。

日志与机器结果就在本目录；所有测试均为离线/fixture，不调用真实模型。安全依赖在线漏洞库未查询，不能声称实时漏洞审计通过。
