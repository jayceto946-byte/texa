# Platform audit: desktop lifecycle and mobile/remote entry

Date: 2026-10-11  
Scope: Electron startup/shutdown, preload/IPC, window state, onboarding/model setup, browser storage/cache, and phone/Tailscale connection path. This audit did not modify product code. Existing dirty Mobile S2 files were left unchanged.

## Result

| Area | Status | Evidence |
|---|---|---|
| Desktop startup, backend ownership and health gating | PASS (code + unit coverage) | `desktop/main.cjs`, `desktop/runtime.cjs`; all desktop tests pass when loopback binding is permitted |
| Desktop close handshake and backend shutdown | PASS (code + unit coverage) | `desktop/window-close.cjs`, `desktop/main.cjs`; close-preparation tests pass |
| Preload boundary and window security flags | PASS (code inspection) | `desktop/preload.cjs`, `desktop/main.cjs` |
| First-run model setup and completion persistence | PASS (code + setup-state tests) | `frontend/src/components/FirstRunGuide.tsx`, `desktop/setup-state.cjs` |
| Phone credential bootstrap and same-origin API selection | PASS (frontend tests) | `frontend/src/api/client.ts`, `RemoteConnectionGate.tsx`; 20 scoped tests pass |
| Browser cache/PWA behavior | PASS for inspected static/read caches; PWA NOT_PRESENT | hashed assets get immutable cache headers; API snapshots are in-memory and short-lived; no manifest/service worker registration found |
| Desktop syntax checks | PASS | `platform-desktop-check.log` |
| Desktop full test suite | PASS (after permitted escalation) | 15/15 pass; [escalated run](evidence/platform-desktop-tests-escalated.log). Default sandbox run remains blocked by `EPERM` for loopback binding. |
| Windows packaged startup/shutdown | NOT_TESTED | Current host is macOS; no Windows VM/runtime available in this task |
| Real Android browser and Tailscale Serve route | NOT_TESTED | No Android device/browser or live Tailscale Serve session available |

## Actual execution chains

### Desktop startup and window

`desktop/main.cjs` takes the single-instance lock, chooses the stable per-user data directory, creates per-run API/capture tokens and an instance ID, and starts the backend. Packaged mode spawns the bundled backend executable; development mode probes an existing service and only accepts it when both instance identity and token authorization match. Otherwise it launches the Python backend. Normal startup chooses a free `127.0.0.1` port, binds the backend to loopback, waits for `/health`, checks the instance ID and warmup state, then loads the web UI with a one-time fragment carrying the API base and token. The frontend consumes and removes that fragment before API use.

The BrowserWindow uses a preload, `contextIsolation: true`, `nodeIntegration: false`, and `sandbox: true`. Navigation is restricted to the local backend/development origin; external HTTPS links open in the system browser. `preload.cjs` exposes specific IPC methods instead of a generic IPC bridge.

### Close, restart and updater shutdown

Window close and app quit call `prepareWindowClose()`. The renderer flushes registered close handlers and acknowledges a nonce tied to the renderer ID. A failed or timed-out flush vetoes close. On accepted close/restart/update, `stopBackend()` calls the authenticated shutdown endpoint, waits for process exit, then applies bounded platform-specific termination (`taskkill /t /f` on Windows; signal and process-group kill elsewhere). Concurrent shutdown calls coalesce through one promise. Unit tests cover nonce validation, coalescing, veto, and timeout behavior.

### First-run model setup

The remote connection gate wraps the lazily imported authenticated workspace. For a remote browser, the gate requires HTTPS, sends the short-lived token to the same-origin `/api`, checks that the desktop requires tokens and reports ready, and only then loads the workspace. On desktop, the first-run guide loads `/system/settings`, requires a reasoning model and any required credential, saves/activates the selected profile, reloads persisted settings, then writes a credential-free setup-complete marker to Electron userData. A legacy localStorage marker is migrated when a configured model exists. Model keys are entered in password fields; setup completion stores only a version/boolean marker.

### Mobile/remote API and caching

`isRemoteBrowser()` treats non-loopback, non-Electron browser hosts as remote. A remote launch strips any supplied desktop API base and old localStorage token, uses relative `/api` requests, and keeps the token in sessionStorage (or page memory if storage is denied). A 401 clears the remote token and raises a reconnect event. This is exercised by the current remote-connection and storage-denial tests.

The desktop backend remains bound to `127.0.0.1`; the desktop settings UI gives the user a `tailscale serve` command targeting the actual backend port and copies the temporary management token. There is no automatic Tailscale installation/configuration. Static hashed JS/CSS assets receive `public, max-age=31536000, immutable`; frontend API read snapshots are in-memory with a 30-second default TTL and explicit invalidation. Inspection found no PWA manifest or service-worker registration, so offline install/cache behavior is not part of the current implementation.

## Defects

No code-confirmed product defect was found in the inspected scope. The default sandbox denied loopback socket binding, and the same desktop suite passed 15/15 with the explicitly permitted read-only escalation. Windows process-tree termination and the live Android/Tailscale route remain unverified platform acceptance items.

| Severity | Root cause | Validation suggestion |
|---|---|---|
| N/A — coverage gap | Current environment does not provide Windows, Android, or a live Tailscale Serve route; loopback bind is denied in the test sandbox. | Run packaged Windows startup/close/restart and Android HTTPS + token reconnect smoke tests on supported hosts; rerun the desktop suite in an environment permitting loopback bind. |

## Test evidence

- [Desktop test output](evidence/platform-desktop-tests-escalated.log): 15 passed, 0 failed when loopback binding was permitted. The earlier [sandbox run](evidence/platform-desktop-tests.log) shows the environment-only `EPERM`.
- [Desktop syntax check](evidence/platform-desktop-check.log): `main.cjs`, `preload.cjs`, `runtime.cjs`, `appearance.cjs` all pass `node --check`.
- [Frontend scoped tests](evidence/platform-frontend-tests.log): 5 files / 20 tests passed (`remoteConnection`, mobile performance, startup gate/storage/guard).

The host shell does not have `npm` on PATH; tests were invoked directly with the bundled Node executable and already-installed project test modules. No dependencies were installed.
