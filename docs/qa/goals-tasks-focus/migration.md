# Focus v3 迁移与回滚方案

本文件是可评审的部署方案。正式数据库尚未获迁移批准，未执行下列生产步骤。

## 变更

保留原 `focus_tasks` / `focus_state` / `focus_receipts`，增量增加任务顺序、条件来源、软删除、完成时间和 `legacy_elapsed_ms`；新增 `focus_sessions` / `focus_segments`、任务历史索引、至多一条未结束时段的唯一索引。Goal / revisions / run_links 不改格式或内容。

v1 或 v2 → v3。Focus API 默认不迁移已有库，而返回可解释的503；全新不存在的库可正常初始化。GoalStore 支持到3但不替 Focus 自动迁移。

旧 in_progress → pending，当前指针保留；原 elapsed 原样保留并作为旧版累计基线。不从旧 started_at 推测离线投入，不生成虚假的旧时段/暂停历史。迁移时运行中的旧段标记 `legacy_interrupted`，未结算尾段不计入新记录。原 duration 仅作后续倒计时偏好。

## 已完成的隔离演练

`tests/test_focus_tasks.py` 中 v2 fixture 保持原表结构、开启 WAL 且关闭自动检查点；实际 `Connection.backup` 后迁移。断言：

- Goal 内容与 revision、goal_revisions、goal_run_links、receipt 每行一致；旧 task ID/revision/elapsed 保留。
- 20.5秒旧累计变成20500ms基线；不合成 session；原运行状态成为待开始、标出未知尾段。
- 新库 integrity_check 和 foreign_key_check 通过。
- 备份仍为schema2，打开恢复后原表各行一致且 integrity_check 为ok。
- 重复打开/重复迁移不制造重复时段或备份；更高未知版本拒绝读取。

测试只对临时库执行，不声称已核对真实库计数。

## 批准后的部署步骤

1. 确认唯一新版运行包、源码身份、前端构建身份、目标数据库绝对路径与schema；停止 Electron 和所有本地后端，暂停远程写入准入。
2. 先用 SQLite backup 得到一致副本，在副本上运行迁移和检查；记录所有表计数/ID、Goal revision/links、旧elapsed、integrity_check及外键检查。
3. 用户批准真实迁移后，从新版仓库运行：

   ```sh
   venv310/bin/python -m scripts.migrate_focus_v3 --database /实际/绝对路径/goals.db --apply
   ```

   脚本在事务之前创建含WAL的一致备份；不存在的路径或未知schema拒绝操作。没有 `--apply` 不写数据库。
4. 启动唯一新版后端与对应前端；检查 Focus/Goal API、暂停恢复、历史及原Goal/AI安排，不调用付费模型来证明计时正确。

## 回滚

- 迁移事务失败：原事务回滚，原库与备份保留，不重启旧/新混用的包。
- 迁移后尚无新写入：冻结所有写入后，按原schema兼容运行包和已校验备份做恢复演练，再决定恢复；不是把备份文件复制进运行中的WAL目录。
- 已有v3新增时段：先冻结，使用 SQLite backup 导出整个v3库及新增 tasks/sessions/segments/receipts。优先修复或使用可读v3的兼容包；不得静默恢复旧备份丢弃新增时间。向v2降级不在本次自动工具范围，须另行批准并核对保留的新增记录。

真正的数据库恢复及系统休眠跨平台验收仍未执行。备份存在不能代替新版数据保留或发布验收。
