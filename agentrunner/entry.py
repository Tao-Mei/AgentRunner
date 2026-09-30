"""Shared CLI and frozen-process entry point.

A frozen executable cannot spawn ``python -m agentrunner.worker`` because
``sys.executable`` is the executable itself. Its private worker modes are
handled here before CLI argument parsing or desktop UI initialization.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "_worker":
        from .worker import run

        return run(args[1])
    if len(args) == 2 and args[0] == "_workflow_worker":
        from .workflow_worker import run

        return run(args[1])
    if args == ["_service"]:
        from .server import serve

        serve()
        return 0
    from .cli import main as cli_main

    return cli_main(args)
