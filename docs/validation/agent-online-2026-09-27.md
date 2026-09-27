# 2026-09-27 真实模型验证

用户明确授权付费请求及公开测试素材使用。读取 Electron 开发版保存的 `.env`，使用 Qwen `qwen3.7-plus`；学习记录与运行数据库放在临时隔离目录，未修改用户教材、错题或会话。

| 用例 | 结果 |
|---|---|
| 文本连接与数学回答 | `x^3` 的导数正确返回 `3x^2` |
| 原生工具调用 | 自动工具选择返回合法函数名与 JSON 参数；强制工具 + 默认思考参数返回 400，自动选择成功 |
| 自然语言目标整理 | 生成合法目标契约，保留“不安排期限、没有教材”的限制 |
| 有界 Goal Runtime | completed；1 次真实工具、3 次模型步骤；通过共享生成与后置验证，答案正确说明有限样本覆盖 |
| 教材函数图视觉 IR | 识别 `f(x)=x^2`、`y=6x-9`、斜率 6、切点 `(3,9)` |
| 图片 → 推理解题 | 验证共点 `(3,9)` 与 `f'(3)=6`，正确证明切线关系；输出已过滤 thinking |
| 缺失附表 | 合成传感器题明确引用缺失附录 B；视觉 IR 提出 blocking required input，领域 helper 确认阻断 |

公开教材图片来自 [OpenStax Calculus Volume 1 §3.1, Figure 3.6](https://openstax.org/books/calculus-volume-1/pages/3-1-defining-the-derivative)。图形结论与该节示例一致；这里只验证一个公开样本，不代表生产教材索引检索或总体识图准确率。

## 修复

真实验证发现原有 profile 仅凭无法从 UI 设置的 `tool_calling_verified` 门槛，仍不能启动 Goal。现在显式“测试连接”会进行一个无领域副作用的工具探针，成功后保存 30 天有效能力记录。记录绑定角色、供应商、模型、transport、endpoint、options 和凭证摘要；密钥本身不写入记录。配置变化或超时需重新验证。能力失败不影响普通文本连接，Goal 仍会拒绝未验证配置。默认聊天 Runtime 接管开关保持关闭。

本次实测成功记录已保存到开发版 `data/progress/tool_capabilities.json`。需要重启开发版后端加载新代码。相关回归 58 项通过，只有既有 Starlette deprecation warning。

初次探针脚本漏加载 `config`，导致两次 401；修正 `.env` 加载顺序后认证成功，不能将初次失败归因于用户密钥。

## 复现

以下脚本会执行付费调用；数据目录自动隔离，报告不包含凭证。测试图片需要自行从上述公开来源准备。

```sh
venv310/bin/python scripts/validate_agent_online.py \
  --allow-paid \
  --env "$HOME/Library/Application Support/kaoyan-assistant-desktop/.env" \
  --report "${TMPDIR:-/tmp}/texa-online-report.json" \
  --image "${TMPDIR:-/tmp}/openstax-figure-3-6.png"
```

原始样本输出仅保存为本地生成报告，不纳入 Git。新复现脚本提供能力、目标、Runtime 和可选图片 IR 冒烟检查；本次缺附表与图片推理解题使用隔离临时 harness 执行。

## 验收范围

尚未覆盖真实生产教材索引、实际领域写入、真实到期定时任务、原生 Electron 停止/断线/恢复交互与 20/40/80 轮人工评分 Answer Eval。当前结果是小样本真实链路验证，不是线上答案准确率认证。
