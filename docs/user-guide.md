# Texa 用户指南

在应用侧栏打开“用户指南”，可按步骤阅读、放大截图并前往对应页面。本文是内置指南的文字版，按当前 `Texa_MacOS` 代码与 UI 整理（2026-10-19）。截图使用真实 Electron 界面和隔离示例资料，不代表真实模型、云 GPU 或发行包端到端验收。

## 第一次学习

连接模型，问一个问题，留下可复习的笔记。没有教材也可以开始。

### 连接回答模型

1. 首次打开时按引导连接；以后在“设置 → 模型连接”修改。选择服务商和模型，填写 API Key（模型服务的访问密钥）。自定义服务还需填写服务地址和 Model ID。
2. 按当前方案使用“测试文字连接”或“测试识图能力”，检查反馈；再点“保存并继续”或“保存并应用”。
3. 回到“学习”发一条问题，确认能收到回答。

**请留意：** 测试不会保存配置，也可能产生服务费用。文字测试通过不代表能识图；图片题需另测识图能力。远程模型或解析服务会接收该功能所需的内容。

**完成后：** 收到一次实际回答，才完成这次连接检查。

### 问清楚，再核对

1. 写明对象、条件和想得到的结果，例如“解释导数的几何意义，并举一个例子”。Enter 发送，Shift+Enter 换行。
2. 有教材时先确认右上角范围；读回答后点“查看来源”，对照原文核对定义、公式、单位和使用条件。
3. 继续追问不清楚的一步；换主题可新开会话。缺附图、附表或另一页时，沿原任务补充图片。

**请留意：** 普通问答没有教材依据；来源也不保证答案完全正确。遇到未核实、依据不足或降级提示，先补材料、核对范围。停止或断线后回原任务查看继续入口。

**完成后：** 知道回答依据什么，以及哪些条件仍需核对。

<details><summary>图片、公式与待确认操作</summary>

底部“图片”加入完整题图，“教材图”选择已有插图，“公式”填写模板或矩阵。发送前检查题干、附表、括号和单位。补充材料按图片使用，不是通用 PDF/Word 附件入口。记录写入提案须由你确认，模型文字不会自动成为学习记录。

</details>

### 把讨论保存为笔记

1. 在学习会话的三点菜单选择“整理为笔记”。选择全部会话或部分轮次，再生成草稿。
2. 检查并编辑标题与正文，点“保存笔记”。
3. 到“笔记 → 已保存”重新打开；以后编辑正式笔记，要点“保存修改”。

**请留意：** “草稿已保存”不等于正式笔记。后续聊天不会自动添进笔记；生成失败或版本冲突时先保留自己的修改，再按提示处理。

**完成后：** 在“已保存”中能重新读到这篇笔记。

## 教材学习

让一本教材可用于回答，再带着明确范围提问。

### 按文件类型导入

1. 先在 PDF 阅读器中试着复制一段正文。能复制文字：选“PDF 教材”、文件、科目和“本地文本提取”。
2. 扫描件或复杂版面：仅在 MinerU 可用时选“MinerU 解析”；已有解析结果可选“MinerU 输出包”，上传保留原目录结构的完整 ZIP。
3. 点“开始导入”，等最终可用状态，再到教材列表检查。

**请留意：** 本地文本提取不做 OCR；扫描件没有可用解析条件时先准备条件。目录页范围按文件页序填写，可能不同于印刷页码。导入完成不保证公式、表格和 OCR 正确，关键内容仍需对照原页。

**完成后：** 教材出现在列表中，并显示可用于学习。

<details><summary>导入中断或概念抽取失败</summary>

“正在准备”不等于已经可检索。概念抽取是可选后续步骤，失败不一定需要重导整本书。退出或重启后的导入恢复尚未完成发行包验证，不要假定支持断点续传。

</details>

### 租卡运行 MinerU

