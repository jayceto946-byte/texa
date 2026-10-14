# MinerU 教材解析：AutoDL 租卡全流程

> 面向本地运行本项目、在 AutoDL 租用 NVIDIA GPU 的用户。本文按 MinerU 3.x 编写；正式跑整本书前必须先做 5 页试跑。

## 1. GPU Host 是什么

`GPU Host` 只是“运行 MinerU 的远端 GPU 计算机”，在这里就是租到的 AutoDL 容器实例，不是另一个产品。

有两条路线：

1. **输出包路线（推荐）**：本地 PDF → 上传 AutoDL → MinerU 识别 → 输出目录压成 zip → 下载 → 本软件“教材导入 / 导入 MinerU 输出包”。不需要配置 `MINERU_API_URL`。
2. **SSH 隧道直连（高级）**：AutoDL 运行 `mineru-api`，本地软件经 SSH 隧道直接上传、轮询和下载。

所以可以“直接连租的卡”，但连接的是租用实例中的 MinerU API。第一次建议走输出包路线，最容易排错，也不要求 SSH 始终在线。

## 2. 租卡和镜像

推荐：

- 按量计费；AutoDL 是实例开机即计费，下载完成后要关机。
- 1 张 RTX 3090 24GB、RTX 4090 24GB 或同级 GPU。
- 内存至少 16GB，建议 32GB。
- 数据盘至少留 30GB。MinerU 官方最低磁盘要求约 20GB。
- Ubuntu + PyTorch 镜像。优先选仍可用的较新组合，如 `PyTorch 2.5.1 / Python 3.12 / CUDA 12.4`；否则选 Python 3.10–3.12、CUDA 11.8 或更新版本。

8GB 只是默认混合后端的最低显存，不建议第一次用它跑长篇数学教材。

在 AutoDL“控制台 → 容器实例 → 租用新实例”选择地区、1 卡、镜像并创建。开机后记下 JupyterLab 入口及 SSH 命令，例如：

```text
ssh -p 10309 root@connect.nmb1.seetacloud.com
```

端口和主机名必须替换为实例详情页显示的实际值。

## 3. 检查实例

进入 JupyterLab，打开 Terminal：

```bash
nvidia-smi
python --version
df -h /root/autodl-tmp
```

应看到具体 GPU、Python 3.10–3.12 和足够的数据盘空间。看不到 GPU 时先确认实例以正常 GPU 模式开机。

## 4. 安装 MinerU

把虚拟环境、模型缓存、PDF 和产物都放到数据盘，避免挤满系统盘：

```bash
mkdir -p /root/autodl-tmp/mineru-work/{input,output}
mkdir -p /root/autodl-tmp/mineru-work/cache/{uv,huggingface,modelscope}

python -m venv /root/autodl-tmp/mineru-venv
source /root/autodl-tmp/mineru-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install uv

export UV_CACHE_DIR=/root/autodl-tmp/mineru-work/cache/uv
export HF_HOME=/root/autodl-tmp/mineru-work/cache/huggingface
export MODELSCOPE_CACHE=/root/autodl-tmp/mineru-work/cache/modelscope
export MINERU_MODEL_SOURCE=modelscope

uv pip install -U "mineru[all]"
```

`mineru[all]` 是官方当前推荐的完整安装方式。大陆网络建议 ModelScope。第一次运行还会下载模型，耗时和占用增加是正常的。

验证安装和 CUDA：

```bash
mineru --version
mineru --help
python -c "import torch; print('torch=', torch.__version__); print('cuda=', torch.cuda.is_available()); print('gpu=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')"
```

必须看到 `cuda=True` 和 GPU 名称。每次打开新 Terminal，都要重新执行 `source /root/autodl-tmp/mineru-venv/bin/activate` 及上面的四条 `export`；环境和模型本身不会消失。

## 5. 上传教材

新手可在 JupyterLab 左侧进入 `autodl-tmp/mineru-work/input`，点上传按钮。建议把 PDF 改成短英文名，如 `advanced_math_1.pdf`。完成后检查：

```bash
ls -lh /root/autodl-tmp/mineru-work/input
```

也可在本地 Windows PowerShell 执行 SCP：

```powershell
scp -P 10309 "D:\Books\advanced_math_1.pdf" root@connect.nmb1.seetacloud.com:/root/autodl-tmp/mineru-work/input/
```

SCP 的端口参数是大写 `-P`。

