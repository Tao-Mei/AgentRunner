# AgentRunner

[English](README.md)

AgentRunner 让 AI Coding Agent 把已经规划好的、耗时的本地机器任务交给独立进程执行。Agent 可以结束当前等待，由 Runner 继续运行命令或工作流。若已配置 Codex 集成，任务结束后 Runner 可以向发起任务的原聊天发送回调。

## 当前状态

v0.1 是以 Windows 为首个验收平台的本地开发者版，还不是一键安装的桌面软件。当前需要手动启动本地 Service；尚无系统托盘、系统通知、自动启动或完整的图形化任务编排界面。

当前已实现：

- 独立运行的本地命令，以及“短任务同步执行、长任务转入后台”的自适应模式。
- 本地 YAML 工作流：步骤依赖、并行、资源容量锁、显式重试、超时、产物和 Finalizer。
- SQLite 持久状态、stdout/stderr 文件、结构化进度事件，以及可查看和取消任务的基础浏览器页面。
- 保守恢复：结果无法确认的步骤保持 `UNKNOWN`，须先核对证据并显式记录决定。
- 可选的 Codex 原聊天回调。重复消息仍可能再次唤醒聊天，回调 Skill 会阻止重复后续工作。

## 本地试用

需要 Windows 和 Python 3.11 或更新版本。在项目根目录安装：

```powershell
python -m pip install .
```

然后在脚本所在目录提交命令：

```powershell
python -m agentrunner run -- python my_script.py
```

返回结果包含 `JOB-...` 任务编号，可用它查询任务和输出：

```powershell
python -m agentrunner show JOB-ID
python -m agentrunner logs JOB-ID --stream stdout
```

如需浏览器页面，在一个终端运行 `python -m agentrunner serve`，在另一个终端运行 `python -m agentrunner ui`，打开输出的本地地址。页面仅在 Service 运行时可访问；关闭页面不会停止已接管的任务。

提交准备好的本地工作流可用 `python -m agentrunner submit workflow.yaml`。完整命令列表见 `python -m agentrunner --help`。默认数据目录是用户目录下的 `.agentrunner`；需要隔离数据时设置 `AGENTRUNNER_HOME`，并确保 CLI、Service 和 worker 使用同一个目录。

## Codex 集成与边界

[提交 Skill](.agents/skills/agent-runner/SKILL.md)说明何时把任务交给 Runner 并结束 Agent 当前 turn。[回调 Skill](.agents/skills/agent-runner-callback/SKILL.md)会在后续处理前核对 Job 和事件身份。回调要求用 `--callback-thread` 提供真实的原聊天 UUID，且本机 `codex queue` 可用。失败回调的自动重送要求 Service 保持运行。消息投递与用户可见回复都不保证恰好一次。

更详细的命令、状态与恢复边界见[本地契约](agentrunner/contract.md)，开发时按[项目路由](structure.md)查找代码。英文 [README](README.md)提供面向国际用户的介绍和本地试用步骤。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。Copyright 2026 Tao Mei。
