# 本地命令、状态与事件契约

入口：`python -m agentrunner`；CLI 成功响应为 JSON，查询命令 `jobs` / `show` 为 JSON，`logs` 为原始文本。命令使用 `--` 分隔 Runner 参数与待执行程序参数。`AGENTRUNNER_HOME` 未设置时使用用户目录下的 `.agentrunner`。CLI、Service 和 worker 必须指向同一个数据目录。

| 提交命令 | 返回与交接 |
| --- | --- |
| `run --cwd DIR [--callback-thread UUID] -- CMD ...` | 独立单命令；确认子进程已启动后返回 `ACCEPTED`、`job_id`、`event_id`。 |
| `exec --cwd DIR -- CMD ...` | 等待单命令结束；返回 `COMPLETED` / `FAILED` / `CANCELLED`、退出码。 |
| `exec --adaptive --grace-seconds N -- CMD ...` | grace 内结束则返回终态；否则返回 `PROMOTED_TO_BACKGROUND`、Job ID，Runner 继续执行。 |
| `submit WORKFLOW.yaml [--cwd DIR] [--callback-thread UUID]` | 预检 DAG 后启动独立 supervisor；其确认接管后返回 `ACCEPTED`。首个 Step 此时不一定已启动。 |

`ACCEPTED` 与 `PROMOTED_TO_BACKGROUND` 是 Agent 的执行交接点，不代表 Job 成功或回调送达。发起 Agent 随即结束 turn，不主动轮询。`REJECTED` 表示 worker 启动时已明确拒绝；`UNKNOWN_SUBMISSION` 包含 Job ID，必须先用 `show` 核对，不能盲目重交。提交前预检错误返回非零退出码，不产生已接收 Job。

| 状态对象 | 取值与含义 |
| --- | --- |
| Job | `CREATED`（已持久化）、`RUNNING`、`FINALIZING`、`COMPLETED`、`FAILED`、`CANCELLED`、`UNKNOWN`（结果无法确认）、`RESUMING`。只有三个完成/失败/取消状态是已知终态；`UNKNOWN` 需人工核对。 |
| Workflow Step | `PENDING`、`RUNNING`、`COMPLETED`、`FAILED`、`TIMED_OUT`、`CANCELLED`、`SKIPPED`、`UNKNOWN`。已完成 Step 恢复时不重跑；`UNKNOWN` 不自动重试。 |
| 回调 | `NOT_REQUESTED`、`PENDING`、`SENDING`、`SENT`、`UNKNOWN`。只有提交时提供有效 `--callback-thread` 才尝试 `codex queue`；`SENT` 仅表明 CLI 接受入队，不保证恰好一次唤醒。Service 运行时重送到期且未确认的回调。 |

`show JOB-ID` 返回 Job 字段、`events`；Workflow 还返回 `steps`，各 Step 含 `attempts`、`exit_code`、`error`、`artifacts`。产物条目记录相对路径、字节数和修改时间。`logs JOB-ID [--step STEP-ID] --stream stdout|stderr|worker` 读取对应落盘日志。`cancel JOB-ID` 请求取消，不意味着返回时进程已经退出。Service API 可提交、观察和控制 Runner Job；页面可观察与取消任务，均不改变 Job 的执行所有权。

v0.2 的 Workflow 调度控制：`pause-scheduling JOB-ID` 只暂停**新步骤**调度，正在运行的步骤继续；`continue-scheduling JOB-ID` 恢复该调度；`stop-after-current JOB-ID` 等当前活跃步骤结束后跳过剩余普通步骤、运行 Finalizer，Job 最终为 `CANCELLED`（若已有步骤失败则为 `FAILED`）。这三个命令只接受 `RUNNING` 的 Workflow；`cancel` 仍是立即请求终止活跃普通步骤。`show` 中的 `pause_requested` 与 `stop_after_current_requested` 是持久控制标记；事件分别记为 `scheduling_paused`、`scheduling_resumed`、`stop_after_current_requested`。它们均不冻结子进程。

