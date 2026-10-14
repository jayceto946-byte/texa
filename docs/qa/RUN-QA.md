# 重复运行质量检查

后续范围与验收分工见 [P0/P1 整改策略](QA-REMEDIATION-STRATEGY.md)。复用下列命令，将有效截图按 [Visual Review Board](VISUAL-REVIEW-BOARD.md) 筛选供 Astra 直接阅图；不重新建设工具。当前 Electron 开发端 E2E 在范围内，真实 Tailscale 设备及正式安装包生命周期延后。

在仓库根目录执行，使用 venv310 Python3.10；本机 Node不在PATH，qa-check会寻找Codex捆绑runtime，也支持TEXA_QA_NODE指定。需要保留已安装依赖，不执行重新安装。

```sh
venv310/bin/python scripts/qa-check.py smoke
venv310/bin/python scripts/qa-check.py frontend
venv310/bin/python scripts/qa-check.py backend
venv310/bin/python scripts/qa-check.py desktop
venv310/bin/python scripts/qa-check.py build
```

每层写入docs/qa/evidence/latest/<layer>，独立临时数据目录和空.env。不要指向真实学习数据。desktop、浏览器、本地服务在沙盒中需要loopback/GUI执行权限。全量用all，不必每次修改运行。

截图需先构建一个独立静态目录。在frontend目录，用现有Node执行`node_modules/vite/bin/vite.js build --outDir /tmp/texa-full-qa-dist`。本机捆绑Node位于`~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`；Playwright模块目录为相邻`node/node_modules`，通过NODE_PATH提供。

```sh
# 回到仓库根目录；node为上述现有解释器，NODE_PATH提供现有Playwright
node scripts/qa-pages.mjs /tmp/texa-full-qa-dist docs/qa/evidence/new-pages
# 局部视觉回归也实际执行笔记/设置交互
TEXA_QA_ROUTES=learning,exercises node scripts/qa-pages.mjs /tmp/texa-full-qa-dist docs/qa/evidence/new-visual
venv310/bin/python scripts/qa-visual-compare.py docs/qa/baselines docs/qa/evidence/new-visual docs/qa/evidence/new-comparison.json
```

合成API服务绑定18039/18040，脚本自行关闭。所有截图要实际读取，render检查只捕获宽度和失败边界，不是审美自动判定；控制台故障和未配置Fixture端点仍需审查。固定基准8张，有效diff阈值0.5%像素/通道差>20；不要为测试通过盲目刷新基准。

真实服务/持久化E2E使用另一个端口18041。单独终端启动下列服务；只接受/tmp下的隔离数据目录，关闭外部模型连接，warmup/模型配置元数据使用Fixture。无需真实密钥。

```sh
TEXA_QA_DATA=/tmp/texa-full-qa-live TEXA_QA_DIST=/tmp/texa-full-qa-dist venv310/bin/python scripts/qa-live-server.py
node scripts/qa-live-e2e.mjs
node scripts/qa-electron.mjs
# 停止并重新启动上述审计服务，然后只读核对最新E2E记录
venv310/bin/python scripts/qa-persistence.py
```

E2E采用每次独立标记，测试写入只在审计目录。qa-persistence通过TEXA_QA_DATA、TEXA_QA_RESULTS、TEXA_QA_PERSISTENCE_OUT选择隔离目录与结果；不能改为用户数据。Electron使用/tmp/texa-full-qa-electron，外部Fixture后端，测试后关闭自己的窗口。正式包托管后端与Windows生命周期另行验收。

## 本轮扩展闭环与截图

沿用现有脚本，先构建独立目录并等待构建成功，再启动服务；捕获过程中不要覆盖同一 dist。

```sh
TEXA_QA_DATA=/tmp/texa-full-qa-live TEXA_QA_DIST=/tmp/texa-full-qa-dist-p0-final TEXA_QA_WORKFLOWS=1 venv310/bin/python scripts/qa-live-server.py
TEXA_QA_WORKFLOWS=1 TEXA_QA_E2E_OUT=docs/qa/evidence/p0-p1/extended-e2e node scripts/qa-live-e2e.mjs
TEXA_QA_WORKFLOWS=1 TEXA_QA_ELECTRON=1 TEXA_QA_E2E_OUT=docs/qa/evidence/p0-p1/electron-final node scripts/qa-live-e2e.mjs
# 后端停止/重启后，只读核对
TEXA_QA_RESULTS=docs/qa/evidence/p0-p1/extended-e2e/results.json TEXA_QA_PERSISTENCE_OUT=docs/qa/evidence/p0-p1/restart-persistence.json venv310/bin/python scripts/qa-persistence.py
```

WORKFLOWS仅替换受控模型/解析输入，Runtime、Job与存储真实；教材故意失败/取消，不代表成功索引发布。qa-pages也复用设置单栏导航、字段保留和键盘断言。所有pytest必须经qa-check隔离环境运行，不要直接运行可能写学习事件的测试。

### 复杂交互模式（复用现有服务/E2E）

`TEXA_QA_DATA=/tmp/texa-complex-qa TEXA_QA_DIST=/tmp/texa-complex-dist-after TEXA_QA_WORKFLOWS=1 TEXA_QA_COMPLEX=1 venv310/bin/python scripts/qa-live-server.py` 启动隔离服务。dist先由现有Vite构建到/tmp；不要复用正式data/progress目录。

给现有 `qa-live-e2e.mjs` 设置 `TEXA_QA_COMPLEX=1` 和 `TEXA_QA_E2E_OUT=docs/qa/evidence/complex/final`；bundledNode/NODE_PATH沿用上述命令。默认1280×820、1024×768、760×820、390×820，可用 `TEXA_QA_WIDTHS=1280,760` 聚焦复验。Electron加 `TEXA_QA_ELECTRON=1`，输出目录用complex/electron。此模式仅创建/tmp合成Word/PDF/图片及持久来源，提取走真实代码；模型/外部连接关闭。正式阅读截图等待目标正文，字段label点击与焦点/inert/Escape单独断言。完成后关闭自己启动的审计服务，保留隔离证据，不停止用户服务。
