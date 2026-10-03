# 本地优先 SSH 原子发布

- 在本地不可变快照执行构建与测试，测试前后核对完整树指纹；测试若改变产物则拒绝发布，防止未验证产物进入 release。
- 先定义每个入口的方向与副作用，再编写测试：sync.sh 是远端到本地拉取，deploy.sh 是本地验证后上传并发布，rollback.sh 是版本恢复；不要以含糊的“同步”命名替代验收标准。
- 拉取优先可信 Git clone；仅未配置 Git 时使用 rsync，Git 失败绝不降级覆盖。已有非空副本拒绝覆盖，失败传输进入目的目录同文件系统的持久 staging，pull 专属 checkpoint 恢复；Linux renameat2(RENAME_NOREPLACE) 防止原子改名覆盖并发新建的本地目录。
- exclusions 只允许安全单组件名称列表，并与不可取消的 uploads/logs/.env、依赖及缓存默认排除合并；远端 shared/uploads、shared/logs、shared/.env 必须预先存在。备份 cp -a 只复制共享 symlink，不复制其目标；回滚切换回未修改的旧 release，不声称从备份恢复共享数据。
- 切换前错误持久标记 failed_before_switch，不能不必要地重启线上服务；检查 current 是否已改变以覆盖切换命令部分成功的情况。构建前先记录 building checkpoint，失败恢复只删除本事务 snapshot 后安全重建。
- 将拉取、本地验证、上传和提交拆成持久 checkpoint；未完成构建可重做，只有源码与产物指纹一致的已完成阶段才能复用。后台进程不抵御容器重启，自动续跑需另行配置已授权调度器。
- 生产不暴露 local backend，集成测试通过 PATH 注入假的 ssh/rsync/curl/systemctl；分别验证拉取方向、覆盖拒绝、上传前备份、失败恢复、并发互斥和断线后查询。
- 只向新 release rsync，采用 --copy-dest 而不是 --link-dest，避免旧 release 的硬链接内容被更新。
- 同时使用本地 flock、远端上传 owner 和事务 flock；记录 current 版本及内容指纹，提交时再检查。
- 通过 nohup 启动独立远端 shell 事务，保存 phase/result/log，SSH 断线后查询同一事务，不盲目发起新发布。
- Bash 的 ERR trap 要继承进函数（set -E）；否则 restart 函数失败会绕过回滚。回滚恢复原 symlink 后仍须重启与 HTTP/关键词校验。
- 备份可使用 cp -a --no-preserve=ownership：某些挂载不能 chown 即使进程为 root，要求所有者保留会令功能测试无意义地失败。
- 在上传前完成唯一事务对应的时间戳备份，恢复同一 checkpoint 时幂等复用；不能把切换前备份误当成满足“传输前备份”。最近五个备份可以清理，但不要自动删除 release；current、正在读取的旧版本和回滚目标必须保留。
- 普通目录 docroot 或缺失可恢复基线时拒绝发布，首次迁移须独立审批；shared 数据不属于代码回滚范围。
- 对 SSH 断线查询持久 result/phase，不推断成功或失败，不盲目重发。回滚后仍须检查 HTTP 状态码与关键词；stderr 和持久记录是本地告警，不等同于已投递消息。
