# macOS arm64 desktop build

Build on a native Apple Silicon Mac with Python 3.10 and Node.js 22. Use the existing pinned Python requirements and npm lockfiles. Keep Windows builds on the existing PowerShell/NSIS path.

```bash
python3.10 -m venv venv310
venv310/bin/python -m pip install -r requirements-build.txt
npm ci --prefix frontend
npm ci --prefix desktop
npm run dev --prefix desktop
```

Build the frozen backend first, then the unsigned desktop package:

```bash
./scripts/build-desktop-backend-macos.sh
npm run dist:mac --prefix desktop
```

The outputs are `build/backend/backend_server/backend_server`, `release/mac-arm64/Texa.app`, and `release/Texa-<version>-mac-arm64.{dmg,zip}`. The DMG and ZIP contain a native arm64 app. Electron reads the backend and ONNX assets from `Texa.app/Contents/Resources`, while user data stays under the macOS application support directory. Set `KAOYAN_USER_DATA_DIR` to isolate a test profile.

The release validator runs at the end of the backend build. To check the frozen native dependencies directly:

```bash
TEXA_FROZEN_SMOKE=1 \
TEXA_EMBEDDING_ASSET_DIR="$PWD/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1" \
build/backend/backend_server/backend_server
```

This build deliberately has no Developer ID signing, notarization, stapling, MAS sandbox, Intel binary, or universal binary.