安装版维护命令 `service-stop` 仅在没有活跃/结果不明 Job 和待投递回调时让本机 Service 正常退出，用于升级或卸载前检查；返回 `STOPPED` 或 `NOT_RUNNING`。窗口关闭与 Service 停止都不会改变已落盘任务状态。

事件按 `{at, kind, detail}` 返回，`at` 为 UTC ISO 时间；同一 Job 按 SQLite 事件 ID 顺序呈现。主要事件包括 `created`、`process_started` / `process_exited`、`workflow_started` / `workflow_finished`、`step_started` / `step_finished` / `step_retry_scheduled`、`cancel_requested`、`finalizing`、`process_identity_unconfirmed`、`step_unknown` / `step_resolved`、`resume_claimed`、`callback_pending` / `callback_sending` / `callback_sent` / `callback_unknown`、`callback_handling_claimed` / `callback_handling_acknowledged`。Observer 另外写入 `structured_stage`、`structured_progress`、`structured_heartbeat`、`process_observed` 和 `file_observed`；没有输出不等于失败。

恢复命令：`reconcile` 核对 PID 与创建时间；结果不明时 `UNKNOWN`，并保留在途 Step 的资源锁。`stop-orphan` 仅终止身份核实的失联子进程；`resolve-step` 要求外部核对依据，`retry` 还要求 `safe_to_retry: true` 和剩余次数。`resume` 只从无未确认在途步骤的检查点继续。回调处理使用 `callback-claim` 核验 Job/event/status/可选当前线程，处理后 `callback-ack`；重复或处理中消息不再执行后续工作。

## 实验性目标模式交接

桌面历史管理：`user_locked` 是用户保留锁，与执行资源锁不同；`note` 默认为空。清理只处理未锁定的已知终态任务，且要求回调无须请求或已确认处理、目标交接已解决、没有资源租约。清理后 `archived=1` 的记录不出现在任务列表，详细步骤、事件与 Runner 日志被清理；Job/event/thread 与回调认领记录保留，重复回调仍返回 `duplicate`。实际工作目录与用户产物不删除。日志删除失败会提示并可再次清理；无法确认的任务不自动清理。

有明确用户授权时，`run --pause-goal --callback-thread UUID -- CMD ...` 或 `submit WORKFLOW --pause-goal --callback-thread UUID` 在执行交接后通过本机 Codex 实验协议暂停原聊天的 active 目标。目标内容与预算不被覆盖。响应中的 `goal_handoff.status=PAUSED` 是暂停确认；`NOT_ACTIVE` 表示没有可暂停的活动目标，`UNKNOWN` / `UNAVAILABLE` 不证明目标停下。即便暂停失败，已接受的 Job 仍由 Runner 执行，不能因此重交任务。`exec` 不提供该选项。

暂停所有权持久绑定到 Job、event 和原聊天。当前回调认领响应携带 `goal_handoff` 状态；处理完对应任务后、ack 前，执行 `goal-release JOB-ID EVENT-ID --claim-token TOKEN --thread-id UUID`。此命令要求匹配终态任务和当前回调处理凭据；存在同聊天的其他活动任务时返回 `BLOCKED`。保存的目标身份、内容、预算、暂停状态及更新时间仍匹配时才恢复为 active，返回 `RELEASED`。重复释放不再调用目标接口；目标变化返回 `CHANGED`，结果不明返回 `UNKNOWN`，均不盲目重试。传输服务只负责投递，不能在聊天消费回调前自行恢复目标。

遇到结果不明，用户先在 Codex 界面确认目标状态并完成所需恢复；随后明确执行 `goal-dismiss JOB-ID --confirm-manual-recovery` 关闭该终态任务的自动恢复记录。该命令只改 Runner 所有权记录，从不修改 Codex 目标，不能自动用于跳过未确认副作用。

目标模式选项使用实验接口，默认不启用。接口没有原子比较更新或暂停来源字段，快照检查不能排除所有并发用户修改；上述恢复保护不等同于无竞争的自动恢复保证。一次探针授权不代表永久授权以后暂停目标。正式安装版的端到端验收尚待完成。
