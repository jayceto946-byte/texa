# Windows 更新退出、分阶段替换与回滚

用户报告 Windows 安装版更新时无响应、快捷方式暂时没有目标、“打开文件－安全警告／是否运行此文件”，随后图标恢复。用户已明确批准调整安装与回滚机制。

## 修改及效果

- Windows 先完成草稿/任务关闭握手、停止后端，再等 Electron 窗口销毁后的 quit 事件交接 NSIS。关闭期间显示安装中，检查/下载不会干扰交接。后端仍存活就取消关闭；安装包已不可读则保留客户端并重新提供下载。源码更新失败也恢复服务。
- NSIS 通过官方 customHeader/customInit include 扩展，保留默认首次安装、手动重装、自动生成和签名 uninstaller 的路径。仅 --updated 且原程序存在时使用分阶段更新，不再启动旧 uninstaller。
- 新程序先解压到安装目录同盘的独立候选目录；检查打包后的文件清单和长度，识别缺失/截断。清单在资源编辑/签名之后、NSIS 归档之前生成，支持 Unicode 路径；不再重复计算文件 hash。可选 elevate.exe 由 builder 随后添加，不纳入这份前置清单。
- 预压缩资源使用上游 customFiles 宏，并临时将 INSTDIR 指向候选目录，不能在准备期间覆盖旧程序。旧程序和快捷方式目标保持到候选完整准备好。
- 准备好后先把旧目录重命名为备份，再把候选重命名为原安装目录。两次同盘重命名之间仍有极短间隔，但不再包含解压/大批文件复制；原快捷方式、AppUserModelId 和安装位置保留，替换后通知 Shell 刷新。
- 原目录被占用时保留旧程序；发布或安装元数据更新、直接启动失败时恢复旧目录及原版本元数据。回滚本身受外部占用阻止时保留备份并报告位置，不为腾出路径递归删除原程序。自动更新失败会尝试重开旧程序，支持该标志的客户端显示上次更新失败。
- 当前用户安装正常启动新程序时直接执行已准备的本地 exe，避免内部重启再经过快捷方式/Explorer 打开文件流程。需管理员安装权限时保留 UAC，并通过原有非提权用户启动机制启动客户端。未删除 Zone.Identifier、改变系统信任策略或关闭安全软件。
- 安装版本和事务阶段（preparing/candidate_ready/committed/rolled_back 等）落在现有更新缓存的事务回执中；原安装包缓存继续更新，保留后续差分更新能力。

## 本机验证

本机是 macOS，结果不能代替 Windows 执行：

- 16 项定向桌面测试覆盖关闭握手、先关窗后安装、后端未退出、下载文件不可读、草稿拒绝、源码失败恢复，以及清单在最后资源编辑后生成、Unicode 路径和无本地绝对路径。
- 真实 Electron 运行生产 preload、关闭握手、安装 IPC 和退出处理，验证卸载拒绝、批准后关闭窗口并启动新 PID、保存拒绝三个场景。安装器 spawn 与后端为替身；VM 选择 Windows 交接分支，操作系统仍是 macOS。回执见 native.json。
- 使用生产 NSIS include 和 electron-builder 默认模板实际编译正常/缺文件两个微型 Windows 安装包，含预压缩资源。回执见 nsis-build.json。macOS 旧 Intel 编译器不能在本机运行，交叉编译使用官方 ARM64 NSIS toolset 1.2.1；生产 Windows 保持原默认工具版本，未更改依赖版本。
- 检查过程修正了模板标签/全局变量冲突、预压缩资源目标目录及启动插件返回状态。初次 Electron 沙箱无法启动，允许隔离测试窗口后验证成功；没有掩盖为产品测试通过。

## Windows 发布门槛与限制

commit 更新和正式发布流水线新增 verify-nsis-staged-update.cjs：在隔离目录实际安装微型夹具，执行正常替换、缺文件候选、真实文件占用、替换后注册表写入失败回滚；后者仅临时改变独立夹具卸载键的 SetValue ACL，并恢复原 ACL。确认旧程序保留/恢复、过时文件不留在新目录、预压缩资源不提前覆盖旧版本。

现有完整 Windows 安装包升级检查继续运行，另要求事务 committed 且版本正确，并读取实际桌面快捷方式目标确认仍为原 Texa.exe。

这些 Windows 执行尚未在本机完成，结果以本次提交触发的发布门槛为准；本机未操作用户已安装的软件。用户数据、教材索引、数据库和其他未提交工作保持原状。

回滚范围是准备、替换、元数据写入和立即启动失败；不声称能自动识别/回滚启动后的任意功能故障或断电。两次目录重命名不是单次文件系统事务；系统强制终止恰好落在两次操作之间时，仍需要保留的备份恢复。尚无用户 Windows 日志或安全提示中的文件路径，不能证明该次安全警告的唯一原因，亦不能保证系统策略产生的所有提示都消失。首次更新的退出仍由旧客户端执行。

参考：[electron-builder NSIS include 文档](https://www.electron.build/v26/docs/nsis/)、[上游 NsisUpdater](https://github.com/electron-userland/electron-builder/blob/master/packages/electron-updater/src/NsisUpdater.ts)、[nsProcess 返回码](https://nsis.sourceforge.io/NsProcess_plugin)、[StdUtils 启动返回状态](https://muldersoft.com/docs/stdutils_readme.html)。
