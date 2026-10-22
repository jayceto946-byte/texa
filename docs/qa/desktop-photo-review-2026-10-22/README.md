# 桌面图片问答与照片复习验收 · 2026-10-22


## 实现与行为

- Cmd/Ctrl/Alt+A 不选择整个工作区；编辑器保留全选，阅读块保留选择与复制。
- 目标管理操作带边框并左对齐。“AI 学习任务”说明用途，执行状态只呈现一次。
- 错题筛选和管理操作同排布局，不再为空标题保留高度。
- 图片问答显示用户请求，下方紧凑缩略图；仅点击后请求原图，以可关闭、有焦点管理的 Dialog 查看。旧识别附加段不再显示为问题正文。
- 独立重做支持上传/粘贴 PNG/JPEG/WebP/BMP（20MB），上传后持久化，支持换图和移除。提交后通过现有视觉和推理角色进行一次有界批改。结构化解析材料不返回前端。
- 模型反馈仍为 unverified；用户选择本次结果后才追加一次作答事实并更新 SM-2。图片模糊/缺关键输入时保留作答状态，不先揭示答案，允许换图。失败保留图片和草稿；六分钟租约支持崩溃后主动重试，旧 run 和旧 revision 不可发布新结果。客户端也拒绝迟到的旧 revision。
- 原图与识别材料位于既有图片存储、会话 JSON 私有字段中；复习事实通过稳定引用关联。无表结构、索引、依赖或 profile 迁移。

## 工程验证

- `venv310/bin/python -m pytest -q tests/test_review_feedback.py tests/test_mistake_lifecycle.py tests/test_mistakes_api.py tests/test_mistake_image_lifecycle.py tests/test_multimodal_bridge.py tests/test_mistake_chat_sources.py`：**64 passed**。
- `npm --prefix frontend test`：**53 文件，251 passed**。
- `npm --prefix frontend run lint`：通过。
- `npm --prefix frontend run build`：通过，既有 MathLive 大 chunk 提示保留。
- `git diff --check`：通过。

日志：[后端](backend-tests.log)、[前端](frontend-tests.log)、[lint](lint.log)、[构建](build.log)。

## Electron 渲染与交互

脚本：[qa-desktop-photo-review-electron.mjs](../../../scripts/qa-desktop-photo-review-electron.mjs)。使用临时 userData、隔离本地 API 夹具和真实 Electron 生产渲染器；不访问真实学习库，不调用模型，不修改用户配置。UI 夹具模拟网络响应；后端测试独立覆盖真实存储、路由、图片验证、私有数据投影、失效租约、CAS 和幂等记录。

**77 项通过**，结果见 [results.json](results.json)。最终无页面异常或失败夹具响应。三尺寸：1280×820、1024×768、760×820。

| 内容 | 1280 | 1024 | 760 |
|---|---|---|---|
| 目标与操作 | [截图](1280-goals.png) | [截图](1024-goals.png) | [截图](760-goals.png) |
| 错题工具行 | [截图](1280-mistakes.png) | [截图](1024-mistakes.png) | [截图](760-mistakes.png) |
| 图片问答 | [截图](1280-chat.png) | [截图](1024-chat.png) | [截图](760-chat.png) |
| 原图查看 | [截图](1280-original.png) | [截图](1024-original.png) | [截图](760-original.png) |
| 图片重做 | [截图](1280-redo.png) | [截图](1024-redo.png) | [截图](760-redo.png) |
| 批改意见 | [截图](1280-feedback.png) | [截图](1024-feedback.png) | [截图](760-feedback.png) |
| 确认复习结果 | [截图](1280-feedback-confirm.png) | [截图](1024-feedback-confirm.png) | [截图](760-feedback-confirm.png) |

缩略图和原图使用用户提供的截图作为不含模型请求的图片夹具，图像本身包含旧 UI，不代表新页面泄漏旧 OCR。批改文字为离线界面样例，不是对此图片的真实批改。

初始脚本曾因沙箱端口限制、未补管理字段、启动导航竞态、异步正文/草稿等待和窄屏隐藏列表而中止；调整测试夹具及等待后重跑。公式首次几何断言也错误地把正常的 visible overflow 当作裁剪，已区分容器实际 overflow。过程截图保留在 `harness-history/`，最终结论以 results.json 和上述最终截图为准。

## 验证边界

Windows 仅在 macOS Electron 中模拟标题栏 CSS，检查 Logo 和全部子节点 no-drag 及导航；**未运行原生 Windows**。未生成安装包或发布版本。**未调用真实 OCR/推理模型，未验证在线批改准确率**；不将结构验证或离线 UI 通过称为答案准确率。主聊天仅调整显示投影，未改写历史会话或清除后台视觉证据。实际使用新接口需重新启动桌面端后端。
