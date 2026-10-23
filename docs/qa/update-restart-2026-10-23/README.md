# Windows 更新退出阻断修复

日期：2026-10-23（Asia/Shanghai），起点 `8bc8402`。用户报告Windows安装版下载后点击重启更新会卡住退出，已授权修复并提交推送。

## 发现与实现

上次静默安装修复验证了 `quitAndInstall(true,true)` 生成 `--updated /S --force-run`，没有覆盖真实窗口的退出。当前Electron主进程虽在nonce绑定握手成功后设置allowQuit，但renderer的 `beforeunload` 是另一道门：它仍能取消app.quit。此时后端已经停止，旧窗口留着；本地实际NSIS模板会等待旧客户端退出，然后尝试结束仍在运行的进程。这是一条可复现、与用户现象相符的退出阻断；本机没有用户Windows日志，不能声称已判定该次故障全部根因。

`desktop/main.cjs` 现在监听 `will-prevent-unload`。仅在allowQuit或allowWindowClose已由现有关闭准备成功后设置时，调用event.preventDefault忽略这个迟到的renderer阻止。没有全局移除beforeunload、跳过草稿/专注/未保存确认，也不使用app.exit强制结束产品进程。准备失败或超时仍保留窗口，不停止后端、不安装。既有backend停止、NSIS静默参数、提交/下载校验及源码更新分支保留。

在现有backend.log中增加固定阶段消息：准备更新、关闭准备/后端停止完成、交给更新器、批准页面卸载、批准应用退出；不记录正文、token或密钥。

## 验证

- 桌面单元54 passed，语法检查通过：`desktop.log`、`syntax.log`。覆盖非本地IPC、下载未完成、草稿拒绝、后端等待、重复点击合并、源码重启、实际NsisUpdater参数及卸载授权门槛。
- `scripts/verify-electron-update-restart.cjs` 使用真实Electron窗口、生产preload/IPC、关闭握手、installAppUpdate、before-quit与卸载处理。NsisUpdater保留真实install/doInstall/quitAndInstall及参数转换，只替代安装器spawn与后端；以真实app.quit/app.relaunch验证进程退出和新PID。
- `native.json`保留初次原生证据；`native-final.json`、`native.log`为纳入生产before-quit处理后的最终复验：旧流程确实prepared/stopped且收到will-prevent-unload，却仍保持窗口；修复后收到相同卸载阻止并成功重启到不同PID；拒绝保存时stopped=false、installArgs=null、原窗口仍存在。三种场景均符合预期。
- 本机原生平台为macOS（Electron公共退出行为），不是Windows安装升级实测。测试没有执行任何真实安装器，不接触正式数据或付费模型。
- Windows commit-update流水线在打包发布前新增同一原生Electron检查，失败阻断构建，并上传update-restart-verification.json。原有真实下载与NSIS覆盖升级检查保留。此次Windows运行结果须以推送后的CI为准，不能继承macOS结果。

## 复现与交付边界

```sh
npm --prefix desktop test
npm --prefix desktop run check
node scripts/verify-electron-update-restart.cjs /private/tmp/texa-update-restart.json
```

原生脚本只操作独立临时profile及自己的Electron测试进程；baseline故意触发旧阻断，fixture结束使用app.exit，产品修复不这样退出。无依赖、数据库、索引或用户配置改动，搁置差异保持工作区未提交。

该修复在新客户端代码中生效。首次从旧客户端更新到包含本修复的版本时，退出仍由旧版本处理，可能仍需手动重开一次；手动打开后再检查版本。不能靠新包改变安装前旧进程已经加载的退出代码。这里只修复已复现的renderer退出阻断，不宣称所有Windows权限、文件占用或安装器启动故障都已解决。
