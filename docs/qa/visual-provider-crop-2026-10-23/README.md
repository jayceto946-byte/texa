# 图片问答：Provider 失败诊断与裁剪显示修复

调查开始于 2026-10-23，最终验证于 2026-10-24。用户报告 iPad 远程图片问答报 `provider_request_failed`，推理模型为 `deepseek-flash`；对话仍显示裁剪前整图。

## 已确认原因

1. 图片展示接口 `/api/mistakes/tasks/{task_id}/image` 原先优先选择 `original_image_path`，即未裁剪的相机整图；识图实际读取独立的 `image_path`，即裁剪后的工作图。问题在展示选图，并非裁剪结果没有上传。默认展示、预览和放大查看现均选择识图输入；`original=true` 保留显式读取相机整图。图片响应禁止缓存，缺失工作图不偷偷回退到现有整图。
2. DeepSeek 适配器同步/异步、流式/非流式路径原先将所有 SDK 异常都压成同一个固定代码。该处理能避免回显供应商正文和私有 thinking，却丢失了 HTTP 状态、网络/超时类别。因此原来仅凭该代码不能区分网络、认证、余额、限流、配置或供应商故障。这次没有取得 Windows 远端的原始异常，不认定它必然属于某一类别，也不将其归因为上次 JSON 修复。

## 修复边界

- 原有 DeepSeek 固定错误代码、隐藏推理回放与回调脱敏合同保留，异常只附加闭集类别和合法 HTTP 状态；日志不输出 SDK 正文、密钥、图片或 reasoning。
- 图片讲解使用共享的供应商中立文本流恢复函数，展示可读错误。只对超时、连接中断和选定临时服务故障最多重新请求一次；认证、余额、参数、限流与协议完整性错误不自动重试。
- 仅在还没有输出正式答案时允许重试，避免重复输出；两次请求按同一 420 秒剩余预算分配超时，按整秒取值避免工厂缓存因微秒差异持续增长。请求前及输出时检查同一 task/run 所有权，停止后不启动下一次请求。
- 沿用已有模型角色、用户配置、视觉 IR、确定性后置验证、缺输入门槛、图片资产和持久化身份。未迁移数据库、索引或正式学习数据，未修改搁置功能，未自动重跑旧失败任务。

错误类别与参数核对使用 [DeepSeek 官方错误码](https://api-docs.deepseek.com/quick_start/error_codes/) 和 [Thinking Mode 文档](https://api-docs.deepseek.com/guides/thinking_mode/)。当前 `deepseek-flash` 的 `thinking` / `reasoning_effort=high` 参数符合公开文档，不能在没有原始状态码时认定它们是本次故障原因。

## 实测

- Python 3.10：14 个相关测试文件 **245 passed**。包含真实 DeepSeekChatOpenAI + HTTPX MockTransport 的同步/异步错误分类、503/网络/超时恢复、402/401/400/429 不重试、已输出正文不重启、停止栅栏、超时预算、协议错误、回调和日志脱敏、资源关闭错误不覆盖已交付正文。
- API/SSE：真实 multipart 上传不同尺寸与颜色的相机整图/裁剪图，验证 OCR 读取的是裁剪图，默认图片/预览/历史重开仍是裁剪图；显式整图读取和原始字节保留；恢复只有一个 user/assistant 投影，失败不误报完成。
- Electron：真实 macOS Electron，当前前端源码隔离生产构建，真实裁剪 UI → multipart → FastAPI/SSE → DeepSeek SDK（模拟 HTTP）→ 会话落盘 → 重开并刷新。1280×820、1024×768、760×820 共 **29 项通过**，无 renderer 错误。包括手柄拖拽真实改变尺寸、显示图与 OCR 输入尺寸一致、放大/刷新一致、503 后一次恢复、402 一次失败且图片保留、供应商私有正文不泄漏。已实际查看完成态和错误态截图。
- Vite 隔离构建、Python 语法和 diff 空白检查通过。没有前端生产源码修改；保留既有 MathLive 大包提示。

最终 [results.json](results.json)、[backend.log](backend.log)、[HTTP 请求](requests.json)。截图：[1280 裁剪](1280-crop.png)、[1280 完成](1280-chat.png)、[1024 完成](1024-chat.png)、[760 完成](760-chat.png)、[760 明确错误](760-error.png)。402 是合成响应，不代表用户真实账户余额不足。

## 验收脚本修正记录

前四轮脚本失败与日志保存在 `first-run/` 至 `fourth-run/`：补充代理诊断后确认是复用测试夹具仅允许 PNG、而真实裁剪输出 JPEG；随后修正自动拖拽命中手柄，以及诊断控制路由被生产 SPA catchall 截获的问题。`image-only-run/` 的图片检查通过，但部分截图停在 Markdown 懒加载骨架屏，因此不计为最终完整视觉验收；最终脚本等待正文和错误提示真正显示。没有为通过这些夹具错误而更改生产图像格式限制、裁剪 UI 或 SPA 路由。文本快照仅去除行尾空白，截图及 JSON/日志保留。

## 复现

先在 `frontend/` 执行 `npm exec -- vite build --outDir /private/tmp/texa-photo-provider-frontend`，再从项目根目录运行：

```sh
TEXA_QA_PLAYWRIGHT=/absolute/path/to/node_modules/playwright \
node docs/qa/visual-provider-crop-2026-10-23/electron.mjs
```

使用现有 venv310 与 Electron；用户数据和空 ENV_PATH 位于新建临时目录，不读取正式库。`fixture.png` 为代码生成的合成图；不发送用户图片，不调用真实付费模型。局限：未验证真实供应商、Windows/iPad 真机及安装包部署，不将工程回放等同远端故障的精确根因证明或模型数学准确率。
