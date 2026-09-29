# 本地运行时路由

| 任务关键词 | 首读文件 | 按需继续读取 |
| --- | --- | --- |
| CLI 命令、提交预检、后台启动与交接 | [cli.py](cli.py) | [worker.py](worker.py) |
| 命令响应、Job/Step 状态、事件字段契约 | [contract.md](contract.md) | [cli.py](cli.py)、[store.py](store.py) |
| 进程执行、日志、退出码 | [worker.py](worker.py) | [store.py](store.py) |
| SQLite Job 与事件状态 | [store.py](store.py) | [cli.py](cli.py) |
| Codex 回调传输与入队结果 | [callback.py](callback.py) | [回调 Skill](../.agents/skills/agent-runner-callback/SKILL.md) |
| 进程身份、取消、失联核对 | [processes.py](processes.py) | [cli.py](cli.py)、[worker.py](worker.py) |
| 本地 Service、令牌 API、任务页面 | [server.py](server.py) | [ui.html](ui.html)、[store.py](store.py) |
| Workflow YAML 预检、依赖展开 | [workflow.py](workflow.py) | [workflow_worker.py](workflow_worker.py) |
| Workflow 调度、步骤日志、资源锁与 Finalizer | [workflow_worker.py](workflow_worker.py) | [store.py](store.py)、[workflow.py](workflow.py) |
| 失联核对、步骤结果决策、检查点恢复 | [cli.py](cli.py) | [store.py](store.py)、[workflow_worker.py](workflow_worker.py) |
| 子进程环境变量筛选与敏感值 | [environment.py](environment.py) | [worker.py](worker.py)、[workflow_worker.py](workflow_worker.py) |
| 日志轮转、结构化事件、进程与文件观察 | [observer.py](observer.py) | [store.py](store.py)、[server.py](server.py) |
