# 本地 v0.1 命令、状态与事件契约

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

事件按 `{at, kind, detail}` 返回，`at` 为 UTC ISO 时间；同一 Job 按 SQLite 事件 ID 顺序呈现。主要事件包括 `created`、`process_started` / `process_exited`、`workflow_started` / `workflow_finished`、`step_started` / `step_finished` / `step_retry_scheduled`、`cancel_requested`、`finalizing`、`process_identity_unconfirmed`、`step_unknown` / `step_resolved`、`resume_claimed`、`callback_pending` / `callback_sending` / `callback_sent` / `callback_unknown`、`callback_handling_claimed` / `callback_handling_acknowledged`。Observer 另外写入 `structured_stage`、`structured_progress`、`structured_heartbeat`、`process_observed` 和 `file_observed`；没有输出不等于失败。

恢复命令：`reconcile` 核对 PID 与创建时间；结果不明时 `UNKNOWN`，并保留在途 Step 的资源锁。`stop-orphan` 仅终止身份核实的失联子进程；`resolve-step` 要求外部核对依据，`retry` 还要求 `safe_to_retry: true` 和剩余次数。`resume` 只从无未确认在途步骤的检查点继续。回调处理使用 `callback-claim` 核验 Job/event/status/可选当前线程，处理后 `callback-ack`；重复或处理中消息不再执行后续工作。
