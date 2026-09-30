"""Windows-first Qt task window for the local Runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QStyle, QTabWidget, QTableWidget, QTableWidgetItem,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import codex_command, log_text, store


def startup_trace(stage: str) -> None:
    target = os.environ.get("AGENTRUNNER_DESKTOP_TRACE")
    if target:
        with Path(target).open("a", encoding="utf-8") as output:
            output.write(f"{datetime.now(timezone.utc).isoformat()} {os.getpid()} {stage}\n")


WORDS = {
    "en": {
        "jobs": "Jobs", "details": "Details", "steps": "Steps", "output": "Output",
        "events": "Events", "artifacts": "Artifacts", "refresh": "Refresh",
        "cancel": "Cancel job", "open_folder": "Open job folder", "ask": "Ask Agent",
        "pause": "Pause next steps", "continue": "Resume steps", "stop_after": "Stop after current steps",
        "stop_confirm": "Let active steps finish, skip remaining steps, and run finalizers for {job_id}?",
        "paused": "Next steps paused", "stopping": "Stopping after active steps",
        "question": "Question", "preset": "Quick question", "language": "Language",
        "close_to_tray": "Close window to tray", "status": "Status", "created": "Created",
        "name": "Name / ID", "step": "Step", "attempts": "Attempts", "progress": "Progress", "error": "Error",
        "select": "Select a job", "no_chat": "This job has no originating Codex chat.",
        "empty_question": "Enter a question or choose a preset.",
        "ask_sent": "Question queued in the originating Codex chat.",
        "ask_failed": "Could not queue the question: {error}",
        "cancel_confirm": "Request cancellation of {job_id}?",
        "cancel_title": "Cancel job", "open": "Open window",
        "exit": "Exit", "exit_blocked": "AgentRunner is still handling jobs or callbacks: {jobs}. Finish or resolve them before exiting.",
        "exit_error": "Could not exit AgentRunner: {error}",
        "tray_unavailable": "System tray is unavailable; the window will close.",
        "cancel_requested": "Cancellation requested for {job_id}.",
        "cancel_unavailable": "Cancellation is unavailable for {job_id}.",
        "control_accepted": "{action} requested for {job_id}.",
        "control_unavailable": "{action} is unavailable for {job_id}.",
        "completed": "Job completed", "failed": "Job failed", "cancelled": "Job cancelled",
        "attention": "AgentRunner needs attention",
        "no_data": "No jobs yet", "ask_busy": "Sending question...",
        "presets": ["", "What is happening now?", "Is this task stuck?", "Why is it taking so long?", "Do I need to intervene?", "Explain the latest error"],
    },
    "zh": {
        "jobs": "任务", "details": "任务详情", "steps": "步骤", "output": "输出",
        "events": "事件", "artifacts": "产物", "refresh": "刷新",
        "cancel": "取消任务", "open_folder": "打开任务文件夹", "ask": "询问 Agent",
        "pause": "暂停后续步骤", "continue": "恢复步骤调度", "stop_after": "当前步骤结束后停止",
        "stop_confirm": "让 {job_id} 的当前步骤执行完，跳过后续步骤，再运行收尾步骤吗？",
        "paused": "后续步骤已暂停", "stopping": "当前步骤结束后停止",
        "question": "自定义问题", "preset": "常见问题", "language": "界面语言",
        "close_to_tray": "点击关闭时收起到托盘", "status": "状态", "created": "创建时间",
        "name": "名称 / 编号", "step": "步骤", "attempts": "尝试次数", "progress": "进度", "error": "错误",
        "select": "请选择任务", "no_chat": "此任务没有配置原 Codex 聊天。",
        "empty_question": "请输入问题或选择常见问题。",
        "ask_sent": "问题已入队到发起任务的 Codex 聊天。",
        "ask_failed": "问题未能入队：{error}",
        "cancel_confirm": "请求取消 {job_id} 吗？",
        "cancel_title": "取消任务", "open": "打开界面",
        "exit": "退出", "exit_blocked": "仍有任务或回调正在处理：{jobs}。请等待完成或处理后再退出。",
        "exit_error": "无法退出 AgentRunner：{error}",
        "tray_unavailable": "系统托盘不可用，将关闭界面。",
        "cancel_requested": "已请求取消任务 {job_id}。",
        "cancel_unavailable": "任务 {job_id} 当前无法取消。",
        "control_accepted": "已请求对任务 {job_id} 执行“{action}”。",
        "control_unavailable": "任务 {job_id} 当前无法执行“{action}”。",
        "completed": "任务已完成", "failed": "任务失败", "cancelled": "任务已取消",
        "attention": "AgentRunner 需要处理",
        "no_data": "暂无任务", "ask_busy": "正在发送问题……",
        "presets": ["", "现在是什么情况？", "任务是不是卡住了？", "为什么这么久还没完成？", "现在需要我干预吗？", "分析最近的错误"],
    },
}

STATUS_LABELS = {
    "en": {"CREATED": "Created", "RUNNING": "Running", "FINALIZING": "Finalizing",
           "COMPLETED": "Completed", "FAILED": "Failed", "CANCELLED": "Cancelled",
           "UNKNOWN": "Needs review", "RESUMING": "Resuming", "PENDING": "Pending",
           "TIMED_OUT": "Timed out", "SKIPPED": "Skipped"},
    "zh": {"CREATED": "已创建", "RUNNING": "运行中", "FINALIZING": "收尾中",
           "COMPLETED": "已完成", "FAILED": "失败", "CANCELLED": "已取消",
           "UNKNOWN": "待核对", "RESUMING": "恢复中", "PENDING": "待执行",
           "TIMED_OUT": "超时", "SKIPPED": "已跳过"},
}


def log_tail(job_id: str, stream: str, step_id: str | None = None, limit: int = 32_768) -> str:
    path = store.job_dir(job_id)
    if step_id:
        path = path / "steps" / step_id
    path = path / f"{stream}.log"
    return log_text.read_tail(path, limit)


def task_output(job_id: str, steps: list[dict], limit_per_stream: int = 16_384) -> str:
    """Show the logs that actually belong to each workflow step."""
    if not steps:
        return "\n".join(filter(None, (log_tail(job_id, stream, limit=limit_per_stream)
                                        for stream in ("stdout", "stderr"))))
    sections = []
    for step in steps:
        for stream in ("stdout", "stderr"):
            tail = log_tail(job_id, stream, step["step_id"], limit_per_stream)
            if tail:
                sections.append(f"[{step['step_id']} / {stream}]\n{tail}")
    return "\n\n".join(sections)


def diagnosis_snapshot(job: dict, steps: list[dict], events: list[dict]) -> str:
    """Bound an Ask Agent message; this is a single observation, not ownership transfer."""
    facts = {
        "job_id": job["id"], "status": job["status"], "exit_code": job["exit_code"],
        "created_at": job["created_at"], "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"), "error": job.get("error"),
        "steps": [{"id": row["step_id"], "status": row["status"], "attempts": row["attempts"],
                   "exit_code": row.get("exit_code"), "error": row.get("error")}
                  for row in steps],
        "recent_events": events[-12:],
        "recent_stdout": log_tail(job["id"], "stdout", limit=2_000),
        "recent_stderr": log_tail(job["id"], "stderr", limit=2_000),
        "recent_step_output": task_output(job["id"], steps, limit_per_stream=500)[-3_000:],
    }
    return json.dumps(facts, ensure_ascii=False, default=str)[:10_000]


class AskWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, thread_id: str, question: str, snapshot: str) -> None:
        super().__init__()
        self.thread_id = thread_id
        self.question = question
        self.snapshot = snapshot

    def run(self) -> None:
        message = (
            "AgentRunner ASK_AGENT_V1. Answer the user's one-time question using this Job snapshot. "
            "Runner keeps executing the Job; do not assume ownership or start a polling loop.\n"
            f"Question: {self.question}\nSnapshot: {self.snapshot}"
        )
        try:
            result = subprocess.run(
                [codex_command.resolve(), "queue", "--thread", self.thread_id, "--message", message],
                capture_output=True, text=True, timeout=25, check=False,
            )
            if result.returncode != 0 or "Queued message " not in result.stdout:
                self.done.emit(False, f"codex queue exited {result.returncode}")
            else:
                self.done.emit(True, "")
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.done.emit(False, type(exc).__name__)


class RunnerWindow(QMainWindow):
    def __init__(self, requested_job_id: str | None = None, request_seq: int = 0) -> None:
        super().__init__()
        self.settings = QSettings("Tao Mei", "AgentRunner")
        stored_language = self.settings.value("language", "zh" if QLocale.system().name().startswith("zh") else "en")
        self.language = stored_language if stored_language in WORDS else "en"
        self.selected_id: str | None = requested_job_id if requested_job_id and store.get_job(requested_job_id) else None
        self.desktop_request_seq = request_seq
        self.previous_statuses: dict[str, tuple[str, str]] | None = None
        self.ask_worker: AskWorker | None = None
        self._close_when_ask_done = False
        self._allow_close = False
        self.setWindowTitle("AgentRunner")
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f7fb; color: #172338; }
            QTableWidget, QPlainTextEdit, QLineEdit, QComboBox, QTabWidget::pane {
                background: white; border: 1px solid #d8e1ed; border-radius: 5px;
            }
            QTableWidget { gridline-color: #edf1f6; selection-background-color: #dceaff; }
            QHeaderView::section { background: #e9eff7; padding: 6px; border: 0; color: #344763; }
            QPushButton { background: #e8f0fb; border: 1px solid #bed0e7; border-radius: 5px;
                          padding: 7px 12px; }
            QPushButton:hover { background: #d7e8fc; }
            QPushButton:disabled { color: #8896a7; background: #f1f3f6; }
            QLineEdit { padding: 6px; }
        """)
        self.resize(1120, 760)
        self._build()
        self._translate()
        self._make_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.show_timer = QTimer(self)
        self.show_timer.timeout.connect(self._poll_show_requests)
        self.show_timer.start(700)
        self.refresh()

    def tr(self, key: str) -> str:
        return WORDS[self.language][key]

    def status_text(self, status: str) -> str:
        return STATUS_LABELS[self.language].get(status, status)

    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.language_label = QLabel()
        self.language_combo = QComboBox()
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(0 if self.language == "zh" else 1)
        self.language_combo.currentIndexChanged.connect(self._change_language)
        self.close_checkbox = QCheckBox()
        self.close_checkbox.setChecked(self.settings.value("close_to_tray", False, type=bool))
        self.close_checkbox.toggled.connect(lambda value: self.settings.setValue("close_to_tray", value))
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.language_label)
        top.addWidget(self.language_combo)
        top.addSpacing(20)
        top.addWidget(self.close_checkbox)
        top.addStretch()
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.jobs_table = QTableWidget(0, 3)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobs_table.itemSelectionChanged.connect(self._job_selected)
        self.jobs_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.jobs_table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.status_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.progress = QProgressBar()
        right_layout.addWidget(self.title_label)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.error_label)
        right_layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self._cancel)
        self.pause_button = QPushButton()
        self.pause_button.clicked.connect(lambda: self._workflow_control("pause"))
        self.continue_button = QPushButton()
        self.continue_button.clicked.connect(lambda: self._workflow_control("continue"))
        self.stop_button = QPushButton()
        self.stop_button.clicked.connect(lambda: self._workflow_control("stop-after-current"))
        self.folder_button = QPushButton()
        self.folder_button.clicked.connect(self._open_folder)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.continue_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.folder_button)
        actions.addStretch()
        right_layout.addLayout(actions)
        self.tabs = QTabWidget()
        self.steps_table = QTableWidget(0, 3)
        self.steps_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.steps_table.horizontalHeader().setStretchLastSection(True)
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.events_text = QPlainTextEdit()
        self.events_text.setReadOnly(True)
        self.artifacts_text = QPlainTextEdit()
        self.artifacts_text.setReadOnly(True)
        for widget in (self.steps_table, self.output_text, self.events_text, self.artifacts_text):
            self.tabs.addTab(widget, "")
        right_layout.addWidget(self.tabs)
        ask_layout = QFormLayout()
        self.preset_label = QLabel()
        self.question_label = QLabel()
        self.preset_combo = QComboBox()
        self.question_input = QLineEdit()
        self.ask_button = QPushButton()
        self.ask_button.clicked.connect(self._ask)
        ask_layout.addRow(self.preset_label, self.preset_combo)
        ask_layout.addRow(self.question_label, self.question_input)
        right_layout.addLayout(ask_layout)
        right_layout.addWidget(self.ask_button)
        self.ask_info_label = QLabel()
        self.ask_info_label.setWordWrap(True)
        right_layout.addWidget(self.ask_info_label)
        splitter.addWidget(right)
        splitter.setSizes([350, 770])
        layout.addWidget(splitter)
        self.setCentralWidget(root)

    def _translate(self) -> None:
        self.language_label.setText(self.tr("language"))
        self.close_checkbox.setText(self.tr("close_to_tray"))
        self.refresh_button.setText(self.tr("refresh"))
        self.jobs_table.setHorizontalHeaderLabels([self.tr("name"), self.tr("status"), self.tr("created")])
        self.steps_table.setHorizontalHeaderLabels([self.tr("step"), self.tr("status"), self.tr("attempts")])
        for index, key in enumerate(("steps", "output", "events", "artifacts")):
            self.tabs.setTabText(index, self.tr(key))
        self.cancel_button.setText(self.tr("cancel"))
        self.pause_button.setText(self.tr("pause"))
        self.continue_button.setText(self.tr("continue"))
        self.stop_button.setText(self.tr("stop_after"))
        self.folder_button.setText(self.tr("open_folder"))
        self.ask_button.setText(self.tr("ask"))
        self.preset_combo.clear()
        self.preset_combo.addItems(self.tr("presets"))
        self.question_input.setPlaceholderText(self.tr("question"))
        self.preset_label.setText(self.tr("preset"))
        self.question_label.setText(self.tr("question"))
        self.title_label.setText(self.selected_id or self.tr("select"))
        if hasattr(self, "tray"):
            self.tray_open.setText(self.tr("open"))
            self.tray_exit.setText(self.tr("exit"))

    def _change_language(self) -> None:
        self.language = self.language_combo.currentData()
        self.settings.setValue("language", self.language)
        self._translate()
        self.refresh()

    def _make_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("AgentRunner")
        menu = QMenu(self)
        self.tray_open = menu.addAction(self.tr("open"))
        self.tray_open.triggered.connect(self.show_window)
        self.tray_exit = menu.addAction(self.tr("exit"))
        self.tray_exit.triggered.connect(self.exit_window)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _poll_show_requests(self) -> None:
        try:
            sequence, requested_job_id = store.desktop_show_request()
            if sequence <= self.desktop_request_seq:
                return
            self.desktop_request_seq = sequence
            if requested_job_id and store.get_job(requested_job_id):
                self.selected_id = requested_job_id
            self.refresh()
            self.show_window()
        except Exception as exc:
            self.statusBar().showMessage(f"{type(exc).__name__}: {exc}")

    def exit_window(self) -> None:
        if self.ask_worker is not None:
            QMessageBox.information(self, self.tr("exit"), self.tr("ask_busy"))
            return
        jobs = store.list_jobs()
        blocking = [job["id"] for job in jobs if job["status"] in
                    {"CREATED", "RUNNING", "FINALIZING", "RESUMING", "UNKNOWN"} or
                    job["callback_status"] in {"PENDING", "SENDING", "UNKNOWN"}]
        if blocking:
            QMessageBox.warning(self, self.tr("exit"), self.tr("exit_blocked").format(jobs=", ".join(blocking[:5])))
            return
        from .launcher import stop_service
        try:
            result = stop_service()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("exit"), self.tr("exit_error").format(error=exc))
            return
        if result["status"] == "BLOCKED":
            ids = list(result.get("active_jobs", [])) + list(result.get("pending_callbacks", []))
            QMessageBox.warning(self, self.tr("exit"), self.tr("exit_blocked").format(jobs=", ".join(ids[:5])))
            return
        self._allow_close = True
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event: object) -> None:  # Qt callback
        hide_to_tray = not self._allow_close and self.close_checkbox.isChecked() and self.tray.isVisible()
        if self.ask_worker is not None and not hide_to_tray:
            self._close_when_ask_done = True
            self.statusBar().showMessage(self.tr("ask_busy"))
            event.ignore()
            return
        if hide_to_tray:
            event.ignore()
            self.hide()
            return
        if self.close_checkbox.isChecked() and not self.tray.isVisible():
            self.statusBar().showMessage(self.tr("tray_unavailable"))
        event.accept()
        QApplication.instance().quit()

    def refresh(self) -> None:
        try:
            jobs = store.list_jobs()
            if jobs and self.selected_id is None:
                self.selected_id = jobs[0]["id"]
            latest = {job["id"]: (job["status"], job["callback_status"]) for job in jobs}
            if self.previous_statuses is not None:
                for job in jobs:
                    previous = self.previous_statuses.get(job["id"])
                    status, callback_status = latest[job["id"]]
                    if callback_status == "UNKNOWN" and (previous is None or previous[1] != "UNKNOWN"):
                        self._notify(job, attention=True)
                    elif (previous is None and status in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}) or (
                        previous is not None and previous[0] != status and
                        status in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}
                    ):
                        self._notify(job, attention=status == "UNKNOWN")
            self.previous_statuses = latest
            self.jobs_table.blockSignals(True)
            self.jobs_table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                for col, value in enumerate((job.get("name") or job["id"], self.status_text(job["status"]), job["created_at"])):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, job["id"])
                    self.jobs_table.setItem(row, col, item)
                if job["id"] == self.selected_id:
                    self.jobs_table.selectRow(row)
            self.jobs_table.blockSignals(False)
            if self.selected_id:
                self._show_detail()
            elif not jobs:
                self.statusBar().showMessage(self.tr("no_data"))
        except Exception as exc:
            self.statusBar().showMessage(f"{type(exc).__name__}: {exc}")

    def _notify(self, job: dict, attention: bool = False) -> None:
        if not self.tray.isVisible() or not QSystemTrayIcon.supportsMessages():
            return
        key = "attention" if attention else {"COMPLETED": "completed", "FAILED": "failed", "CANCELLED": "cancelled"}[job["status"]]
        icon = QSystemTrayIcon.MessageIcon.Information if job["status"] == "COMPLETED" and not attention else QSystemTrayIcon.MessageIcon.Warning
        self.tray.showMessage(self.tr(key), job["id"], icon, 8000)

    def _job_selected(self) -> None:
        rows = self.jobs_table.selectionModel().selectedRows()
        if rows:
            item = self.jobs_table.item(rows[0].row(), 0)
            self.selected_id = item.data(Qt.ItemDataRole.UserRole)
            self._show_detail()

    def _show_detail(self) -> None:
        if not self.selected_id:
            return
        job = store.get_job(self.selected_id)
        if not job:
            return
        steps = store.list_steps(self.selected_id) if job["kind"] == "workflow" else []
        events = store.list_events(self.selected_id)
        self.title_label.setText(job.get("name") or self.selected_id)
        control_state = (self.tr("stopping") if job["stop_after_current_requested"] else
                         self.tr("paused") if job["pause_requested"] else "")
        if job["callback_status"] == "UNKNOWN":
            control_state = f"{control_state} {self.tr('attention')}".strip()
        self.status_label.setText(f"{self.tr('status')}: {self.status_text(job['status'])} {control_state}    {self.selected_id}")
        error = job.get("error") or next((f"{step['step_id']}: {step['error']}" for step in reversed(steps)
                                          if step.get("error")), "")
        self.error_label.setText(f"{self.tr('error')}: {error}" if error else "")
        complete = sum(step["status"] in {"COMPLETED", "SKIPPED"} for step in steps)
        self.progress.setRange(0, len(steps) if steps else (0 if job["status"] == "RUNNING" else 1))
        self.progress.setValue(complete if steps else (1 if job["status"] == "COMPLETED" else 0))
        self.cancel_button.setEnabled(job["status"] in {"CREATED", "RUNNING"})
        workflow_running = job["kind"] == "workflow" and job["status"] == "RUNNING" and not job["cancel_requested"]
        self.pause_button.setEnabled(workflow_running and not job["pause_requested"] and not job["stop_after_current_requested"])
        self.continue_button.setEnabled(workflow_running and bool(job["pause_requested"]) and not job["stop_after_current_requested"])
        self.stop_button.setEnabled(workflow_running and not job["stop_after_current_requested"])
        self.ask_button.setEnabled(bool(job.get("callback_thread")) and self.ask_worker is None)
        if not job.get("callback_thread"):
            self.ask_info_label.setText(self.tr("no_chat"))
        elif self.ask_worker is None and self.ask_info_label.text() == self.tr("no_chat"):
            self.ask_info_label.clear()
        self.steps_table.setRowCount(len(steps))
        for row, step in enumerate(steps):
            for col, value in enumerate((step["step_id"], self.status_text(step["status"]), step["attempts"])):
                self.steps_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.output_text.setPlainText(task_output(self.selected_id, steps))
        self.events_text.setPlainText("\n".join(json.dumps(event, ensure_ascii=False, default=str) for event in events[-100:]))
        artifacts = [f"{step['step_id']}: {artifact['path']} ({artifact['size']} bytes)"
                     for step in steps for artifact in step.get("artifacts", [])]
        self.artifacts_text.setPlainText("\n".join(artifacts))

    def _cancel(self) -> None:
        if not self.selected_id:
            return
        if QMessageBox.question(self, self.tr("cancel_title"), self.tr("cancel_confirm").format(job_id=self.selected_id)) != QMessageBox.StandardButton.Yes:
            return
        from .cli import cancel_job

        result, _ = cancel_job(self.selected_id)
        key = "cancel_requested" if result.get("cancel_requested") else "cancel_unavailable"
        self.statusBar().showMessage(self.tr(key).format(job_id=self.selected_id))
        self.refresh()

    def _workflow_control(self, action: str) -> None:
        if not self.selected_id:
            return
        if action == "stop-after-current" and QMessageBox.question(
            self, self.tr("stop_after"), self.tr("stop_confirm").format(job_id=self.selected_id),
        ) != QMessageBox.StandardButton.Yes:
            return
        accepted = store.set_workflow_control(self.selected_id, action)
        labels = {"pause": "pause", "continue": "continue", "stop-after-current": "stop_after"}
        key = "control_accepted" if accepted else "control_unavailable"
        self.statusBar().showMessage(self.tr(key).format(action=self.tr(labels[action]), job_id=self.selected_id))
        self.refresh()

    def _open_folder(self) -> None:
        if self.selected_id:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(store.job_dir(self.selected_id))))

    def _ask(self) -> None:
        if not self.selected_id or self.ask_worker is not None:
            return
        question = self.question_input.text().strip() or self.preset_combo.currentText().strip()
        if not question:
            self.statusBar().showMessage(self.tr("empty_question"))
            return
        job = store.get_job(self.selected_id)
        if not job or not job.get("callback_thread"):
            self.statusBar().showMessage(self.tr("no_chat"))
            return
        steps = store.list_steps(self.selected_id) if job["kind"] == "workflow" else []
        snapshot = diagnosis_snapshot(job, steps, store.list_events(self.selected_id))
        self.ask_worker = AskWorker(job["callback_thread"], question, snapshot)
        self.ask_worker.done.connect(self._ask_done)
        self.ask_worker.finished.connect(self._ask_finished)
        self.ask_button.setEnabled(False)
        self.ask_info_label.setText(self.tr("ask_busy"))
        self.ask_worker.start()

    def _ask_done(self, success: bool, error: str) -> None:
        message = self.tr("ask_sent") if success else self.tr("ask_failed").format(error=error)
        self.ask_info_label.setText(message)
        self.statusBar().showMessage(message)

    def _ask_finished(self) -> None:
        self.ask_worker = None
        self.ask_button.setEnabled(True)
        if self._close_when_ask_done:
            self._close_when_ask_done = False
            self.close()


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments and (len(arguments) != 2 or arguments[0] != "--show-job"):
        raise ValueError("Expected --show-job JOB-ID")
    requested_job_id = arguments[1] if arguments else None
    startup_trace("before desktop claim")
    owner, request_seq = store.claim_desktop(requested_job_id)
    if not owner:
        startup_trace("routed to existing window")
        return 0
    startup_trace("desktop claim ready")
    startup_trace("before QApplication")
    app = QApplication([sys.argv[0]])
    startup_trace("after QApplication")
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "win32":
        app.setFont(QFont("Microsoft YaHei UI", 10))
    from .launcher import ensure_service

    service_error = ""
    try:
        startup_trace("before ensure_service")
        ensure_service()
        startup_trace("after ensure_service")
    except Exception as exc:
        service_error = f"{type(exc).__name__}: {exc}"
        startup_trace("service error: " + service_error)
    startup_trace("before RunnerWindow")
    try:
        window = RunnerWindow(requested_job_id, request_seq)
    except BaseException:
        store.release_desktop()
        raise
    startup_trace("after RunnerWindow")
    if service_error:
        window.statusBar().showMessage(service_error)

    app.aboutToQuit.connect(store.release_desktop)
    window.show_window()
    startup_trace("window shown")
    try:
        return app.exec()
    finally:
        store.release_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
