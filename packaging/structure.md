# Packaging route

| Task | Read first | Then |
| --- | --- | --- |
| Console CLI and frozen worker dispatch | [runner_exe.py](runner_exe.py) | [entry.py](../agentrunner/entry.py) |
| Desktop window and frozen worker dispatch | [desktop_exe.py](desktop_exe.py) | [desktop.py](../agentrunner/desktop.py) |
| Reproducible Windows build | [build.ps1](build.ps1) | [installer.nsi](installer.nsi) |
| Installation folder, shortcuts, bundled icons and global Skills | [installer.nsi](installer.nsi) | [install-preflight.ps1](install-preflight.ps1), [icon assets](../agentrunner/assets/agentrunner.png) |

| 程序版本、Windows 文件属性与安装包命名 | [version_info.py](version_info.py) | [版本常量](../agentrunner/__init__.py)、[build.ps1](build.ps1)、[installer.nsi](installer.nsi) |
| Sandbox Skill discovery and repair | [find-runner.ps1](find-runner.ps1) | [repair-skills.ps1](repair-skills.ps1), [resolver checks](../probes/smoke_skill_location.ps1) |
