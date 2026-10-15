#!/bin/bash
# Build and run the integrated checkout; never redirect to another worktree.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODE="${TEXA_NODE:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
ELECTRON="$ROOT/desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
for required in "$ROOT/desktop/main.cjs" "$NODE" "$ELECTRON" "$ROOT/venv310/bin/python"; do
  if [ ! -f "$required" ]; then
    printf 'Missing runtime requirement: %s\n' "$required" >&2
    exit 1
  fi
done

if [ "${TEXA_BUILD_ONLY:-0}" != 1 ]; then
  "$ROOT/venv310/bin/python" - "$ELECTRON" <<'PY'
import subprocess, sys
commands = subprocess.check_output(['ps', '-ax', '-o', 'command='], text=True).splitlines()
if any(command.startswith(sys.argv[1] + ' ') for command in commands):
    sys.exit('Texa is already running. Quit it with Command-Q before launching a new build.')
PY
fi

printf 'Building %s (%s) at %s\n' "$(git -C "$ROOT" branch --show-current)" "$(git -C "$ROOT" rev-parse --short HEAD)" "$ROOT"
cd "$ROOT/frontend"
"$NODE" node_modules/typescript/bin/tsc -b
"$NODE" node_modules/vite/bin/vite.js build
printf 'Ready: %s\n' "$ROOT"
if [ "${TEXA_BUILD_ONLY:-0}" = 1 ]; then exit 0; fi
export KAOYAN_PYTHON="$ROOT/venv310/bin/python"
export TEXA_EMBEDDING_ASSET_DIR="$ROOT/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1"
cd "$ROOT"
exec "$ELECTRON" "$ROOT/desktop"
