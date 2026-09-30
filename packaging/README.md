# Windows packaging

This directory holds entry points and build scripts for the Windows desktop distribution. Build output stays under `.build/` and `.dist/` and is not committed. The regular Python package remains usable without the desktop dependency; the installed application will bundle its own Python runtime.

See [structure.md](structure.md) for the local build route. A v0.2 preview installer has passed clean-VM checks for no-Python execution, a detached job, notification, upgrade, and uninstall. The installed Codex chat and desktop diagnosis paths still need end-to-end acceptance.

The installer checks for running AgentRunner processes before replacing files. On upgrade or uninstall it first asks an idle local Service to stop; active or unresolved Jobs and pending callbacks block that stop. Closing the desktop window does not cancel a Job. The tray's **Exit** action stops an idle Service and closes the window; it refuses to exit while Jobs or callbacks still need attention. Uninstall preserves the user's `.agentrunner` task data and removes only the known files from installer-owned global Skills.
