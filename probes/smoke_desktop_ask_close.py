"""Closing while sending a question must retain window-close semantics."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QSettings
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from agentrunner.desktop import RunnerWindow


def main() -> None:
    test_root = Path(__file__).resolve().parent / ".probe-state"
    test_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=test_root, prefix="ask-close-") as root:
        settings = QSettings(str(Path(root) / "settings.ini"), QSettings.Format.IniFormat)
        with patch.dict(os.environ, {"AGENTRUNNER_HOME": root}), patch(
            "agentrunner.desktop.QSettings", return_value=settings
        ):
            app = QApplication([])
            window = RunnerWindow()
            for tray_setting in (False, True):
                window.close_checkbox.setChecked(tray_setting)
                window.ask_worker = object()
                event = QCloseEvent()
                with patch.object(window.tray, "isVisible", return_value=False):
                    window.closeEvent(event)
                assert not event.isAccepted(), "Question sender was destroyed before finishing"
                with patch.object(window, "close") as close, patch.object(window, "exit_window") as exit_program:
                    window._ask_finished()
                    exit_program.assert_not_called()
                    close.assert_called_once()
            window.close_checkbox.setChecked(True)
            window.ask_worker = object()
            with patch.object(window.tray, "isVisible", return_value=True), patch.object(window, "hide") as hide:
                window.closeEvent(QCloseEvent())
                hide.assert_called_once()
                assert window.ask_worker is not None
                assert not window._close_when_ask_done
            window.ask_worker = None
            window.timer.stop()
            app.quit()
    print("Pending question finishes, then ordinary window close resumes")


if __name__ == "__main__":
    main()