## 6. 先做 5 页试跑

```bash
source /root/autodl-tmp/mineru-venv/bin/activate
export UV_CACHE_DIR=/root/autodl-tmp/mineru-work/cache/uv
export HF_HOME=/root/autodl-tmp/mineru-work/cache/huggingface
export MODELSCOPE_CACHE=/root/autodl-tmp/mineru-work/cache/modelscope
export MINERU_MODEL_SOURCE=modelscope

mineru \
  -p /root/autodl-tmp/mineru-work/input/advanced_math_1.pdf \
  -o /root/autodl-tmp/mineru-work/output/advanced_math_1-test \
  -m auto \
  -s 0 \
  -e 4
```

`-s 0 -e 4` 是第 1–5 个 PDF 页面（从 0 计数）。检查核心产物：

```bash
find /root/autodl-tmp/mineru-work/output/advanced_math_1-test -type f \
  \( -name "*.md" -o -name "*content_list*.json" -o -name "*middle*.json" \) \
  -print
```

至少应找到 Markdown、content_list JSON 或 middle JSON。用 JupyterLab 打开 Markdown，抽查中文、LaTeX 公式、双栏顺序和扫描页正文。合格后才跑整本。

## 7. 解析整本书

```bash
mineru \
  -p /root/autodl-tmp/mineru-work/input/advanced_math_1.pdf \
  -o /root/autodl-tmp/mineru-work/output/advanced_math_1 \
  -m auto
```

数学教材保留默认公式和表格识别。若确认是纯扫描件且 `auto` 没有触发 OCR，用新目录重跑：

```bash
mineru \
  -p /root/autodl-tmp/mineru-work/input/advanced_math_1.pdf \
  -o /root/autodl-tmp/mineru-work/output/advanced_math_1-ocr \
  -m ocr
```

长任务优先在 JupyterLab Terminal 运行；使用 SSH 时先进入 `screen` 或 `tmux`，避免断线终止。

## 8. 检查、打包、下载

```bash
find /root/autodl-tmp/mineru-work/output/advanced_math_1 -type f \
  \( -name "*.md" -o -name "*content_list*.json" -o -name "*middle*.json" \) \
  -print
du -sh /root/autodl-tmp/mineru-work/output/advanced_math_1
```

本软件可识别 `*content_list*.json`、`*middle*.json` 或 Markdown。要打包整个输出目录和图片资源，不能只下载 Markdown：

```bash
apt-get update
apt-get install -y zip
cd /root/autodl-tmp/mineru-work/output/advanced_math_1
zip -r /root/autodl-tmp/mineru-work/advanced_math_1-mineru.zip .
ls -lh /root/autodl-tmp/mineru-work/advanced_math_1-mineru.zip
```

本软件会用 zip 文件名作为默认教材名，请命名清楚且避免和已有教材重名。

下载方式：

- JupyterLab 找到 `autodl-tmp/mineru-work/advanced_math_1-mineru.zip`，右键 Download。
- 或本地 PowerShell：

```powershell
scp -P 10309 root@connect.nmb1.seetacloud.com:/root/autodl-tmp/mineru-work/advanced_math_1-mineru.zip "$env:USERPROFILE\Downloads\"
```

确认本地 zip 能打开后再关闭实例。

## 9. 导入本软件

1. 启动 Electron 桌面端，进入“教材导入”。
2. 选择“导入 MinerU 输出包”，不要选“导入 PDF 教材”。
3. 选择 zip，点击“导入输出包”。
4. 等待“解压结果包 → 整理结构 → 建立索引 → 完成”。上传后还要在本机建立 Chroma 索引，不能立即退出。
5. 在教材库确认教材和章节，并在对话中选择该教材做检索验证。

成功标准不是“zip 上传完成”，而是任务最终完成且索引到文本块。只有一个“全文”章节不一定失败，通常只是标题层级没有可靠识别。

## 10. 关机和保留

按量实例开机即计费。确认 zip 已下载且可打开后，回 AutoDL 控制台关机。AutoDL 当前会保留关机实例数据，但达到连续关机释放周期后可能清除；PDF 和 zip 必须另存本地。

保存镜像可复用系统盘环境，但 `/root/autodl-tmp` 是数据盘，不会随镜像保存。

## 11. 可选：通过 SSH 隧道直连

先验证输出包流程。AutoDL Terminal 启动 API：

