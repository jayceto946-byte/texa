# 桌面 UI 重构补充：笔记文章呈现与持久会话管理

后续用户要求进一步简化生成约束、允许适度补充，已实现 [自然文章提示词 v4](session-note-article-v4-2026-10-03.md)。下文保留本轮 v3 的实施记录。

用户已明确批准此前 S6 提案，并要求移除笔记默认页面的来源标识、感叹号、“三项待检查”和标题下的警示。本次沿用 Astra 宏观方案：GPT-6.1 Sol 负责 S6 后端与临时库回归，主代理负责笔记、会话前端、集成复核和桌面验证。保留工作区其他任务的修改。

## 笔记呈现与保存

- 草稿、正式笔记与笔记列表不显示检查数量、逐块来源按钮或核实徽标；编辑器不要求用户逐块选择来源。生成页和预检去掉来源审计提示，保留会话范围、设置、生成动作和返回会话。
- 点击“保存笔记”直接保存当前草稿版本，不再要求勾选警告。服务继续执行结构有效性、草稿/正式版本 CAS 与 operation receipt；保存保留内部 quality 和冻结来源，不提升内部数学验证状态。旧请求中的 acknowledgement 字段继续可接收，已不构成发布门槛。
- 生成提示升级为 `session-note-article-v3`：按学习主题合并为连贯文章，来源 token/coverage 仅进入数据字段，正文不插来源编号、脚注或审计说明。保持原会话的条件和已讨论内容；没有调用真实模型验收这次提示的文章质量。
- 原句“来源追踪与结构校验不代表数学正确性”指软件检查引用能否对应原消息、数据能否按约定解析，而没有证明数学结论。它属于内部校验范围说明，不需要出现在日常笔记阅读或保存流程。实际保存失败、版本冲突及生成失败仍提供可执行的恢复动作。

## 持久会话管理

- 在原 `_conversation_events.db` 增加独立管理元数据、schema 登记及 operation receipt 表；旧会话缺省为 active、未置顶、revision 0。原消息事件、Ledger 与冻结来源不重写。
- 三点菜单提供置顶、取消置顶、整理笔记、归档、恢复和移入回收站。回收站会话保留内容与原 active/archived 状态；明确恢复后才能继续输入。没有永久删除、自动过期、资产级联清理或把置顶变为 Goal。
- 历史分最近/归档/回收站，置顶优先；完整目录按 scope 在分页前筛选，支持合并教材名称。旧不带 view 的 API 继续返回数组。游标绑定 scope 与目录代次，目录改变时明确失效，前端重新读取第一页，避免悄悄漏掉历史置顶记录。
- 管理操作使用 revision CAS 和幂等 operation_id。任务准入、消息写入、管理动作与明确结束任务共用既有单后端进程运行栅栏。运行中、等待材料/确认、可恢复中断等真实任务会阻止归档/回收站；用户可查看、继续或明确结束任务，管理动作不自动结束任务。
- 停止后的结束动作保留消息、部分输出、附件和原回执；取消后更新原 assistant 消息中的任务投影，长会话旧任务也不会继续显示失效恢复入口。无法核对的已准入写入不因结束动作而绕过。
- 备份纳入会话 SQLite、兼容 JSON 与任务 JSON；恢复校验接受旧无管理表数据库，拒绝不支持的新管理版本。代码回退时保留新表，旧消息仍可读取；旧客户端不会呈现新管理状态，不把这种能力缺失称为完整产品回退。

## 验证证据

- Python 使用现有 `venv310` / 3.10.21：主代理联合回归 **258 passed**；Sol 最终将 `DATA_DIR` / `PROGRESS_PATH` 指向新的临时目录，隔离复跑 **250 passed**（两组有重叠，不相加）。临时库覆盖旧数据缺省、CAS/幂等、超过 80 个会话的分页、任务准入竞态、重开、回收站恢复、取消后的旧消息投影，以及备份恢复后的管理状态/原消息/独立笔记数据。
- 笔记测试验证无额外 acknowledgement 的显式保存成功，回执可重复读取，内部 quality 与 warnings 完整保留，没有成为数学已验证状态。
- 前端 **31 文件 / 140 项测试通过**；TypeScript、变更文件 ESLint、生产 Vite 构建通过。保留既有 Markdown mixed import 与大 chunk 构建提示，没有新增依赖。
- 独立 macOS Electron 1280×820 使用内存 API fixture，实际点击保存笔记成功；标题下、正文右侧都没有核实/来源控件。该检查是桌面 UI 验证，不是对真实学习数据的笔记发布。
- 浏览器 fixture 实测置顶→归档→回收站→恢复原归档状态、输入禁用/恢复、结束未完成任务后重新归档及撤销。两种平台 chrome 标记、三种尺寸（1280×820、1024×768、760×820）、两个页面共 12 个布局场景：页头均 48px，无窗口横向溢出，草稿审计控件数量为 0。Windows 为布局模拟，未做原生 Windows 验证。

Sol 最终隔离复跑命令（6 条 Starlette / Swig 依赖弃用警告）：

```sh
task_validation_root=$(mktemp -d /tmp/texa-s6-validation.XXXXXX)
DATA_DIR="$task_validation_root" PROGRESS_PATH="$task_validation_root/progress" \
venv310/bin/python -m pytest -q \
  tests/test_conversation_management.py tests/test_conversation_event_store.py \
  tests/test_conversation_memory_concurrency.py tests/test_learning_task_state_machine.py \
  tests/test_agent_runtime_*.py tests/test_runtime_v0_contract.py tests/test_runtime_policy_v0.py \
  tests/test_pending_actions.py tests/test_data_backup.py tests/test_figure_learning.py \
  tests/test_mistake_image_lifecycle.py tests/test_chat_stream_reliability.py \
  tests/test_execution_details.py tests/test_session_notes.py \
  tests/test_mistake_chat_sources.py tests/test_answer_verification.py
```

此前未统一隔离环境的既有测试 observer 曾向仓库 `data/progress/runtime_events.db` 写入诊断 audit 事件；没有删除或回滚该诊断库，以免覆盖用户记录。会话、错题、笔记等真实学习资产未由这些测试修改。不能把本轮验证描述为所有数据文件零写入；最终复跑已隔离，新增会话管理测试 fixture 也禁用了 observer。

## 桌面构建交付

生产构建已合入 `frontend/dist`，入口为 `index-BGLA5Q8Y.js`；复制新资源后原子替换入口，保留旧 hash 资源供当前窗口继续加载。原构建备份在 `/private/tmp/texa-frontend-dist-before-followup-20261003`。没有强制重载或重启用户正在运行的 Texa；从本仓库启动的桌面端关闭并重开后加载新后端和页面。没有重制已安装的打包应用。

截图与布局记录：

- [干净的草稿阅读页](../artifacts/desktop-ui-refactor-2026-10-03/followup/draft-clean-1280.png)
- [原生 Electron 草稿](../artifacts/desktop-ui-refactor-2026-10-03/followup/native-draft-clean-1280.png)
- [原生直接保存后](../artifacts/desktop-ui-refactor-2026-10-03/followup/native-note-saved-1280.png)
- [回收站状态](../artifacts/desktop-ui-refactor-2026-10-03/followup/conversation-trash-1280.png)
- [12 项布局矩阵](../artifacts/desktop-ui-refactor-2026-10-03/followup/layout-matrix.json)

本次不包含真实付费模型质量、原生 Windows、安装包升级或多后端进程并发运行验收。小模型整理侧重和 Goal 长期对话仍为后续功能。
