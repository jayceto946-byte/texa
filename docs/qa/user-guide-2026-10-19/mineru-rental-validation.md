# 租卡 MinerU 教程补充与证据边界

日期：2026-10-19；当前 `Texa_MacOS` 工作树。教材学习增加可选“租卡运行 MinerU”步骤；仍保留四个主场景。当前共 14 步、23 个步骤内功能操作。

内容包含选卡与 Ubuntu/Python/CUDA 镜像、独立环境安装、国内包源及模型源、GPU 自检、上传与三页试跑、整书导出、结构检查、原 PDF、打包与校验、JupyterLab/SCP/SFTP 下载、控制台关机与存储费用、Texa 导入及来源核对。

命令限定为 MinerU 4.0.0 / vLLM 0.21.0 / CUDA 12.9；不是让用户混用 MinerU 3 的 `-p/-o`、`core/all` extras 或零起始页码。4 的 `mineru-kit parse --format zip` 与 native structured_content 有当前 Texa 适配入口。只给云实例安装说明，未修改 Texa 依赖或 `venv310`。

## 来源（均为官方，核对于本日）

- [MinerU 4 快速开始](https://opendatalab.github.io/MinerU/quick_start/) 与 [扩展模块](https://opendatalab.github.io/MinerU/quick_start/extension_modules/)：4.x 安装入口、Python 和 extras；用户教程固定稳定版本，不引用浮动 master 安装。
- [MinerU 模型来源](https://opendatalab.github.io/MinerU/usage/model_source/)：ModelScope、独立 small/VLM backend、下载、verify 与 local 推理。
- [MinerU CLI](https://opendatalab.github.io/MinerU/usage/cli_tools/)：完整文档/样本页、命令参数。4 的 `mineru` 文档库入口可能只处理前 10 页，故教程使用 `mineru-kit parse --pages all`。
- [MinerU 输出合同](https://opendatalab.github.io/MinerU/reference/output_files/)：ZIP 保存的结构、图片资源；不把新版 middle JSON 改名为旧 content_list。
- [vLLM 0.21 安装](https://docs.vllm.ai/en/v0.21.0/getting_started/installation/gpu/)：默认 CUDA 12.9 二进制、新虚拟环境与 Torch ABI 约束。Ubuntu、内存与磁盘数值是本教程的配置建议，并非平台库存或实测性能承诺。
- [NVIDIA RTX 4090](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4090/)、[RTX 5090](https://marketplace.nvidia.com/en-us/consumer/graphics-cards/nvidia-geforce-rtx-5090/)：标准版显存。实际租赁 D/定制型号须看平台信息，无价格和速度倍数承诺。
- [AutoDL 下载](https://www.autodl.com/docs/down/)：JupyterLab 先打包文件夹、SCP 在本机运行及大写 `-P`；SFTP 按平台提供的信息使用。
- [AutoDL 存储](https://www.autodl.com/docs/dir/)、[镜像](https://www.autodl.com/docs/image/)、[省钱](https://backup.autodl.com/docs/save_money/)：数据盘与系统盘区分、保存镜像不等于保存数据盘、关机与无卡模式。教程不保证关机后零费用或永久保留。
- [清华 PyPI 镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)：HTTPS 镜像地址，包镜像与 CUDA wheel、模型下载是不同来源。

## 本地代码核对

- `ingestion/mineru_structured.py`：MinerU 4 producer、pages/blocks 校验与原生 Canonical 适配。
- `ingestion/document_adapters.py`：原生 structured 优先；跨目录混放文档会被拒绝；旧版 content_list/middle 的结构不同。
- `backend/api/books.py`：ZIP 解压与输出根目录探测；原 PDF 必须随所选输出目录可见。教程将原 PDF 放在 structured JSON 同目录，兼容 ZIP 内嵌一层目录。
- `utils/resource_limits.py`：默认 ZIP 2 GiB、解压 20 GiB、100,000 条目、单条目 4 GiB；部署可通过环境变量调整。
- `frontend/src/pages/BooksPage.tsx`：输出包教材名取 ZIP 文件名，用户选择科目后“导入输出包”；不编造名称输入框或远程 GPU 常驻要求。

## 验证与未验证

前端构建/lint、235 项现有测试通过；Python 3.10 的原生 MinerU / 外部输出导入 / DocumentAdapter 合同 27 项通过。教程 Bash 块只做 `bash -n` 语法检查；结构检查块用标准库在临时合成材料上验证，不启动 GPU、不证明 OCR 正确。

Electron 最终 113 项检查通过（含全部 23 个功能操作入口、三个窗口尺寸与复制）；具体结果见 results.json。

界面证据使用隔离 macOS Electron、只读示例 API；检查六阶段阅读、长命令内部滚动、原文复制与导入路径。Texa 输出包页是真实界面截图；没有伪造 AutoDL 控制台截图、远端终端成功日志或计费回执。实际截图与逐项结果见同目录 JSON/PNG。

付费租卡、真实远端安装/模型下载/解析、平台网络与计费、实例关机及候选发行包端到端导入均未执行。原 V01–V18 不变，新增 V04-G1–G6 全部保持未测，详见 [release-checklist.md](release-checklist.md)。