1. 需要租卡时再看本节，已有输出包可直接导入。在 AutoDL 等平台租一张 4090 或 5090，选适配的 Ubuntu 镜像，在实例终端安装 MinerU。下面以 AutoDL 容器实例为例。
2. 上传一本 PDF，先试解析 3 页，核对公式、表格和附图，再处理整本书；按下方清单检查输出并打包。
3. 下载 ZIP 到自己的电脑并校验，确认实例关机，再用 Texa“教材 → 导入教材 → MinerU 输出包”导入。

**请留意：** 租卡开机期间会计费，关闭网页或断开 SSH 不会关机。以下命令按 2026-10-19 官方文档整理，未在付费实例实测；请先小样验证。教材会上传至租赁平台，只上传允许在该平台处理的材料。

#### 1. 选卡、镜像与磁盘

登录租赁平台并按要求完成账号准备，先查看价格和预算。AutoDL 从控制台的租用入口选择容器实例、地区与主机；GPU 数量选 1，临时解析可选择按量计费，再选镜像、磁盘并创建实例。开机后从实例的 JupyterLab 打开 Terminal（终端）。SSH 也可用，但主机、端口和密码必须取自自己的实例。其他平台入口名称以实际页面为准。

推荐单卡 RTX 4090（常见 24 GB 显存）或 RTX 5090（标准版 32 GB；D 等型号以租用页为准）。第一次可选 4090；5090 可作为较大显存的选择，实际速度和总费用要用自己的 3 页样本比较，不只看卡名。无需多卡。

推荐 Ubuntu 22.04 LTS、x86_64、Python 3.12 的基础/PyTorch 镜像；Ubuntu 24.04 也可作为备选，但本教程未分别实测。本流程固定 MinerU 4.0.0 + vLLM 0.21.0 的 CUDA 12.9 路径，选择平台标明兼容 CUDA 12.9 的驱动环境。不要选旧 CUDA 11.x 镜像，也不要在容器内重装宿主 NVIDIA 驱动。

建议内存至少 32 GB，数据盘预留至少 60 GB 可用空间，整本扫描书可能需要更多。AutoDL 通常用 /root/autodl-tmp 放输入、环境、模型和输出，避免填满系统盘；其他平台改成实际数据盘路径。租用前看清计费、存储和数据保留规则，并设置合适的定时关机。

实例终端：先检查环境

```bash
nvidia-smi
cat /etc/os-release
uname -m
python --version
df -h /root/autodl-tmp
```

#### 2. 用国内源安装，独立于 Texa 环境

以下按顺序在新租赁实例的同一个 Bash 终端执行。重新连接或新开终端后，先回工作目录、激活 .venv 并重设下方缓存及模型环境变量，不要重新创建环境。确认上一步 Python 是 3.12、架构是 x86_64，且 nvidia-smi 能看到所租 GPU；其中 CUDA Version 表示驱动支持上限，不代表 Python 已装好 CUDA 版 PyTorch。

系统包沿用平台预设的 Ubuntu 源；Python 包用阿里云 PyPI，模型用 ModelScope。镜像速度受地区与同步情况影响。若 Python 包缺版本，可将命令中的源换成 https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple；仍没有时查官方 PyPI，不随意取消版本约束。PyTorch 的 CUDA wheel 仍由官方源提供，国内 PyPI 不能替代它。

这是远端 MinerU 的 Python 3.12 环境，不是本机 Texa 的 venv310。不要在 Texa 环境粘贴这些安装命令。安装失败先保留错误，不用 --no-deps 强装，也不要覆盖镜像原有 PyTorch。

实例终端：系统依赖与工作目录

```bash
apt-get update
apt-get install -y libgl1 libglib2.0-0 fonts-noto-cjk fontconfig zip unzip
mkdir -p /root/autodl-tmp/texa-mineru/{input,output,exports,cache}
cd /root/autodl-tmp/texa-mineru
export UV_CACHE_DIR="$PWD/cache/uv"
export HF_HOME="$PWD/cache/huggingface"
export MODELSCOPE_CACHE="$PWD/cache/modelscope"
export MINERU_HOME="$PWD/cache/mineru"
```

实例终端：安装固定版本

