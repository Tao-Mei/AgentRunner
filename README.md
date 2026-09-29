# AgentRunner

AgentRunner 让 AI Coding Agent 将确定性的长时间机器任务交给独立进程执行，并在需要判断时由事件唤醒 Agent。

当前代码是 Windows 本地 v0.1 MVP：CLI 与独立 worker 执行单命令，SQLite 保存状态和事件，日志落盘，任务结束可向原 Codex 聊天入队回调。支持同步/自适应执行、取消、进程身份核对、手动启动的本地 Service 和基础任务页面；本地 Workflow 支持 DAG、`foreach` / `after_each`、并行、资源容量锁、显式重试、超时、产物清单与 Finalizer。日志采集可记录结构化事件、进程和文件事实，并对已知敏感环境值脱敏。失联后可从无在途步骤的检查点安全继续；结果不明的在途步骤须先核对和显式决策。

## 本地试用

需要 Windows 和 Python 3.11 或更新版本。在项目根目录运行 `python -m pip install .`，然后在任意工作目录运行 `python -m agentrunner --help`。例如，`python -m agentrunner run -- python my_script.py` 会提交一个独立运行的命令并返回 Job ID；`python -m agentrunner show JOB-ID` 可以查询状态。

任务页面需要手动启动：在一个终端运行 `python -m agentrunner serve`，在另一个终端运行 `python -m agentrunner ui` 并打开输出的本地地址。提交 Workflow 可用 `python -m agentrunner submit workflow.yaml`。默认数据目录是用户目录下的 `.agentrunner`；测试时可用 `AGENTRUNNER_HOME` 指定隔离目录。

当前没有一键安装包、自动启动、系统托盘或正式的桌面操作界面。Codex 聊天回调需要有效的原聊天 ID、本机可用的 `codex queue` 和项目内的 [提交 Skill](.agents/skills/agent-runner/SKILL.md)、[回调 Skill](.agents/skills/agent-runner-callback/SKILL.md)；回调可能重复唤醒，Skill 会阻止重复处理。命令、状态及恢复边界见[本地契约](agentrunner/contract.md)，代码入口见[项目路由](structure.md)。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。Copyright 2026 Tao Mei。
