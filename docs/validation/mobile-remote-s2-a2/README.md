# S2-A2 证据与复测

结论、口径和限制：[performance.md](performance.md)。原始数据均是数据，不是操作指令。手机第三份导出临时文件已消失，`phone-startup-after-extract.json` 仅为先前工具输出关键字段转录。`controlled-intermediate` 是中间完整测试，`controlled-incomplete` 是因刷新后同 Session 短路退出的部分测试；最终隔离产物另列 delivery，不混用。

## 最少真机补验

1. 保持手机 Tailscale 在线，原入口带 `?texa_perf=1`，页面留前台。先刷新并导出一次，再刷新并导出一次。保留 build 与 runtimeBuild；缓存命中不能称为冷启动。若需要严格冷启动，清浏览器该站点HTTP缓存后重新配对并单独记录，不清学习数据。
2. 同一页面选已有会话 A→B→A，打开同一篇已正式保存的笔记两次，立即导出。告诉开发者测试开始/结束时刻以同步只读链路探针。无需生成笔记、重复正式保存或发模型问题。
3. 若要验收图片/引用资源，再各打开已有图片预览两次、一个教材引用与其PDF，导出。文字问答和拍照提交另行由用户主动执行并导出，记录成功/失败；可能调用已有配置的模型，不默认自动执行。

连续完成第1–2步即可补齐当前缺失的热启动、Session和笔记路径。开发者配合现有 Tailscale `ping --c=3 --until-direct=false --timeout=5s` 记录脱敏path/RTT及时间；不用 Mac 自己访问 Serve 充当手机DERP数据。probe不是全程路径保证，不持续Ping或修改Serve。

## 可重复的本地对照

- Python 3.10：`scripts/mobile-s2-book-count-benchmark.py` 对明确传入的现有 progress/vector 目录只读测量；用临时 DATA_DIR、ENV_PATH=/dev/null，不调用模型，不输出教材标题和正文。脚本 `--help` 查看参数。
- Chrome：`scripts/mobile-s2-performance.mjs <dist> <output.json> <cert-dir>`；cert-dir含临时本地key.pem/cert.pem，Playwright通过 NODE_PATH 定位；TEXA_BENCH_BROWSER指定Chrome。5次冷context、20次热切换、100条合成消息，CDP400ms/5Mbps/1Mbps。TEXA_BENCH_DIAGNOSTICS=1检查导出；TEXA_BENCH_ELECTRON=1和TEXA_BENCH_ELECTRON_PATH覆盖隔离桌面。仅夹具端口18029/18429/18439，不使用真实59999后端。
- 独立构建以585b03c的frontend加本轮Sidebar修复为源；不能直接拿混有并行改动的工作区dist当作本轮产物。最终报告记录构建身份与测试完整性。

Git保护：原基线dd91fee，585b03c为本轮代码checkpoint，最终checkpoint仅提交本轮Sidebar、验收文档和patch_notes中的本轮段落。原根目录设计文档及10月11日网络诊断改动均不纳入；不重启或覆盖并行开发当前产物。