```bash
python -m pip install -U uv -i https://mirrors.aliyun.com/pypi/simple
uv venv --python "$(command -v python)" --seed .venv
source .venv/bin/activate
uv pip install "mineru[full]==4.0.0" "vllm==0.21.0" --torch-backend=cu129 --index-url https://mirrors.aliyun.com/pypi/simple
uv pip check
python -c "import torch; from importlib.metadata import version; print('MinerU', version('mineru')); print('Torch', torch.__version__, 'CUDA', torch.version.cuda); assert torch.cuda.is_available(), 'CUDA 不可用，先检查环境'; x=torch.ones(1, device='cuda'); print(torch.cuda.get_device_name(0), x.cpu())"
uv pip freeze > exports/environment.txt
```

#### 3. 下载模型，上传 PDF 并试跑

在 AutoDL 控制台打开该实例的 JupyterLab，进入数据盘 texa-mineru/input，用上传按钮放入一本完整 PDF，重命名为 book.pdf。大文件可用平台提供的 SFTP/SSH 信息通过 FileZilla 上传；不要把 PDF 上传到临时目录或仅粘贴本机路径。

下面先下载并检查 Standard 所需模型，再运行 PDF 的第 1–3 个文件页。MinerU 4 的 --pages 从 1 开始，可能不同于印刷页码。模型文件检查通过还不是 OCR 成功；解压 sample.zip，对照原 PDF 检查文字顺序、上下标、公式、表格和附图。

样本正确后运行整本命令；sample 和 full 使用不同目录，不能把试跑结果当整书导入。首次下载和首次 CUDA 编译会花时间，查看日志与 nvidia-smi；不要因暂时没有新文字就重复启动。终端断开、失败或显存不足时先核对当前任务，保留日志，不假定支持断点续传。

实例终端：下载并检查模型

```bash
export MINERU_MODEL_SMALL_BACKEND=torch
export MINERU_MODEL_VLM_ENGINE=vllm
export MINERU_MODEL_SOURCE=modelscope
mineru-kit models download --tier standard --small-backend torch --vlm-engine vllm --source modelscope
mineru-kit models verify --tier standard --small-backend torch --vlm-engine vllm
mineru-kit models show
```

实例终端：先试 3 页，再跑整本

```bash
export MINERU_MODEL_SOURCE=local
set -o pipefail
mineru-kit parse input/book.pdf --tier standard --pages 1-3 --format zip -o output/sample.zip 2>&1 | tee exports/sample.log
# 先检查样本；确认后再运行下一条
mineru-kit parse input/book.pdf --tier standard --pages all --format zip -o output/full.zip 2>&1 | tee exports/full.log
```

#### 4. 检查完整材料，再打包

用 JupyterLab 解压/查看，或执行下面命令；任一步报错就停止，目录已存在时换一个新的导出目录。一个包只放一本书、一次整书解析结果，不要把 sample、full、其他教材或环境目录混入同一包。不要只导出 Markdown；有插图时还需要其引用的真实图片文件，保留所有相对路径。

MinerU 4 的完整导出通常有 markdown.md、structured_content.json、middle_json.json 和 images/，可能另有 model_output.json；images 只在有图片资产时出现。Texa 优先读取 structured_content.json。仅有新版 middle_json 并不能保证被 Texa 识别，不能改名伪装成 content_list。旧版包可有 *_content_list.json / *_middle.json，但不要与新版不同文档混装。

在 structured_content.json 中检查 metadata.producer.name 为 MinerU、version 为 4.x，pages 有内容，且没有 is_full_document=false。将页面数与原 PDF 对照；再人工检查最后一页确已处理。小样、缺页、缺公式或图片引用失效时先修复，不把“有 ZIP”当作解析成功。保留原 PDF 便于校对和来源阅读；下面复制为 book_origin.pdf 一并打包。

Texa 默认 ZIP 上限 2 GiB、解压总量 20 GiB、最多 100,000 个条目、单条目 4 GiB，部署可能另设限制。超限应缩小材料并分别导入、保留清楚名称和原页范围；不要通过更改扩展名绕过限制。

