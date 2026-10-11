# 重复运行质量检查

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

E2E采用每次独立标记，测试写入只在审计目录。qa-persistence当前核对固定/tmp/texa-full-qa-live与latest E2E结果，若选择新目录须同步修改测试脚本参数/路径，不能改为用户数据。Electron使用/tmp/texa-full-qa-electron，外部Fixture后端，测试后关闭自己的窗口。正式包托管后端与Windows生命周期另行验收。
