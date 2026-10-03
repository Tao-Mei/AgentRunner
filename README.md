# AgentRunner

[简体中文](README.zh-CN.md)

AgentRunner hands deterministic, long-running local tasks from an AI coding agent to an independent process. The agent can stop waiting while the Runner executes the command or workflow. When a task finishes, the Runner can send a callback to the originating Codex chat if that integration has been configured.

## Current status

Version 0.1 is the validated Windows-first developer baseline. A v0.2 Windows desktop preview installer is now available, including a task window, tray, history controls, and Codex Skills. This is an early preview, not a stable release; cross-project chat and desktop-question acceptance remains pending.

The current implementation provides:

- Detached local commands and an adaptive mode that runs short commands synchronously and promotes longer ones to the background.
- Local YAML workflows with dependencies, parallel steps, resource capacity locks, explicit retries, timeouts, artifacts, and finalizers.
- Persistent SQLite job state, files for stdout and stderr, structured progress events, and a basic browser page for viewing and cancelling jobs.
- Conservative recovery: a step with an unconfirmed outcome remains `UNKNOWN` until a person checks the evidence and records a decision.
- Optional Codex chat callbacks. Duplicate messages may still wake the chat, while the callback skill suppresses duplicate follow-up work.

## Try it locally

### Windows desktop preview

[Download the Windows installer](https://github.com/Tao-Mei/AgentRunner/releases/download/v0.2.0-preview.1/AgentRunner-Setup-0.2.0-dev.exe) · [Release notes and SHA256 checksums](https://github.com/Tao-Mei/AgentRunner/releases/tag/v0.2.0-preview.1)

1. Download and run `AgentRunner-Setup-0.2.0-dev.exe`; choose the installer, not GitHub's source ZIP.
2. Choose an installation folder and optional desktop shortcut, then open AgentRunner from the Start menu or shortcut.
3. Select **Help** for usage instructions. Python and the companion Codex Skills are included.
4. For chat handoff and callbacks, install and configure Codex yourself and authenticate as required by Codex, then invoke `$agent-runner` in a chat. If the new Skills are not recognized, reopen Codex and try a new chat.

AgentRunner does not manage Codex accounts or read or store Codex login credentials. It invokes the local Codex program for chat integration; Codex handles authentication. Without Codex, the task window and local Runner commands remain available, but Codex chat handoff and callbacks do not. This is a Windows x64 preview; no macOS/Linux installer is provided.

The wizard lets you choose an empty installation folder, opt into a desktop shortcut, and launch the app on completion. Upgrades reuse the registered folder; to move an existing installation, uninstall first and reinstall in the new folder. Skills discover the registered installation location. The **Help** button explains controls, tray behavior, questions and history. Drag job headers to reorder columns or click them to sort; preferences are saved. Jobs support an optional note and a history lock. **Clean history** removes unlocked finished jobs and Runner logs only after callbacks and goal recovery are resolved, retaining work artifacts and callback deduplication records. Completed, failed and cancelled jobs are included. Cleanup cannot recover removed logs or notes.

In a Codex chat, invoke `$agent-runner` and describe a deterministic local task, its working directory, and expected outputs. The Skill uses the installed Runner. The task window displays jobs, steps, logs and artifacts. **Ask Agent** queues a preset or custom question with one snapshot in the originating chat; queue acceptance does not mean that Codex has answered. Closing the window does not cancel a job. **Exit** in the tray refuses to stop while jobs or callbacks still need attention. Upgrade or uninstall only after that work is resolved; uninstall preserves job data and interface settings.

In goal mode, ending a turn alone does not suspend automatic continuation. With explicit user authorization, `run` or `submit` can use `--pause-goal` with `--callback-thread`; only `goal_handoff.status=PAUSED` confirms suspension. The matching callback Skill restores the same goal after handling the result. This uses an experimental local Codex protocol without atomic compare-and-set: changed or uncertain goal state needs human review and must not be blindly restored. The installed pause/completion/callback/restore path has been verified on the development computer; acceptance in another project chat and desktop questions remains pending.

### Python core

Requirements: Windows and Python 3.11 or newer. From the repository root, install the package:

```powershell
python -m pip install .
```

You can then submit a command from the directory containing your script:

```powershell
python -m agentrunner run -- python my_script.py
```

The response contains a `JOB-...` ID. Use it to inspect the task:

```powershell
python -m agentrunner show JOB-ID
python -m agentrunner logs JOB-ID --stream stdout
```

For the local browser page, run `python -m agentrunner serve` in one terminal. In another terminal, run `python -m agentrunner ui` and open the printed local URL. The page is available only while the service is running; closing the page does not stop an accepted job.

To submit a prepared local workflow, use `python -m agentrunner submit workflow.yaml`. Run `python -m agentrunner --help` for all commands. Job data is stored in `.agentrunner` under your user directory by default. Set `AGENTRUNNER_HOME` when you need an isolated data directory; the CLI, service, and workers must use the same one.

Notes can be edited directly by double-clicking a Note cell or typing in the details note field; both save automatically to the same job. The compact `L` column uses clickable open/closed lock icons. Hover over its header for the lock/unlock hint.

## Codex integration and limits

The [submission skill](.agents/skills/agent-runner/SKILL.md) describes when an agent should hand work to the Runner and stop its turn. The [callback skill](.agents/skills/agent-runner-callback/SKILL.md) checks job and event identity before follow-up work. A callback requires a valid originating chat UUID supplied with `--callback-thread` and a working local `codex queue`. The service must be running for automatic retries of failed callback delivery. Delivery and user-facing replies are not guaranteed exactly once.

The detailed [runtime contract](agentrunner/contract.md) and [project navigation](structure.md) are currently in Chinese. The English overview and commands above are sufficient to try a local command; the Chinese [README](README.zh-CN.md) is maintained for day-to-day development and use.

## License

Apache License 2.0. See [LICENSE](LICENSE). Copyright 2026 Tao Mei.
