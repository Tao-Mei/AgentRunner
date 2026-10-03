# Packaging route

| Task | Read first | Then |
| --- | --- | --- |
| Console CLI and frozen worker dispatch | [runner_exe.py](runner_exe.py) | [entry.py](../agentrunner/entry.py) |
| Desktop window and frozen worker dispatch | [desktop_exe.py](desktop_exe.py) | [desktop.py](../agentrunner/desktop.py) |
| Reproducible Windows build | [build.ps1](build.ps1) | [installer.nsi](installer.nsi) |
| Installation folder, shortcuts, bundled icons and global Skills | [installer.nsi](installer.nsi) | [install-preflight.ps1](install-preflight.ps1), [icon assets](../agentrunner/assets/agentrunner.png) |
