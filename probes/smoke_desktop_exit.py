"""Check that the tray Exit action stops an idle Runner and refuses active work."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from agentrunner.desktop import RunnerWindow


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentrunner-exit-") as data_dir:
        os.environ["AGENTRUNNER_HOME"] = data_dir
        app = QApplication([])

        blocked = RunnerWindow()
        with (patch("agentrunner.desktop.store.list_jobs", return_value=[
                  {"id": "JOB-active", "status": "RUNNING", "callback_status": "NOT_REQUESTED"}]),
              patch("agentrunner.desktop.QMessageBox.warning") as warning,
              patch("agentrunner.launcher.stop_service") as stop):
            blocked.exit_window()
            assert warning.call_count == 1
            assert "JOB-active" in warning.call_args.args[2]
            stop.assert_not_called()
            assert not blocked._allow_close

        idle = RunnerWindow()
        with (patch("agentrunner.desktop.store.list_jobs", return_value=[]),
              patch("agentrunner.launcher.stop_service", return_value={"status": "STOPPED"}) as stop):
            idle.exit_window()
            stop.assert_called_once()
            assert idle._allow_close

        app.quit()
    print("desktop exit: active work blocked, idle service stopped")


if __name__ == "__main__":
    main()