预期结构（目录外层名称可不同）

```text
bundle/
  markdown.md
  structured_content.json
  middle_json.json
  images/                  # 有图片时保留
  model_output.json        # 可选，若原输出含有则保留
  book_origin.pdf          # 自己保留的原 PDF
```

实例终端：先解压到新的目录

```bash
unzip -t output/full.zip
mkdir exports/book-bundle && unzip output/full.zip -d exports/book-bundle
find exports/book-bundle -maxdepth 3 -type f | head -60
```

实例终端：核对结构并放入原 PDF

```bash
python - <<'PY'
import json, shutil
from pathlib import Path
root = Path("exports/book-bundle")
files = list(root.rglob("*structured_content*.json"))
assert len(files) == 1, "应只有一本书的一份 structured_content，请先检查目录"
data = json.loads(files[0].read_text(encoding="utf-8"))
producer = data.get("metadata", {}).get("producer", {})
assert str(producer.get("name", "")).lower() == "mineru"
assert str(producer.get("version", "")).startswith("4.")
assert data.get("pages"), "没有页面内容"
assert data.get("is_full_document") is not False, "这是部分文档，不能当整书导入"
print("解析页数:", len(data["pages"]))
print("原文档元数据:", data.get("metadata", {}).get("document", {}))
print("整书标志:", data.get("is_full_document", "未声明，必须人工核对"))
print("请对照原 PDF 页数、末页、公式与图片；此检查不证明 OCR 正确。")
target = files[0].parent / "book_origin.pdf"
assert not target.exists(), "原 PDF 已存在，请先核对，不自动覆盖"
shutil.copy2("input/book.pdf", target)
print("已保留原 PDF:", target)
PY
```

实例终端：人工检查完成后打包

```bash
cd exports/book-bundle
zip -r ../book-mineru.zip .
cd ../..
unzip -t exports/book-mineru.zip
sha256sum exports/book-mineru.zip > exports/book-mineru.zip.sha256
```

#### 5. 下载到本机，然后关机

在 JupyterLab 中找到 exports/book-mineru.zip，右键下载；同时下载 .sha256、environment.txt 和解析日志。JupyterLab 下载的是文件，文件夹要先打成 ZIP。大文件也可用 FileZilla 的 SFTP，或在本机终端执行下方 scp。

scp 在自己的 Mac/Windows 终端执行，替换控制台 SSH 指令里的主机和端口；-P 是大写，密码只在交互提示中输入。下载后在本机检查 ZIP 能打开，并把 SHA-256 与下载的 .sha256 文件对照。

确认文件已在自己的电脑后，到 AutoDL 控制台点“关机”，等实例状态变为“已关机”，并检查计费状态。关闭 JupyterLab、浏览器或 SSH 均不等于关机。只剩传文件时可按平台规则使用无卡模式；不要在无卡模式继续跑 GPU 解析。

按量 GPU 运行费、包周期和存储费规则不同，关机后仍可能有存储费用；以租用页为准。确认本地结果与备份齐全后才考虑释放实例；释放或更换镜像可能损失云端材料，保存镜像也不等于备份数据盘。

本机终端：SCP 下载示例（请替换主机与端口）

```bash
scp -P 12345 root@你的实例主机:/root/autodl-tmp/texa-mineru/exports/book-mineru.zip .
scp -P 12345 root@你的实例主机:/root/autodl-tmp/texa-mineru/exports/book-mineru.zip.sha256 .
```

本机校验：macOS 终端

```bash
shasum -a 256 book-mineru.zip
```

本机校验：Windows PowerShell

```powershell
Get-FileHash .\book-mineru.zip -Algorithm SHA256
```

#### 6. 导入 Texa，核对一次教材问答

回到运行 Texa 的电脑，打开“教材 → 导入教材”，选择“MinerU 输出包”。先将本机 ZIP 改为易辨认的教材名（教材名称取自文件名），选择该 ZIP 和所属科目，再点“导入输出包”。此路径复用已解析产物，不需要本机安装 MinerU，也不需要把云实例长期保持开机。