```bash
source /root/autodl-tmp/mineru-venv/bin/activate
export UV_CACHE_DIR=/root/autodl-tmp/mineru-work/cache/uv
export HF_HOME=/root/autodl-tmp/mineru-work/cache/huggingface
export MODELSCOPE_CACHE=/root/autodl-tmp/mineru-work/cache/modelscope
export MINERU_MODEL_SOURCE=modelscope
export MINERU_API_OUTPUT_ROOT=/root/autodl-tmp/mineru-api-output

mineru-api --host 127.0.0.1 --port 8000 --enable-vlm-preload true
```

只绑定远端 `127.0.0.1`，不要把无认证 API 暴露到公网。

本地 PowerShell 保持运行：

```powershell
ssh -N -L 9001:127.0.0.1:8000 -p 10309 root@connect.nmb1.seetacloud.com
```

另开 PowerShell 验证：

```powershell
Invoke-RestMethod http://127.0.0.1:9001/health
```

软件中的 MinerU API URL 填：

```text
http://127.0.0.1:9001
```

然后选择“导入 PDF 教材”。直连期间 AutoDL 必须开机、`mineru-api` 必须运行、SSH 隧道不能关闭。AutoDL 的 SSH 主机名不是 `MINERU_API_URL`。

## 12. 常见问题

- `torch.cuda.is_available()` 为 `False`：先检查 GPU 模式和 `nvidia-smi`。若后者正常，多为镜像、PyTorch wheel 与驱动不匹配；优先更换较新的 PyTorch + CUDA 镜像。
- 下载慢：确认 `MINERU_MODEL_SOURCE=modelscope`，不要删除缓存，否则会重复下载。
- `No space left on device`：运行 `df -h` 和 `du -sh /root/autodl-tmp/mineru-work/*`，确认环境、缓存和输出都在数据盘。
- CUDA OOM：检查 `nvidia-smi`，换大显存实例；最后才降级为 `mineru -p 输入.pdf -o 输出目录 -b pipeline -m ocr -l ch`，并重新抽查公式和版面。
- 软件找不到 content_list、middle JSON 或 Markdown：通常是压错目录、任务未完成或 zip 损坏；重新执行第 8 节的 `find`，再打包整个正式输出目录。

## 官方参考

- [MinerU 安装与硬件要求](https://github.com/opendatalab/MinerU)
- [MinerU 快速使用](https://opendatalab.github.io/MinerU/usage/quick_usage/)
- [MinerU CLI 参数](https://opendatalab.github.io/MinerU/usage/cli_tools/)
- [MinerU 输出格式](https://opendatalab.github.io/MinerU/reference/output_files/)
- [AutoDL 快速开始](https://www.autodl.com/docs/quick_start/)
- [AutoDL JupyterLab](https://www.autodl.com/docs/jupyterlab/)
- [AutoDL SCP](https://www.autodl.com/docs/scp/)
- [AutoDL 实例目录](https://www.autodl.com/docs/env/)
- [AutoDL 计费](https://www.autodl.com/docs/price/)

## 2026-10-03：MinerU 4 原生输出包

本地 Texa 已新增 `structured_content.json` 原生入口，已用提供的 MinerU 4.0.8 输出离线验收；不需要预先转换为 `texa_content_list_v1.json`。远端 MinerU 的 Python/CUDA 环境继续与本地 Python 3.10 分离，本文上面的 3.x 部署示例不代表 4.x 服务端安装步骤。

将同一本书的 `structured_content.json` 和原始 `images/` 一起放入 ZIP，保留相对目录，使用桌面端“导入 MinerU 输出包”。不要把不同书的结果合成一个目录；损坏原生文件、未知版本或歧义来源会给出诊断，不会静默导入另一份书。原始 PDF 可选，缺 PDF 时显示为没有 PDF。

兼容顺序为 native structured → content-list v1/v2 → 旧 middle → Markdown。新 `pages` middle 不由旧 `pdf_info` parser 读取，`_middle_chunks.json` 也不是输入或可恢复索引快照。公式和表格原图与结构化正文一并保存，缺图不会删除可用正文；原图不是数学正确性验证。

首次 native 验收使用隔离数据目录或新教材身份。发布及兼容性细节、完整语料数量差异、GUI 和硬终止恢复未覆盖项见 [实施验收报告](mineru-native-implementation-2026-10-03.md)。保留已有 bridge、源归档和旧 content-list 支持。
