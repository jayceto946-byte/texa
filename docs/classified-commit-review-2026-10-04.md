# 未提交改动分类与提交前复核

日期：2026-10-04（Asia/Shanghai）。起点为已推送的 `Texa_MacOS` / `1b6bb18`。
用户批准审查剩余改动、分类提交并推送。本次只整理已有实现与记录，没有继续扩展功能、重构、迁移正式数据、重装依赖或运行模型。

## 分类

| 组 | 范围 |
| --- | --- |
| 后端学习流程 | 独立 SessionNote 存储、冻结完整来源、有界生成与候选发布、revision CAS/幂等保存、Job 恢复；持久会话导航与任务准入/明确结束；错题来源复用、未完成复习读取；公开执行详情、备份验证及离线回归。共用 API、Runtime 与存储入口按依赖一起提交。 |
| 桌面保存与配置 | renderer nonce/sender 关闭握手、保存失败阻止关闭/重启/更新；不含凭证的首次配置完成标志、IPC、打包清单与测试。 |
| 前端学习流程 | 笔记预检、草稿与正式版本、串行 CAS 自动保存、来源定点导航；会话分页/置顶/归档/回收站及阻断任务操作；错题状态复用、可展开执行详情与相应测试。 |
| 共享工作区 UI | 页头高度/字号/边框、管理页滚动与层级、复习继续入口、练习空态和人工录入、错题子页及周报布局。 |
| 文档与验收证据 | AGENTS 长期约定、patch notes、原有 handoff/实施/验收报告及有说明的合成执行区截图、JSON 记录、本复核记录。历史阶段结论按原日期保留。 |

## 文件与数据边界

- 使用逐文件清单提交，未使用 `git add .`。提交前检查原有文件内容 hash，防止遗漏或混入审查期间的新变化。
- `.DS_Store`、`frontend/ui-refactor-preview.html`、`frontend/src/ui-refactor-preview.tsx` 为本地元数据/开发验收预览，保留原文件但不提交。
- 新的 PNG 仅为 `docs/validation/execution-trace-2026-10-03` 中 10 张有说明的合成界面截图；不是教材扫描页、原始用户截图或学习记录。
- 未纳入环境文件、凭证、数据库、生产学习数据、完整教材、归档、安装包、frontend/dist、缓存或 `/private/tmp` 产物。文档里的本地路径与 checksum 是溯源记录。
- 12 份 SessionNote 代表样例是已有 synthetic/offline fixture；本次未运行付费模型，也未把此前结构检查或代理审阅当作人工签审。
- 部分旧报告引用 `artifacts/` 下本地保存的原生截图、模型首次输出与发布候选；这些忽略目录中的材料未自动加入 Git。

## 本次复核

- Python 3.10 / venv310：全量离线 **1313 passed**，6 条既有依赖弃用提示。DATA_DIR、MINERU_OUTPUT_PATH 与 ENV_PATH 显式隔离到 `/private/tmp/texa-classified-commit-tests-*`。
- 前端：**31 个测试文件 / 140 passed**；TypeScript、全量 ESLint 与 Vite 构建通过。构建写到独立 `/private/tmp` 目录，没有覆盖正在使用的 frontend/dist。既有 Markdown 混合导入和较大 chunk 提示保留。
- 桌面：**14 passed**；临时 loopback 监听在允许本地监听的环境中验证。
- 逐组暂存检查发现新文件 SourceGroupList.tsx 末尾多余空行，已仅清理该格式问题。工作区与逐组暂存 diff 空白检查、新增文件类型/凭证形态检查、JSON 解析通过。未发现功能阻断问题。
- UI 使用 texa-ui-system 做源码审查，并抽看已有合成执行区截图；本次未重做原生 GUI 全流程、Windows、发布包或真实模型语义验收。原报告中的未覆盖项不因此放行。

提交顺序遵循后端接口 → 桌面桥接 → 前端流程 → 共享 UI → 文档。最终组合由上述测试覆盖；不将拆分提交数量表述为新增功能或额外验收。