等待最终可用状态后回教材列表，“设为学习范围”。用原书一个明确概念提问，点“查看来源”检查教材、页码、公式与附图。导入完成只表示系统接受并建立了资料，不证明 OCR 或回答完全正确。

若提示多文档歧义、文件损坏、超限或没有正文，先检查第 4 步的结构和材料，不反复上传同一包。确认原 PDF 随包保留且来源可核对；教材导入不会自动建立练习题库。

**完成后：** 本机保留完整解析包和原 PDF；云实例已确认关机；Texa 中能选到教材并核对来源。

官方参考（2026-10-19 核对）：[MinerU 4 安装](https://opendatalab.github.io/MinerU/quick_start/) · [扩展依赖](https://opendatalab.github.io/MinerU/quick_start/extension_modules/) · [模型下载](https://opendatalab.github.io/MinerU/usage/model_source/) · [输出包结构](https://opendatalab.github.io/MinerU/reference/output_files/) · [vLLM 0.21 CUDA](https://docs.vllm.ai/en/v0.21.0/getting_started/installation/gpu/) · [AutoDL 上传与下载](https://www.autodl.com/docs/down/) · [AutoDL 省钱与关机](https://www.autodl.com/docs/save_money/)

### 设定学习范围

1. 在教材列表找到刚导入的书，选择“设为学习范围”。
2. 回“学习”，发送前检查右上角显示的学科和教材。问某章时，把章节名和具体问题写在提问里。
3. 用书中一个明确概念试问，打开来源确认来自预期教材。重开旧会话时再检查一次范围。

**请留意：** 导入教材不会自动建立题库。只选学科与选定一本教材的范围不同；“主要”角色也不保证只引用这一本书。

**完成后：** 当前范围与回答引用的材料一致。

<details><summary>多本书如何整理</summary>

有配套资料时，再按科目、分类及“主要 / 辅助 / 独立”整理。首次学习无需先配齐所有分类或概念关联。

</details>

### 顺着来源继续学

1. 点回答的“查看来源”，对照关键定义、条件与计算依据。
2. 追问具体一步，例如“第二行为什么成立”；发现条件有误就明确纠正。长会话中的精确条件建议重述。
3. 想留作复习材料，在会话菜单中整理并保存笔记。

**请留意：** 教材答不出时先看导入状态、范围和材料是否齐全。只有界面提供且你主动选择通用回答时，才把它作为普通解释阅读。

**完成后：** 能回看依据，并留下自己确认过的学习成果。

## 练习复习

题目先校对入库，作答后确认错题，复习时独立重做。

### 校对题目，再入库

1. 打开“练习 → 导入”，从已导入教材抽取，或上传 .docx / 含文字的 .pdf；也可手动录入。先用少量完整题目试一次。
2. 进入“校对候选题”，用“原文对照”检查题干、条件、答案与解析。需要时编辑、拆分或合并；页面要求时点“确认本题结构”。
3. 选择完整的题目，点“确认入库”。检查新增、重复和待处理回执，再到“题库”重开一道题。

**请留意：** 候选尚未入库，刷新或退出可能丢失。缺图、附表或条件的题不能靠删除图号绕过检查；修改后可能需要重新确认结构。入库结果不明先“核对导入批次”，不要反复提交。回滚批次会影响已入库题目。

**完成后：** 题库里出现已核对的正式题目。

### 提交一次真实作答

1. 在“练习”选范围、题量和顺序，开始本轮。
2. 先写自己的思路，再看参考答案；从“没掌握 / 基本理解 / 已掌握”选择真实自评并确认提交。
3. 完成后回看本轮记录；出现“待确认收录”时，再继续校对错题。

**请留意：** 自评不是自动阅卷。暂停或结束本轮不等于提交当前作答，离开前确认已提交。没有标准答案时，AI 解题只是草稿，核对后须点“保存到题库”；关闭、刷新或退出可能丢失未保存草稿。

**完成后：** 本次作答已提交，有可回看的练习记录。

### 确认收录错题

1. 从练习的“待确认收录”进入，核对题干、当时作答、参考答案及必要图表。
2. 保存校对并确认收录。手头只有图片或手写题时，可从错题录入开始，检查 OCR 后“保存并安排复习”。
3. 回到正式错题档案重新打开，检查能否“现在重做”。

**请留意：** 草稿和待确认候选都不是正式错题。缺材料时先存草稿；OCR 需要人工改正，不知道错因可以稍后再写。手动标记掌握不能替代独立重做。

**完成后：** 错题成为可独立重做的正式档案。

### 独立重做，记录结果

1. 打开“复习”，检查当前范围和到期内容，点“开始本次复习”或继续已有会话。
2. 先独立写答案，再“提交作答并查看反馈”；按实际情况选择本次结果并提交。
3. 回到队列检查记录。概念复习需另行展开、理解并记录。

**请留意：** 只揭示答案不算完成复习，空白作答不能算独立做对。错题会话不会顺带完成概念复习；空队列只表示当前范围没有到期项。

**完成后：** 本次结果已记录，能看到后续待办。

## 学习管理

安排今天的行动，保留学习记录，需要时再开启辅助功能。

### 安排任务与专注

1. 新建目标，写希望达到的结果；保存后添加今天能做的具体任务，例如“做 8 道课后题”。
2. 选一项任务开始专注，按需暂停、继续或结束。
3. 做完后主动“完成任务”；整个目标是否完成需要另行确认。

**请留意：** 保存目标不会自动启动 AI。计时到点不会自动完成任务，暂停计时也不等于停止 AI 辅助。定时安排依赖本机服务，关机后不会由云端代跑。

**完成后：** 任务状态与专注记录分别可查。

<details><summary>AI 整理、重点与报告</summary>

目标内的 AI 辅助需要明确启动；等待材料或确认时先看原任务提示。主输入区“学习操作”可查看或生成章节重点、打开日报周报。报告用于回顾记录，不是能力评分。睡眠、退出、手机并发和定时恢复仍需发行包实测。

</details>

### 备份与谨慎恢复

1. 到“设置 → 数据与教材”创建备份。需要时选择同时备份向量检索和 MinerU 产物，完成后查看校验结果、详情及保存位置。
2. 恢复前核对日期、包含范围和当前数据的安全副本。恢复按备份所含数据目录替换，同目录中新记录可能被覆盖。
3. 恢复在重启时执行；重开后分别核对教材、会话、笔记、作答、错题和目标，不只看登记提示。

**请留意：** 恢复不是逐条合并。系统会先创建安全备份，但不能据此保证所有故障都能自动回滚。备份不含 API Key，迁移后需重新配置。不要在正式学习资料上用旧备份试验恢复。

**完成后：** 有可定位、已校验的备份，并清楚恢复会覆盖什么。

<details><summary>哪些内容需要主动保存</summary>

模型测试后要保存配置；笔记草稿要“保存笔记”；题目候选要确认入库；AI 答案要“保存到题库”；练习作答要提交；错题要确认收录；重做后要记录结果。目标、任务完成和专注记录是分别提交的操作。

</details>

### 从当前状态继续

1. 不能回答：检查模型连接反馈、网络与服务额度，保存配置后再试一条实际问题。教材依据不足：检查教材状态、范围和缺失材料。
2. 找不到成果：笔记查“草稿 / 已保存”，错题查“待确认 / 档案”，再检查筛选、归档和会话回收站。回收站会话需恢复后才能继续提问。
3. 启动或更新失败：保留版本与脱敏错误，先重试或查看诊断，不要先清空数据。向维护者反馈时说明操作步骤和预期结果，遮住密钥、配对码及私人资料。

**完成后：** 找到对应记录或明确的下一步处理入口。

<details><summary>手机连接（可选）</summary>

在桌面“设置 → 手机连接”按提示准备 Tailscale，用本人手机打开地址并配对。电脑和本地服务需保持运行；手机访问同一份资料，不是独立同步副本。不要分享配对码。候选发行包、真实手机与重启配对行为仍待实测。

</details>
