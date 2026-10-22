import type { GuideStep } from './content';

export const rentedMineruStep: GuideStep = {
  id: 'rented-gpu', title: '租卡运行 MinerU', image: 'import-bundle',
  alt: 'Texa 的教材导入页；完成云端解析后选择 MinerU 输出包导入 ZIP',
  instructions: ['需要租卡时再看本节，已有输出包可直接导入。在 AutoDL 等平台租一张 4090 或 5090，选适配的 Ubuntu 镜像，在实例终端安装 MinerU。下面以 AutoDL 容器实例为例。', '上传一本 PDF，先试解析 3 页，核对公式、表格和附图，再处理整本书；按下方清单检查输出并打包。', '下载 ZIP 到自己的电脑并校验，确认实例关机，再用 Texa“教材 → 导入教材 → MinerU 输出包”导入。'],
  warning: '租卡开机期间会计费，关闭网页或断开 SSH 不会关机。以下命令按 2026-10-19 官方文档整理，未在付费实例实测；请先小样验证。教材会上传至租赁平台，只上传允许在该平台处理的材料。',
  sections: [
    {
      title: '1. 选卡、镜像与磁盘',
      paragraphs: ['登录租赁平台并按要求完成账号准备，先查看价格和预算。AutoDL 从控制台的租用入口选择容器实例、地区与主机；GPU 数量选 1，临时解析可选择按量计费，再选镜像、磁盘并创建实例。开机后从实例的 JupyterLab 打开 Terminal（终端）。SSH 也可用，但主机、端口和密码必须取自自己的实例。其他平台入口名称以实际页面为准。', '推荐单卡 RTX 4090（常见 24 GB 显存）或 RTX 5090（标准版 32 GB；D 等型号以租用页为准）。第一次可选 4090；5090 可作为较大显存的选择，实际速度和总费用要用自己的 3 页样本比较，不只看卡名。无需多卡。', '推荐 Ubuntu 22.04 LTS、x86_64、Python 3.12 的基础/PyTorch 镜像；Ubuntu 24.04 也可作为备选，但本教程未分别实测。本流程固定 MinerU 4.0.0 + vLLM 0.21.0 的 CUDA 12.9 路径，选择平台标明兼容 CUDA 12.9 的驱动环境。不要选旧 CUDA 11.x 镜像，也不要在容器内重装宿主 NVIDIA 驱动。', '建议内存至少 32 GB，数据盘预留至少 60 GB 可用空间，整本扫描书可能需要更多。AutoDL 通常用 /root/autodl-tmp 放输入、环境、模型和输出，避免填满系统盘；其他平台改成实际数据盘路径。租用前看清计费、存储和数据保留规则，并设置合适的定时关机。'],
      commands: [{ label: '实例终端：先检查环境', text: 'nvidia-smi\ncat /etc/os-release\nuname -m\npython --version\ndf -h /root/autodl-tmp' }],
    },
    {
      title: '2. 用国内源安装，独立于 Texa 环境',
      paragraphs: ['以下按顺序在新租赁实例的同一个 Bash 终端执行。重新连接或新开终端后，先回工作目录、激活 .venv 并重设下方缓存及模型环境变量，不要重新创建环境。确认上一步 Python 是 3.12、架构是 x86_64，且 nvidia-smi 能看到所租 GPU；其中 CUDA Version 表示驱动支持上限，不代表 Python 已装好 CUDA 版 PyTorch。', '系统包沿用平台预设的 Ubuntu 源；Python 包用阿里云 PyPI，模型用 ModelScope。镜像速度受地区与同步情况影响。若 Python 包缺版本，可将命令中的源换成 https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple；仍没有时查官方 PyPI，不随意取消版本约束。PyTorch 的 CUDA wheel 仍由官方源提供，国内 PyPI 不能替代它。', '这是远端 MinerU 的 Python 3.12 环境，不是本机 Texa 的 venv310。不要在 Texa 环境粘贴这些安装命令。安装失败先保留错误，不用 --no-deps 强装，也不要覆盖镜像原有 PyTorch。'],
      commands: [
        { label: '实例终端：系统依赖与工作目录', text: 'apt-get update\napt-get install -y libgl1 libglib2.0-0 fonts-noto-cjk fontconfig zip unzip\nmkdir -p /root/autodl-tmp/texa-mineru/{input,output,exports,cache}\ncd /root/autodl-tmp/texa-mineru\nexport UV_CACHE_DIR="$PWD/cache/uv"\nexport HF_HOME="$PWD/cache/huggingface"\nexport MODELSCOPE_CACHE="$PWD/cache/modelscope"\nexport MINERU_HOME="$PWD/cache/mineru"' },
        { label: '实例终端：安装固定版本', text: 'python -m pip install -U uv -i https://mirrors.aliyun.com/pypi/simple\nuv venv --python "$(command -v python)" --seed .venv\nsource .venv/bin/activate\nuv pip install "mineru[full]==4.0.0" "vllm==0.21.0" --torch-backend=cu129 --index-url https://mirrors.aliyun.com/pypi/simple\nuv pip check\npython -c "import torch; from importlib.metadata import version; print(\'MinerU\', version(\'mineru\')); print(\'Torch\', torch.__version__, \'CUDA\', torch.version.cuda); assert torch.cuda.is_available(), \'CUDA 不可用，先检查环境\'; x=torch.ones(1, device=\'cuda\'); print(torch.cuda.get_device_name(0), x.cpu())"\nuv pip freeze > exports/environment.txt' },
      ],
    },
    {
      title: '3. 下载模型，上传 PDF 并试跑',
      paragraphs: ['在 AutoDL 控制台打开该实例的 JupyterLab，进入数据盘 texa-mineru/input，用上传按钮放入一本完整 PDF，重命名为 book.pdf。大文件可用平台提供的 SFTP/SSH 信息通过 FileZilla 上传；不要把 PDF 上传到临时目录或仅粘贴本机路径。', '下面先下载并检查 Standard 所需模型，再运行 PDF 的第 1–3 个文件页。MinerU 4 的 --pages 从 1 开始，可能不同于印刷页码。模型文件检查通过还不是 OCR 成功；解压 sample.zip，对照原 PDF 检查文字顺序、上下标、公式、表格和附图。', '样本正确后运行整本命令；sample 和 full 使用不同目录，不能把试跑结果当整书导入。首次下载和首次 CUDA 编译会花时间，查看日志与 nvidia-smi；不要因暂时没有新文字就重复启动。终端断开、失败或显存不足时先核对当前任务，保留日志，不假定支持断点续传。'],
      commands: [
        { label: '实例终端：下载并检查模型', text: 'export MINERU_MODEL_SMALL_BACKEND=torch\nexport MINERU_MODEL_VLM_ENGINE=vllm\nexport MINERU_MODEL_SOURCE=modelscope\nmineru-kit models download --tier standard --small-backend torch --vlm-engine vllm --source modelscope\nmineru-kit models verify --tier standard --small-backend torch --vlm-engine vllm\nmineru-kit models show' },
        { label: '实例终端：先试 3 页，再跑整本', text: 'export MINERU_MODEL_SOURCE=local\nset -o pipefail\nmineru-kit parse input/book.pdf --tier standard --pages 1-3 --format zip -o output/sample.zip 2>&1 | tee exports/sample.log\n# 先检查样本；确认后再运行下一条\nmineru-kit parse input/book.pdf --tier standard --pages all --format zip -o output/full.zip 2>&1 | tee exports/full.log' },
      ],
    },
    {
      title: '4. 检查完整材料，再打包',
      paragraphs: ['用 JupyterLab 解压/查看，或执行下面命令；任一步报错就停止，目录已存在时换一个新的导出目录。一个包只放一本书、一次整书解析结果，不要把 sample、full、其他教材或环境目录混入同一包。不要只导出 Markdown；有插图时还需要其引用的真实图片文件，保留所有相对路径。', 'MinerU 4 的完整导出通常有 markdown.md、structured_content.json、middle_json.json 和 images/，可能另有 model_output.json；images 只在有图片资产时出现。Texa 优先读取 structured_content.json。仅有新版 middle_json 并不能保证被 Texa 识别，不能改名伪装成 content_list。旧版包可有 *_content_list.json / *_middle.json，但不要与新版不同文档混装。', '在 structured_content.json 中检查 metadata.producer.name 为 MinerU、version 为 4.x，pages 有内容，且没有 is_full_document=false。将页面数与原 PDF 对照；再人工检查最后一页确已处理。小样、缺页、缺公式或图片引用失效时先修复，不把“有 ZIP”当作解析成功。保留原 PDF 便于校对和来源阅读；下面复制为 book_origin.pdf 一并打包。', 'Texa 默认 ZIP 上限 2 GiB、解压总量 20 GiB、最多 100,000 个条目、单条目 4 GiB，部署可能另设限制。超限应缩小材料并分别导入、保留清楚名称和原页范围；不要通过更改扩展名绕过限制。'],
      commands: [
        { label: '预期结构（目录外层名称可不同）', text: 'bundle/\n  markdown.md\n  structured_content.json\n  middle_json.json\n  images/                  # 有图片时保留\n  model_output.json        # 可选，若原输出含有则保留\n  book_origin.pdf          # 自己保留的原 PDF' },
        { label: '实例终端：先解压到新的目录', text: 'unzip -t output/full.zip\nmkdir exports/book-bundle && unzip output/full.zip -d exports/book-bundle\nfind exports/book-bundle -maxdepth 3 -type f | head -60' },
        { label: '实例终端：核对结构并放入原 PDF', text: 'python - <<\'PY\'\nimport json, shutil\nfrom pathlib import Path\nroot = Path("exports/book-bundle")\nfiles = list(root.rglob("*structured_content*.json"))\nassert len(files) == 1, "应只有一本书的一份 structured_content，请先检查目录"\ndata = json.loads(files[0].read_text(encoding="utf-8"))\nproducer = data.get("metadata", {}).get("producer", {})\nassert str(producer.get("name", "")).lower() == "mineru"\nassert str(producer.get("version", "")).startswith("4.")\nassert data.get("pages"), "没有页面内容"\nassert data.get("is_full_document") is not False, "这是部分文档，不能当整书导入"\nprint("解析页数:", len(data["pages"]))\nprint("原文档元数据:", data.get("metadata", {}).get("document", {}))\nprint("整书标志:", data.get("is_full_document", "未声明，必须人工核对"))\nprint("请对照原 PDF 页数、末页、公式与图片；此检查不证明 OCR 正确。")\ntarget = files[0].parent / "book_origin.pdf"\nassert not target.exists(), "原 PDF 已存在，请先核对，不自动覆盖"\nshutil.copy2("input/book.pdf", target)\nprint("已保留原 PDF:", target)\nPY' },
        { label: '实例终端：人工检查完成后打包', text: 'cd exports/book-bundle\nzip -r ../book-mineru.zip .\ncd ../..\nunzip -t exports/book-mineru.zip\nsha256sum exports/book-mineru.zip > exports/book-mineru.zip.sha256' },
      ],
    },
    {
      title: '5. 下载到本机，然后关机',
      paragraphs: ['在 JupyterLab 中找到 exports/book-mineru.zip，右键下载；同时下载 .sha256、environment.txt 和解析日志。JupyterLab 下载的是文件，文件夹要先打成 ZIP。大文件也可用 FileZilla 的 SFTP，或在本机终端执行下方 scp。', 'scp 在自己的 Mac/Windows 终端执行，替换控制台 SSH 指令里的主机和端口；-P 是大写，密码只在交互提示中输入。下载后在本机检查 ZIP 能打开，并把 SHA-256 与下载的 .sha256 文件对照。', '确认文件已在自己的电脑后，到 AutoDL 控制台点“关机”，等实例状态变为“已关机”，并检查计费状态。关闭 JupyterLab、浏览器或 SSH 均不等于关机。只剩传文件时可按平台规则使用无卡模式；不要在无卡模式继续跑 GPU 解析。', '按量 GPU 运行费、包周期和存储费规则不同，关机后仍可能有存储费用；以租用页为准。确认本地结果与备份齐全后才考虑释放实例；释放或更换镜像可能损失云端材料，保存镜像也不等于备份数据盘。'],
      commands: [
        { label: '本机终端：SCP 下载示例（请替换主机与端口）', text: 'scp -P 12345 root@你的实例主机:/root/autodl-tmp/texa-mineru/exports/book-mineru.zip .\nscp -P 12345 root@你的实例主机:/root/autodl-tmp/texa-mineru/exports/book-mineru.zip.sha256 .' },
        { label: '本机校验：macOS 终端', text: 'shasum -a 256 book-mineru.zip' },
        { label: '本机校验：Windows PowerShell', text: 'Get-FileHash .\\book-mineru.zip -Algorithm SHA256' },
      ],
    },
    {
      title: '6. 导入 Texa，核对一次教材问答',
      paragraphs: ['回到运行 Texa 的电脑，打开“教材 → 导入教材”，选择“MinerU 输出包”。先将本机 ZIP 改为易辨认的教材名（教材名称取自文件名），选择该 ZIP 和所属科目，再点“导入输出包”。此路径复用已解析产物，不需要本机安装 MinerU，也不需要把云实例长期保持开机。', '等待最终可用状态后回教材列表，“设为学习范围”。用原书一个明确概念提问，点“查看来源”检查教材、页码、公式与附图。导入完成只表示系统接受并建立了资料，不证明 OCR 或回答完全正确。', '若提示多文档歧义、文件损坏、超限或没有正文，先检查第 4 步的结构和材料，不反复上传同一包。确认原 PDF 随包保留且来源可核对；教材导入不会自动建立练习题库。'],
    },
  ],
  result: '本机保留完整解析包和原 PDF；云实例已确认关机；Texa 中能选到教材并核对来源。',
  resources: [
    { label: 'MinerU 4 安装', url: 'https://opendatalab.github.io/MinerU/quick_start/' },
    { label: '扩展依赖', url: 'https://opendatalab.github.io/MinerU/quick_start/extension_modules/' },
    { label: '模型下载', url: 'https://opendatalab.github.io/MinerU/usage/model_source/' },
    { label: '输出包结构', url: 'https://opendatalab.github.io/MinerU/reference/output_files/' },
    { label: 'vLLM 0.21 CUDA', url: 'https://docs.vllm.ai/en/v0.21.0/getting_started/installation/gpu/' },
    { label: 'AutoDL 上传与下载', url: 'https://www.autodl.com/docs/down/' },
    { label: 'AutoDL 省钱与关机', url: 'https://www.autodl.com/docs/save_money/' },
  ],
  actions: [{ label: '导入 MinerU 输出包', to: '/books/import' }],
};
