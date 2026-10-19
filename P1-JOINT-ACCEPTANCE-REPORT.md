# P1 教材打包与 Agent 完成交付：联合验收与合入回执

日期：2026-10-19（Asia/Shanghai）。

**工程集成与本轮最小验收 PASS，已合入本地 Texa_MacOS；整题独立数学核验与完整教学发布仍 HOLD。** 没有推送远端、扩大默认预算、重建索引、修改OCR或扩展路由功能。

## 1. 提交与目标工作区

| 项目 | 身份 |
|---|---|
| 共同基线 | `655aa481743b20e24eaab52f5f75d141b4db83dc` |
| 教材A最终分支提交 | `077e168b9fb0771abfc64e4854d818836cf83f23`（含实现 `4e1b385`） |
| Agent B最终分支提交 | `91d774539d0cb1c45d248f0a41639e57bf8cddd1`（含实现 `3574537`） |
| 顺序集成提交 | `9955a6c0c54c061f8c7f6bcf09bf39a5f8f53d25` |
| 本轮修复及验收证据提交 | `2e6c35602b48c73e158f9de5e80d716bc13a5b7e` |
| 集成分支 | `integration/p1-context-agent-joint` |
| 集成工作区 | `/Users/jichengqian/Documents/Codex/2026-10-19/referenced-chatgpt-conversation-this-is-an/work/texa-joint` |
| 目标工作区/分支 | `/Users/jichengqian/Documents/ChatGPT/texa` / `Texa_MacOS` |
| 目标合入前 | `ac071baca0382bdfefece0c1a2b693105dced8a7` |
| 原工作区可恢复快照 | stash `38f5551c623ccf54875d838c732de4a2f67d0358`，保留未删除 |

本报告和收尾元数据另作文档提交，最终HEAD由交付回执提供，避免文件自引用自身SHA。共同基线的P1-A/B/C、候选题合同及可靠性依赖完整纳入，未孤立拣取两个修复到旧主线。

原工作区57个既有文件逐项核对：53个字节一致；`backend/api/exercises.py`、`backend/schemas.py`、`memory/exercise_bank.py` 的三方合并结果与已验集成代码一致，原变更均已包含；`patch_notes.md` 同时保留Agent记录与原侧栏记录。7个独立界面文件及原侧栏记录保持未暂存、未提交；其他未跟踪文档、脚本、截图包保留。重复的原未跟踪文件已随基线成为正式文件，内容一致，没有覆盖为旧版。见 `docs/qa/p1-joint/target-integration.json`。

恢复快照时仅变更记录冲突；最终针对单一已定位区间保留双方。自动审批曾拒绝全文件删除分隔线的命令，该命令未执行，改用限定区间合并后通过。没有 reset --hard、clean 或删除原工作。

## 2. strict final 最小修复

原报告“252 passed / 1 deselected”对应的既有三行测试此前已独立复现为252 passed / 1 failed。根因是先验证模型正文，再追加computed-only核验说明，最终发布正文不再满足三行约束。

本轮仅改变 `native_loop` 的交付拼接：

- 在最终验证前确定现有严格格式要求。
- 严格格式不额外拼接核验说明或阶段推导；computed-only披露继续进入verification、SQL、SSE及现有执行记录。
- 普通回答的核验说明在最终验证前加入正文；阶段推导仍不用于充当最终答案的核验证据。
- computed不升级verified；缺核验仍degraded/unverified，预算失败仍failed/error且不产生成功消息回执。

没有改验证器、数学worker、工具预算、模型协议或前端产品代码。原三行断言未删除或放宽，补充JSON/纯文本及核验状态投影检查。原三行正文在SQL/SSE中逐字保留；现有Markdown对软换行的视觉排版不在本轮修改范围，不将截图的连续排版称为视觉三行格式验收。

## 3. 联合确定性与桌面验证

| 范围 | 实际结果 |
|---|---|
| 两报告去重后的26个相关Python测试文件 | **384 passed，0 failed，0 deselected**，51.51秒 |
| 相关前端 | **32 passed**：原31项范围加既有状态标签测试 |
| TypeScript / Vite | PASS；保留既有大chunk提示 |
| Electron壳 | **24 passed** |
| 实际macOS Electron，隔离SQL/SSE脚本回放 | **11项检查 PASS**，无renderer异常 |
| 合入目标后的直接相关后端复验 | **67 passed**：strict final、预算联合、候选题合同 |
| 合入目标后的相关前端复验 | **43 passed**：上述范围加候选题操作 |
| 合入目标后的TypeScript / 前端构建 | PASS |

这些集合有重叠，不能相加作为独立总量。未重跑全仓库或完整P1 Benchmark。

桌面使用真实Electron/preload、合并版本的React页面和真实临时Runtime/SQL/SSE回放，通过既有会话链接加载：degraded/unverified显示“部分内容尚未验证，需要核对”；预算失败显示“回答中断”；既有精确通过对照显示“处理完成”。没有把局部执行的绿色完成图标当整题verified。该桌面验收使用脚本Provider，不冒充付费模型Electron全链路。

初次壳测试回环绑定被沙箱拒绝，取得本机回环执行权限后24项通过。前端第一次因复用依赖目录的Vite配置缓存写入受限失败，改用runner加载且关闭缓存后通过，没有改依赖。桌面夹具先后修正失败输出无成功outbox、会话URL加载和等待Markdown异步渲染的假设；通过对照采用既有精确原题，带额外标点的版本保留unverified，未改验证器。失败经过保留在validation.json说明及渲染中截图，不混入最终PASS计数。

## 4. 真实教材C复跑

仍是《传感器原理及应用》第2版、index `c8b6947edb7858f2`、Canonical hash `89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`，锚点 `e62ed1070495dd21e981`。

