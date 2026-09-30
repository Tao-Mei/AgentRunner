# 本地运行时路由

| 任务关键词 | 首读文件 | 按需继续读取 |
| --- | --- | --- |
| CLI 命令、提交预检、后台启动与交接 | [cli.py](cli.py) | [worker.py](worker.py) |
| CLI 与打包后独立 worker 的共用入口 | [entry.py](entry.py) | [__main__.py](__main__.py)、[cli.py](cli.py) |
| 按需启动本地 Service 与桌面窗口 | [launcher.py](launcher.py) | [entry.py](entry.py)、[desktop.py](desktop.py) |
| 命令响应、Job/Step 状态、事件字段契约 | [contract.md](contract.md) | [cli.py](cli.py)、[store.py](store.py) |
| 进程执行、日志、退出码 | [worker.py](worker.py) | [store.py](store.py) |
| 捕获日志的 UTF-8 与 Windows 本机编码显示 | [log_text.py](log_text.py) | [cli.py](cli.py)、[desktop.py](desktop.py)、[server.py](server.py) |
| SQLite Job 与事件状态 | [store.py](store.py) | [cli.py](cli.py) |
| Codex 回调传输与入队结果 | [callback.py](callback.py) | [回调 Skill](../.agents/skills/agent-runner-callback/SKILL.md) |
| 开始菜单启动后的 Codex 路径解析 | [codex_command.py](codex_command.py) | [cli.py](cli.py)、[callback.py](callback.py)、[desktop.py](desktop.py) |
| 目标模式授权暂停、回调后恢复与暂停所有权 | [goal_handoff.py](goal_handoff.py) | [goal_rpc.py](goal_rpc.py)、[cli.py](cli.py)、[回调 Skill](../.agents/skills/agent-runner-callback/SKILL.md) |
| 进程身份、取消、失联核对 | [processes.py](processes.py) | [cli.py](cli.py)、[worker.py](worker.py) |
| 本地 Service、令牌 API、任务页面 | [server.py](server.py) | [ui.html](ui.html)、[store.py](store.py) |
| Windows 桌面任务窗口、托盘、诊断提问 | [desktop.py](desktop.py) | [store.py](store.py)、[callback.py](callback.py) |
| Workflow YAML 预检、依赖展开 | [workflow.py](workflow.py) | [workflow_worker.py](workflow_worker.py) |
| Workflow 调度、步骤日志、资源锁与 Finalizer | [workflow_worker.py](workflow_worker.py) | [store.py](store.py)、[workflow.py](workflow.py) |
| 失联核对、步骤结果决策、检查点恢复 | [cli.py](cli.py) | [store.py](store.py)、[workflow_worker.py](workflow_worker.py) |
| 子进程环境变量筛选与敏感值 | [environment.py](environment.py) | [worker.py](worker.py)、[workflow_worker.py](workflow_worker.py) |
| 日志轮转、结构化事件、进程与文件观察 | [observer.py](observer.py) | [store.py](store.py)、[server.py](server.py) |
