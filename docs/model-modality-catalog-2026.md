# 2026 模型模态核对（截至 2026-09-28）

Texa 的模型选择器服务于学习问答与图片题：它需要**文本输出**。本表将输入与输出分开记，避免把“支持图片输入”误写成“能生成图片”。注册表中的 `vision` 仅表示**接收图片并输出文本**；图片生成、音频、视频与实时语音接口不属于当前聊天/识图角色，不能因为它们“多模态”就加入回答模型下拉框。

这是一份按官方文档核对的当前可用型号快照，不承诺覆盖厂商在 2026 年发布的每个快照、地域、预览版和专用媒体端点。型号的供应、别名和输入限制会继续变化。未知型号按“未验证”处理，用户可用设置中的真实图片探针检查；探针只证明当前端点能正确读取测试图片，不能证明长期可用性或所有学习题型的识别质量。

| 服务商 / 2026 型号或系列 | 输入 → 输出 | Texa 注册表处理 | 核对来源 |
| --- | --- | --- | --- |
| Qwen `qwen3.8-max`、`qwen3.8-flash`、`qwen3.7-plus`、`qwen3.7-flash`、`qwen3.6-plus/flash`、`qwen3.5-plus/flash` | 文本、图片（部分还接受视频）→ 文本 | 可作为单模型或识图模型 | [阿里云视觉理解](https://help.aliyun.com/zh/model-studio/vision-model/) |
| Qwen `qwen3.7-max-2026-05-20` 与 `qwen3.7-max-2026-06-08` | 前者文本 → 文本；后者文本、图片 → 文本 | 不以同系列名称推断能力；暂不预置快照 | [阿里云模型更新](https://help.aliyun.com/zh/model-studio/newly-released-models) |
| DeepSeek `deepseek-v4-pro`、`deepseek-flash` | Pro 文本 → 文本；Flash 文本、图片 → 文本 | Pro 仅回答；Flash 可识图。旧 `deepseek-v4-flash` 为兼容项，不将其能力按新别名推断 | [DeepSeek 型号与价格](https://api-docs.deepseek.com/quick_start/pricing/)、[视觉接口](https://api-docs.deepseek.com/guides/vision/) |
| Moonshot `kimi-k2.5`、`kimi-k2.6` | 文本、图片 → 文本 | 可识图；K2.6 的公开视觉基准与 API 使用说明需结合当前端点探针复核 | [K2.5 平台说明](https://platform.moonshot.ai/docs/guide/prompt-best-practice)、[K2.6 官方公告](https://forum.moonshot.ai/t/meet-kimi-k2-6-advancing-open-source-coding/369) |
| Google `gemini-3.8-flash`、`3.7-flash`、`3.6-flash`、`3.5-flash` | 文本、图片等 → 文本 | 可识图；当前 Texa 只调用图片输入/文本输出路径 | [Gemini 型号目录](https://ai.google.dev/gemini-api/docs/models)、[3.8 Flash 规格](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) |
| OpenAI `gpt-5.6-sol/terra/luna`、`gpt-5.4-mini` | 文本、图片 → 文本 | 可识图 | [OpenAI 模型目录](https://platform.openai.com/docs/models) |
| Anthropic Claude 4.6/4.7 等当前 Claude 模型 | 文本、图片 → 文本 | 已调研，暂不增加内置 Provider；官方 OpenAI SDK 兼容层主要用于测试比较，严格工具 schema 会被忽略，Texa 的受控工具流程不能据此宣称完整生产兼容 | [Claude 型号目录](https://platform.claude.com/docs/en/models/overview)、[兼容层限制](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk) |
| 专用图像/音频/视频生成模型（如 GPT-Image、Gemini Image/Live、Qwen-Image） | 输入或输出含图片、音频、视频，常非文本回答 API | 不加入问答模型选择器；未来若增加生成媒体工作流须单独设计接口、权限、预算与验证 | [OpenAI 模型目录](https://platform.openai.com/docs/models)、[Gemini 模型目录](https://ai.google.dev/gemini-api/docs/models)、[阿里云模型目录](https://help.aliyun.com/zh/model-studio/models) |

## 自定义模型能力检查

OpenAI-compatible 自定义服务复用 `/api/system/settings/models/test` 的 `vision` 角色和生产图片请求路径，发送一张本地生成的八条色带 PNG，不包含教材或用户图片。色带顺序随机；只有模型按顺序正确回答时才显示成功。API Key 只用于该次请求且错误信息会脱敏。失败可能来自网络、鉴权、接口格式或识别失误，不等同于型号永久不支持图片。识图测试由用户显式点击，可能产生少量供应商费用；保存配置仍不强制要求测试成功。