| 项目 | 旧Base | 合并版本 |
|---|---:|---:|
| 单元展开 | 39块/3207字符 | 相同 |
| 最终原文 | 72字符 | 18个连续块/1537字符 |
| 可见片段（含限制提示） | 381字符 | 1846字符 |
| 式(1.5)–(1.11) | 0个真实公式 | 全部7式逐字进入最终消息 |
| 元数据 | 无连续推导 | 6601字节，保守预留6605≤8000 |
| ToolResult / chat checkpoint | 旧失败 | 15976 / 27533字符，均在原上限内 |
| 完整度 | partial | partial/source unknown |

最终human消息hash仍为 `8820d0ff5f3525281bb630329a615a3a264812eaeb317865aec01ba5a0fcd47c`。受控preceding/continuation可读完39块，但不同时塞入一次模型请求；普通短问答正文与Base相同。旧v2工具合同、版本变更、同单元及恢复栅栏由相关回归覆盖。原图/公式缺陷、未读图片和OCR来源未知继续保留，没有写生产教材或学习数据库。

## 5. 三项有限DeepSeek复验

用户明确批准具体C/B/AB片段发送到 `api.deepseek.com` 后执行。第一次外发申请被自动审批拒绝且未执行、0请求；没有绕过。模型 `deepseek-flash`，temperature=1、thinking enabled、reasoning_effort=high、max_tokens=8192、自动重试0。固定工具准备和数学共享**总预算3**；验收模型请求上限每任务2次、全轮6次，实际5次。

| 任务 | HTTP | 实际工具数（含检索） | 总tokens | 端到端 | 结果 |
|---|---:|---:|---:|---:|---|
| C 最小二乘 | 1 | 1 | 9752 | 29.74秒 | 连续讲解七式，指出(1.9)应对b求偏导；run completed、task degraded/unverified |
| B 灵敏度 | 2 | 3 | 12414 | 20.40秒 | 7/30≈0.233 Ω/°C、200–290°C范围及线性/外推限制；run completed、task degraded/unverified |
| AB 闭区间最值 | 2 | 3 | 14107 | 25.58秒 | 连续性、驻点/不可导点/端点比较完整，最大18/最小−18；run completed、task degraded/unverified |
| 合计 | **5** | 7 | **36273** | — | 没有预算中断、没有整题verified |

输入23696、输出12577 tokens；输出包括Provider报告的reasoning tokens，只保留计数，不落盘隐藏推理。没有额外模型评委或付费重跑。

B执行calculate(7/30)，再核验 `(328-307)/(290-200)=7/30`。局部残差0不认证表格、单位、建模或全题；最终仍提示结论绑定缺口。

AB执行导数恒等式核验，再用**现有合法标量表达式**核验四项代入残差平方和为0；两次回执均成功，无tuple/list输入，没有新增批量接口。第二项是一条聚合等价关系，并非四份独立回执；候选点完整性和最值存在性仍由教材与推导说明，不能升级为整题verified。两真实工具样本均没有精确缓存复用命中，不能把观察到的收敛归因于缓存。

C明确分开教材条件与自行补充的代数条件，指出式(1.4)未见、图片未读，未把统计假设冒充原文。本轮已实际阅读三项公开最终回答；它们只证明本次有限样本，不证明稳定完成率或长期模型行为。

AB结果和摘要成功保存后，旧合成语料helper对进程内manifest读取器的替换导致末尾 `sensor.sources()` 后检查失败，脚本退出1。模型任务本身已completed，该脚本异常不作模型失败，也没有付费重跑。随后直接重新计算四个真实来源文件hash，确认全部不变；收尾脚本已改为直接hash检查。见 `source-integrity-postcheck.json`。

## 6. 入口与发布边界

生产 `try_chat_response` 的教材answer route当前候选工具为空，仅固定准备 `search_textbook v3`；AB/B配置探针确认总预算3，0模型请求。这是已有路由边界，本轮未扩展。

上述付费验收沿用既有有界native数学候选和固定检索harness，只把预算值固定为生产的3；它覆盖合并后的打包、数学回执、原生协议、SSE与终态，**不等于生产主聊天已开放教材+数学工具联合能力**。离线旧批次在3预算下证明AB超额计划正确拒绝并闭合未执行ID，B两次数学操作能用完预算后直接交付。

`run completed` 是执行/交付结束，`task degraded` 是任务门槛有缺口，`verification unverified/passed=false` 是独立支持不足；SSE final事件不等于整题通过。桌面保持该区分。

尚未验或仍有限制：完整生产混合检索、正式KG语义分类、真实视觉、付费Electron端到端/重启恢复、自然语言数学结论的完整核验绑定、模型稳定成功率。式(1.9)源图标记问题及图资源绑定缺口继续作为独立数据/视觉限制。工程合入不解除原教学发布HOLD。

## 7. 证据与复跑

公开证据：`docs/qa/p1-joint/`。真实教材正文、公开模型请求/回答及临时数据库仅在 `/private/tmp/texa-p1-joint-20261019/`，未提交教材正文或凭证。公开证据已检查无密钥模式、Bearer值或reasoning_content字段。

`scripts/accept_p1_joint.py` 默认仅确定性运行；显式 `--case` 才请求模型，并使用持久请求账本及单样本防重复。已有三项样本不自动重跑。脚本读取已存专用profile到进程，不改全局配置。`scripts/qa-p1-joint-electron.cjs` 使用隔离临时数据目录与本机端口，回放合成任务，不调用付费模型。

最终报告文档提交后，目标分支仅再快进该文档提交；不暂存原界面改动、不删除安全stash、不推送远端。
