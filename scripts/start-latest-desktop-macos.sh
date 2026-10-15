#!/bin/bash
# Build a separate runtime from the latest feature checkout, preserving both checkouts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${1:-$HOME/.codex/worktrees/goals-tasks-focus/texa}"
NODE="${TEXA_NODE:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}"
ELECTRON="$ROOT/desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
for required in "$SOURCE/desktop/main.cjs" "$NODE" "$ELECTRON" "$ROOT/venv310/bin/python"; do
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

RUNTIME="$ROOT/artifacts/dev-runtime/$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$RUNTIME"
# Copy tracked files, including their current uncommitted contents. Never copy user data or .env.
git -C "$SOURCE" ls-files -z | rsync -a --from0 --files-from=- "$SOURCE/" "$RUNTIME/"
ln -s "$ROOT/frontend/node_modules" "$RUNTIME/frontend/node_modules"
ln -s "$ROOT/desktop/node_modules" "$RUNTIME/desktop/node_modules"
if [ -d "$ROOT/assets/embedding-runtime" ]; then
  mkdir -p "$RUNTIME/assets"
  ln -s "$ROOT/assets/embedding-runtime" "$RUNTIME/assets/embedding-runtime"
fi
printf '%s\n' "$RUNTIME" > "$ROOT/artifacts/latest-desktop-runtime.txt"
printf 'Building source %s at %s\n' "$(git -C "$SOURCE" rev-parse --short HEAD)" "$SOURCE"
cd "$RUNTIME/frontend"
"$NODE" node_modules/typescript/bin/tsc -b
"$NODE" node_modules/vite/bin/vite.js build
printf 'Ready: %s\n' "$RUNTIME"
if [ "${TEXA_BUILD_ONLY:-0}" = 1 ]; then exit 0; fi
export KAOYAN_PYTHON="$ROOT/venv310/bin/python"
export TEXA_EMBEDDING_ASSET_DIR="$ROOT/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1"
cd "$RUNTIME"
exec "$ELECTRON" "$RUNTIME/desktop"
