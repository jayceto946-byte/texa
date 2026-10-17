# F3 — 安全读取题库图片（P1，建议首先实施）

状态：独立待办，未实施。Astra 接受的 path-only 不可读提示继续有效。

用户价值：图片题缺少原图就无法完整作答；收益高于增加生成入口。为 F2 的附件编辑建立基础。

当前能力：`ExerciseRecord.image_path` 为可选本地字符串，另有 `ocr_text`、Markdown 正文及来源；题库没有按 exercise 身份读取图片的端点。Markdown URL 能渲染不等于任意本地路径能读取。错题已有 `/{id}/image`、`/{id}/attachments/{attachment_id}`，由记录关联文件，`resolve` 后检查归属 `IMAGES_PATH/mistakes`；全局 `LocalApiBoundaryMiddleware` 管理桌面 Token 和本机来源。Electron 开启正式 preload/网络边界，渲染层不能任意读磁盘。错题上传允许 PNG/JPG/JPEG/WebP/BMP（20MB 限额），这些限制不是尚不存在的题库资源合同。

技术阻断：旧 path 可能是外部、Windows、失效或跨设备路径；不能直接用请求 path 拼接 FileResponse，也不能将旧路径当成授权证明。当前快照的16条真实题库记录没有 image_path，尚不能证明旧图片迁移效果。

推荐最小方案：将用户明确选择/导入的图片复制进题库专属托管目录，记录稳定 asset ID、所属 exercise、类型/大小/hash 与 provenance；迁移时只允许明确授权的受控根，不自动扫描任意磁盘。新增按 exercise ID + asset ID 查关联的鉴权资源端点，校验规范路径、符号链接、文件类型/大小和所属关系。前端用现有 authenticated blob hook 加载；404/403/损坏保留不可读提示和重新关联入口。备份包含托管附件，跨设备恢复保留 asset ID 与校验值；不依赖源机器绝对路径。原图与压缩预览分离。

涉及模块：`memory/exercise_bank.py`、`backend/api/exercises.py`、`backend/services/mistake_images.py`（借鉴边界，按需抽取）、`backend/security.py`、`frontend/src/hooks/useAuthenticatedBlobUrl.ts`、`ExerciseReader.tsx`、导入候选/备份服务、Electron 打包资源验证。

风险：路径越权、软链接逃逸、超大图片、备份遗漏、跨设备路径失效、原图与 OCR 不匹配。若需新增 schema/迁移，先提交具体方案获得批准。本轮不执行迁移。

工作量：约3–5工程日，另需 macOS/Windows 数据与安装包验收；不是工期承诺。

验收标准：鉴权拒绝和跨记录拒绝；路径穿越/软链接/外部路径拒绝；受支持类型与超限拒绝；损坏/丢失有真实降级；真实图片与公式题在1280/1024/760可阅读；跨设备备份恢复后仍绑定同一图片；不上传第三方平台、不读取未授权文件。生产图片样本另行准备。

依赖：复用既有鉴权/备份；F2 附件编辑依赖本合同；F1 若需图片理解，也先依赖完整输入身份。
