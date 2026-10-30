# Texa 项目文档

日常集成与桌面交付使用 `Texa_MacOS`。开发约定见 [AGENTS.md](../AGENTS.md)，版本变化和验证结果见 [版本记录](patch_notes.md)。

## 使用与部署

- [用户指南](user-guide.md)
- [新机器部署](new_user_deploy.md)、[macOS arm64 构建](macos_arm64_build.md)、[Docker 部署](docker_deploy.md)
- [MinerU 解析部署](mineru_deploy.md)、[手机连接](mobile-remote-s0-guide.md)
- [桌面更新](desktop-auto-update.md)、[Commit 更新通道](commit-update-operations.md)
- [数据安全](data_safety.md)、[发布与恢复](release_security_and_recovery.md)、[用户数据迁移](user-data-migration.md)

## 架构与合同

- [目录说明](project_layout.md)、[架构交接](ARCHITECTURE_HANDOFF.md)
- [发展目标与实施入口](texa-development-handoff-2026-10-06.md)
- [Runtime、证据与上下文设计](semantic-runtime-evidence-context-design-2026-10-05.md)
- [Runtime RFC](agent-runtime-rfc.md)、[RuntimeEvent](runtime-event-v1.md)
- [工具调用合同](tool-calling-contract.md)、[工具合同 v1](contracts/runtime-tools-v1.md)
- [ONNX 嵌入运行时](embedding-runtime.md)、[问题理解接口](question-understanding-interface-2026-10-04.md)
- [习题候选合同](design/question-candidate-contract-2026-10-17/candidate-contract-specification.md)
- [QA 运行说明](qa/RUN-QA.md)、[API 清单](qa/API-ENDPOINTS.md)

## 图标设计探索

- [图标审计与库存](design/TEXA-ICON-AUDIT.md)、[初步规范与运行入口](design/TEXA-ICON-SPEC.md)、[三方向评审](design/TEXA-ICON-EVALUATION.md)
- 原型：前端开发服务的 `/icon-design.html`，与正式业务入口隔离；已确认的 A 图标通过统一组件接入正式工作区，B/C 保留为探索。

## 历史材料

阶段计划、实验报告和审计记录保存在本地 `docs/archive/`，不进入 GitHub、干净源码导出或 Docker 构建。归档按原仓库路径保存；本地整理报告与逐文件清单位于 `docs/archive/repository-cleanup-2026-10-28/`。

现有代码、维护脚本、CI、长期文档引用或冻结评测复现仍依赖的材料保留原位。`docs/patch_notes.md` 中的旧路径属于当时的历史记录；原位文件已归档时，可在本地归档的相同路径查阅，或从 Git 历史恢复。已搁置材料继续遵守 AGENTS.md 的保留边界。
