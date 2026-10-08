# Windows packaging

This directory holds entry points and build scripts for the Windows desktop distribution. Build output stays under `.build/` and `.dist/` and is not committed. The regular Python package remains usable without the desktop dependency; the installed application will bundle its own Python runtime.

See [structure.md](structure.md) for the local build route. A v0.2 preview installer has passed clean-VM checks for no-Python execution, a detached job, notification, upgrade, and uninstall. The installed Codex chat and desktop diagnosis paths still need end-to-end acceptance.

The installer checks for running AgentRunner processes before replacing files. On upgrade or uninstall it first asks an idle local Service to stop; active or unresolved Jobs and pending callbacks block that stop. Closing the desktop window does not cancel a Job. The tray's **Exit** action stops an idle Service and closes the window; it refuses to exit while Jobs or callbacks still need attention. Uninstall preserves the user's `.agentrunner` task data and removes only the known files from installer-owned global Skills.


Version constants are maintained in `agentrunner/__init__.py`; the Python package uses the corresponding PEP 440 version in `pyproject.toml`. `version_info.py` rejects a mismatch and generates resources for both executables. The same display version supplies the installer filename and Windows installation registry. For preview 2: display/tag `0.2.0-preview.2` / `v0.2.0-preview.2`, Python `0.2.0rc2`, Windows numeric version `0.2.0.2`.

## Skill discovery in a sandbox

The installer writes a machine-local `scripts/runner-location.ini` beside each global Skill resolver, recording the executable and actual task data root. It is ignored by Git and removed only with installer-owned Skills. `find-runner.ps1` is the canonical resolver; the two bundled copies must match it. Run the resolver and Runner in the same PowerShell process so its `AGENTRUNNER_HOME` setting survives. Skill paths come from the loaded Skill location, not redirected environment folders. Stale configuration fails closed instead of switching databases. Explicit absolute `AGENTRUNNER_HOME` overrides remain available for intentional isolated jobs.

Existing installations can update their installer-owned Skills without replacing binaries or stopping jobs. From this repository, in the normal installation user's session, run `packaging/repair-skills.ps1 -InstallDir ABSOLUTE-INSTALL-DIR -DataRoot ACTUAL-DATA-DIR -SkillsRoot ACTUAL-CODEX-SKILLS-DIR`. It updates only Skill instructions, resolvers and local manifests and refuses unowned Skills. Future installs generate the manifest automatically, using an explicit installer-session `AGENTRUNNER_HOME` or the installation user's `.agentrunner` directory.

The manifest grants no sandbox permissions. Read/process/write/desktop denial needs appropriate approved access; never create a second sandbox database or resubmit to work around it. Run `probes/smoke_skill_location.ps1` for bounded resolver checks. This source fix does not replace the published preview.2 installer.
