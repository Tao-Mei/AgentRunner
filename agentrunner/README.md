# 本地运行时

此目录实现本地命令与 Workflow 预览版，负责提交、独立执行、SQLite 状态、日志和 Codex 回调传输。它只处理可执行程序与参数，不理解具体业务、视频或统计任务。已有手动启动的本地 Service、基础 Web UI、Workflow DAG 调度和检查点恢复。失联的在途进程无法凭空恢复退出码，必须保留 `UNKNOWN` 并由用户依据外部证据决定步骤结果或安全重试。

入口为 `python -m agentrunner`。开发阶段使用 `AGENTRUNNER_HOME` 指定可写数据目录；一次提交只在独立 worker 或 Workflow supervisor 写入启动确认后返回 `ACCEPTED`。单命令此时已启动子进程；Workflow 此时已由 supervisor 接管，首个 Step 可能尚未启动。`serve` 提供绑定 `127.0.0.1` 的令牌 API 和页面，页面退出不影响 worker。命令可用 `--pass-env NAME` 声明向子进程传递的变量，用 `--watch PATTERN` 记录文件变化；Workflow Step 可声明 `pass_env` 和 `artifacts`。命令、状态、事件字段见[本地契约](contract.md)，模块定位见[局部路由](structure.md)。

Workflow supervisor 失联后，先运行 `python -m agentrunner reconcile`。若 Job 为 `UNKNOWN` 且所有步骤结果可确认，可用 `python -m agentrunner resume JOB-ID` 从持久检查点继续；已完成步骤不会重跑。对于 `UNKNOWN` 步骤，先检查进程、日志和产物，再以 `resolve-step JOB-ID STEP-ID --outcome completed|failed|retry --evidence "核对依据"` 记录决定。`retry` 只允许原 Step 声明 `safe_to_retry: true`、仍有尝试次数，且旧进程已确认退出。Runner 不会自动重跑结果不明的步骤。

收到本地 Job 回调后，可用 `callback-claim JOB-ID EVENT-ID --status COMPLETED|FAILED|CANCELLED` 核验并认领；已知当前聊天 ID 时加 `--thread-id UUID` 核对目标。`new` 或 `recovered` 返回的 `claim_token` 在必要的后续处理完成后交给 `callback-ack JOB-ID EVENT-ID --claim-token TOKEN`。`in_progress` 与 `duplicate` 不再处理。超过五分钟的未确认认领可恢复，但必须先核对上次处理的持久副作用。该机制不能保证回调消息或用户可见回复恰好一次。

带回调线程的命令和 Workflow 提交会将当前 PATH 中可用的 Codex CLI 绝对路径记入 Runner 数据目录。界面提问与回调优先解析当前 PATH，再使用仍存在的记录路径，因此从开始菜单启动不需要全局修改 PATH。Codex 更新导致旧路径失效时，需要从 Codex 再次提交任务刷新记录；缺失 CLI 时不会声称入队成功。
