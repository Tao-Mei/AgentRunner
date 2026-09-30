"""PyInstaller entry point for the windowed desktop application."""

import sys

from agentrunner.entry import main as runner_main


if __name__ == "__main__":
    if (len(sys.argv) == 3 and sys.argv[1] in {"_worker", "_workflow_worker"}) or sys.argv[1:] == ["_service"]:
        raise SystemExit(runner_main())
    from agentrunner.desktop import main as desktop_main

    raise SystemExit(desktop_main(sys.argv[1:]))
