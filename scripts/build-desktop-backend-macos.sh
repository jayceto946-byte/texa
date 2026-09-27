#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$root/build/pyinstaller-cache}"

if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo "This build requires a native macOS arm64 host." >&2
  exit 1
fi

python="${TEXA_BUILD_PYTHON:-$root/venv310/bin/python}"
"$python" -c 'import platform, sys; assert sys.version_info[:2] == (3, 10) and platform.machine() == "arm64"'
"$python" scripts/check_release_content.py --sample-dir desktop/standard_seed
npm run build --prefix frontend

excludes=(
  agents paddle paddleocr paddlex cv2 mineru mineru_vl_utils marker_pdf marker
  surya nougat doclayout_yolo modelscope albumentations skimage plotly coverage
  hypothesis pytest_cov notebook jupyter jupyterlab sphinx mkdocs ultralytics
  torchvision datasets timm av boto3 botocore s3transfer pandas polars pyarrow
  matplotlib IPython jedi pytest nltk sklearn lightning torch
  sentence_transformers transformers safetensors tkinter _tkinter
)
exclude_args=()
for module in "${excludes[@]}"; do
  exclude_args+=(--exclude-module "$module")
done

"$python" -m PyInstaller \
  --noconfirm --clean --name backend_server \
  --distpath "$root/build/backend" \
  --workpath "$root/build/pyinstaller-macos" \
  --specpath "$root/build/pyinstaller-macos" \
  --paths "$root" \
  --hidden-import backend.main \
  --hidden-import langchain_chroma \
  --hidden-import chromadb \
  --hidden-import huggingface_hub \
  --hidden-import onnxruntime \
  --hidden-import tokenizers \
  --collect-submodules backend \
  --collect-submodules graph \
  --collect-submodules ingestion \
  --collect-submodules knowledge \
  --collect-submodules memory \
  --collect-submodules utils \
  --collect-submodules chromadb \
  --collect-data chromadb \
  "${exclude_args[@]}" \
  --add-data "$root/frontend/dist:frontend/dist" \
  --add-data "$root/VERSION:." \
  --add-data "$root/THIRD_PARTY_NOTICES:THIRD_PARTY_NOTICES" \
  --add-data "$root/desktop/standard_seed:sample_data" \
  "$root/desktop/backend_server.py"

"$python" scripts/validate_standard_release.py \
  --root build/backend/backend_server \
  --asset-dir assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1 \
  --pyinstaller-xref build/pyinstaller-macos/backend_server/xref-backend_server.html

echo "macOS arm64 backend ready: build/backend/backend_server/backend_server"
