# AgentRunner

[English](README.md)

AgentRunner 让 AI Coding Agent 把已经规划好的、耗时的本地机器任务交给独立进程执行。Agent 可以结束当前等待，由 Runner 继续运行命令或工作流。若已配置 Codex 集成，任务结束后 Runner 可以向发起任务的原聊天发送回调。

## 当前状态

v0.1 是已验收的 Windows 本地开发者版。现在提供 v0.2 Windows 桌面预览版安装包，包含任务窗口、托盘、历史管理及 Codex 配套 Skill。该版本供早期试用，尚非稳定版；跨项目聊天及界面提问仍需进一步实测。

当前已实现：

- 独立运行的本地命令，以及“短任务同步执行、长任务转入后台”的自适应模式。
- 本地 YAML 工作流：步骤依赖、并行、资源容量锁、显式重试、超时、产物和 Finalizer。
- SQLite 持久状态、stdout/stderr 文件、结构化进度事件，以及可查看和取消任务的基础浏览器页面。
- 保守恢复：结果无法确认的步骤保持 `UNKNOWN`，须先核对证据并显式记录决定。
- 可选的 Codex 原聊天回调。重复消息仍可能再次唤醒聊天，回调 Skill 会阻止重复后续工作。

## 本地试用

### Windows 桌面预览版

[下载 Windows 安装包](https://github.com/Tao-Mei/AgentRunner/releases/download/v0.2.0-preview.1/AgentRunner-Setup-0.2.0-dev.exe) · [版本说明与 SHA256 校验文件](https://github.com/Tao-Mei/AgentRunner/releases/tag/v0.2.0-preview.1)

1. 下载 `AgentRunner-Setup-0.2.0-dev.exe` 并双击运行；请选择安装包，不是 GitHub 的源码 ZIP。
2. 按向导选择安装位置及是否创建桌面快捷方式，完成后从开始菜单或快捷方式打开 AgentRunner。
3. 在窗口中点击“使用帮助”查看操作说明。安装包自带 Python，并自动安装 Codex 配套 Skill。
4. 如需聊天交接和回调，用户自行安装、配置 Codex，并按 Codex 的要求完成认证；随后在聊天中调用 `$agent-runner`。如果当前聊天未识别新 Skill，重新打开 Codex 后新建聊天再试。

AgentRunner 不管理 Codex 账号，也不读取或保存 Codex 登录凭据。它调用本机 Codex 程序完成聊天集成，认证由 Codex 自己处理。没有 Codex 时仍可打开界面及使用本地 Runner 命令，但不能使用 Codex 聊天交接与回调。该包为 Windows x64 预览版；macOS/Linux 不提供安装包。

向导允许选择专用空安装目录、是否创建桌面快捷方式，以及安装后启动程序。升级沿用登记目录；迁移已有安装时先卸载，再选新目录安装。Skill 通过安装登记找到程序。窗口“使用帮助”解释按钮、托盘、提问及历史管理。拖动表头可调整列顺序，点击表头切换排序，显示偏好会保存。任务支持默认空白的备注及保留锁。“一键清理”移除未锁定且已完成、失败或取消的任务和 Runner 日志，但跳过回调或目标恢复尚未结束的任务；实际工作产物和回调去重记录保留。清理后的日志和备注无法在窗口恢复。

在 Codex 聊天调用 `$agent-runner`，说明确定的本地任务、工作目录和预期产物，Skill 会使用安装版 Runner。任务窗口可查看任务、步骤、日志与产物。“询问 Agent”将预设或自定义问题及一次事实快照入队到原聊天；入队成功不代表 Codex 已回复。关闭窗口不取消任务；托盘“退出”在任务或回调仍需处理时会拒绝退出。升级或卸载前应先完成或处理这些工作；卸载保留任务数据和界面设置。

目标模式下，仅结束当前 turn 不会暂停自动续跑。经用户明确授权，`run` 或 `submit` 可同时使用 `--pause-goal` 和 `--callback-thread`；只有返回 `goal_handoff.status=PAUSED` 才确认暂停。对应回调 Skill 处理结果后恢复原目标。此功能使用没有原子比较更新的 Codex 本地实验协议：目标已变更或状态不明确时需人工核对，不得盲目恢复。开发机安装版的暂停、完成、回调、恢复链路已验证；另一项目聊天及界面提问验收仍未完成。

### Python 内核

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

备注可以双击左侧“备注”单元格直接编辑，也可以在右侧详情输入，两处自动保存到同一任务。最左侧 `L` 列显示可点击的开锁／闭锁图标，鼠标指向表头会提示“锁定/解锁”。

## Codex 集成与边界

[提交 Skill](.agents/skills/agent-runner/SKILL.md)说明何时把任务交给 Runner 并结束 Agent 当前 turn。[回调 Skill](.agents/skills/agent-runner-callback/SKILL.md)会在后续处理前核对 Job 和事件身份。回调要求用 `--callback-thread` 提供真实的原聊天 UUID，且本机 `codex queue` 可用。失败回调的自动重送要求 Service 保持运行。消息投递与用户可见回复都不保证恰好一次。

更详细的命令、状态与恢复边界见[本地契约](agentrunner/contract.md)，开发时按[项目路由](structure.md)查找代码。英文 [README](README.md)提供面向国际用户的介绍和本地试用步骤。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。Copyright 2026 Tao Mei。
