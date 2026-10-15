# 本轮验证与重现

当前基线f999e72；新 worktree 和运行构建源相同。构建、测试在已有依赖完整的原master checkout进行，输出均隔离到/tmp；不是S3产品实现。执行工具使用bundled Node；Python业务测试严格venv310 Python3.10.21。

|检查|结果|证据文件|
|---|---|---|
|tsc -b|PASS|执行回执，exit0（无文本）|
|Vite build frontend --outDir /tmp/texa-mobile-s3-dist|PASS，大chunk警告|构建identity/manifest；没有覆盖frontend/dist|
|frontend vitest run|45文件203项PASS|evidence/texa-mobile-s3-vitest.log|
|frontend eslint .|1 error：render ref|evidence/texa-mobile-s3-lint.log|
|pytest S0/S1/network/task state/recovery/notes|92项PASS|evidence/texa-mobile-s3-pytest.log|
|desktop Node四文件|首次14/15，loopback EPERM；获准重跑15/15|evidence/texa-mobile-s3-desktop-tests*.log|
|qa-pages|119检查PASS，错误夹具11条503console，0unhandled|evidence/pages/results.json|
|focused audit|58图/29 metrics，0page errors；不是逐步断言全PASS|evidence/focused/focused-results.json|
|真实隔离API390普通模式|5项PASS|evidence/live-api/results.json|
|旧扩展E2E|5项PASS后旧按钮选择器超时，回执段NOT RUN|evidence/live-recovery/results.json、failure.png|
|临时修文案的扩展E2E|11项PASS，0errors|evidence/live-recovery-current-label/results.json|
|真实Electron壳|3项PASS|evidence/electron/results.json|

11项扩展E2E保留生产FastAPI、stores、JobManager、任务/回执服务，仅model/parser inputs synthetic。聊天回执为legacy task_；Goal为SQL rtask_。没有验证生产SQL native chat在真实弱网完整工具链的正确性。无付费调用、生产学习库读写或真实教材索引激活。

复用原 `scripts/qa-pages.mjs`、`qa-live-server.py`、`qa-live-e2e.mjs`、`qa-electron.mjs`；此处`focused-audit.mjs`复用前者的同一fixture路由，加触控metrics/底部/合成canonical SSE。`live-e2e-current-label.mjs`与原E2E仅按钮“提交并查看解析”→“查看参考答案”不同，没有改正式脚本。

重现（独立/tmp输出、端口空闲；NODE_BIN/NODE_PATH取本机已有bundled runtime，不重装）：

```sh
# 在仓库根目录；已有依赖工作区，先用现有tsc与Vite做隔离构建
NODE_PATH="$BUNDLED_MODULES" "$NODE_BIN" scripts/qa-pages.mjs /tmp/texa-mobile-s3-dist /tmp/texa-mobile-s3-recheck/pages
NODE_PATH="$BUNDLED_MODULES" "$NODE_BIN" docs/qa/mobile-s3/focused-audit.mjs /tmp/texa-mobile-s3-dist /tmp/texa-mobile-s3-recheck/focused
TEXA_QA_DATA=/tmp/texa-mobile-s3-recheck-api TEXA_QA_DIST=/tmp/texa-mobile-s3-dist TEXA_QA_WORKFLOWS=1 venv310/bin/python scripts/qa-live-server.py
# 另一个终端：以下会在一次性QA数据目录写合成学习资产
NODE_PATH="$BUNDLED_MODULES" TEXA_QA_WORKFLOWS=1 TEXA_QA_DATA=/tmp/texa-mobile-s3-recheck-api TEXA_QA_WIDTHS=390 TEXA_QA_E2E_OUT=/tmp/texa-mobile-s3-recheck/api "$NODE_BIN" docs/qa/mobile-s3/live-e2e-current-label.mjs
```

常规截图夹具18039/18040、focused18049/18050、真实API18041。结束只关闭本次创建的进程，不重启用户Desktop/Serve。源脚本Chrome路径依赖本机安装，换环境需明确浏览器路径。Android真机步骤按Acceptance Matrix人工执行；桌面viewport/isMobile不冒充真机。
