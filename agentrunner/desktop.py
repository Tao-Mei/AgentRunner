"""Windows-first Qt task window for the local Runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QStyledItemDelegate, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import DISPLAY_VERSION, codex_command, history, log_text, store
from .help_text import HELP


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
        "close_to_tray": "Close window to tray", "status": "Status", "created": "Created", "elapsed": "Run time", "total_elapsed": "Total run time",
        "name": "Task name", "job_id": "Task ID", "command_task": "Command task (unnamed)", "workflow_task": "Workflow (unnamed)", "local_time": "Local time on this computer", "step": "Step", "attempts": "Attempts", "progress": "Progress", "error": "Error",
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
        "close_to_tray": "点击关闭时收起到托盘", "status": "状态", "created": "创建时间", "elapsed": "已运行", "total_elapsed": "总计运行",
        "name": "任务名称", "job_id": "任务编号", "command_task": "命令任务（未命名）", "workflow_task": "工作流任务（未命名）", "local_time": "本机当地时间", "step": "步骤", "attempts": "尝试次数", "progress": "进度", "error": "错误",
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

WORDS['en'].update({
    'help': 'Help', 'clean': 'Clean history', 'locked': 'Locked', 'note': 'Note',
    'lock': 'Lock / unlock', 'locked_tip': 'Locked — click to unlock', 'unlocked_tip': 'Unlocked — click to lock',
    'clean_confirm': 'Remove all unlocked finished jobs and their Runner logs? Completed, failed and cancelled jobs qualify only after callbacks and goal recovery are resolved. Work files and callback deduplication records are kept.',
    'clean_result': 'Removed {count} jobs. Locked or unresolved jobs were kept.',
    'clean_error': 'Some log folders could not be removed; retry cleanup later:\n{errors}',
    'metadata_error': 'This job is no longer available.',
    'note_save_failed': 'Some task names or notes could not be saved. Copy the text or resolve the error before closing or cleaning history.',
})
WORDS['zh'].update({
    'help': '使用帮助', 'clean': '一键清理', 'locked': '锁定', 'note': '备注',
    'lock': '锁定/解锁', 'locked_tip': '已锁定，点击解锁', 'unlocked_tip': '未锁定，点击锁定',
    'clean_confirm': '清理所有未锁定且已结束的任务及其 Runner 日志吗？包括已完成、失败和取消的任务，但会跳过回调或目标恢复未处理完的任务。实际工作产物和回调去重记录保留。',
    'clean_result': '已清理 {count} 条任务；锁定或尚未处理完的任务已保留。',
    'clean_error': '部分日志目录未能删除，可稍后再次清理：\n{errors}',
    'metadata_error': '此任务已不在列表中。',
    'note_save_failed': '部分任务名称或备注未能保存。请先复制内容或处理保存错误，再关闭或清理历史。',
})


def elapsed_seconds(job: dict, now: datetime | None = None) -> int | None:
    """Wall time from recorded start; unknown outcomes have no invented end."""
    try:
        start = datetime.fromisoformat(job['started_at'])
        if start.tzinfo is None:
            return None
        if job['status'] in {'COMPLETED', 'FAILED', 'CANCELLED'}:
            end = datetime.fromisoformat(job['finished_at'])
        elif job['status'] in {'RUNNING', 'FINALIZING', 'RESUMING'}:
            end = now or datetime.now(timezone.utc)
        else:
            return None
        if end.tzinfo is None:
            return None
        return max(0, int((end - start).total_seconds()))
    except (KeyError, TypeError, ValueError):
        return None


def duration_text(seconds: int | None, language: str = 'en') -> str:
    if seconds is None:
        return '—'
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    units = ('天', '小时', '分', '秒') if language == 'zh' else ('d', 'h', 'm', 's')
    parts = [f'{value}{unit}' for value, unit in zip((days, hours, minutes, seconds), units) if value or unit == units[-1]]
    return ('' if language == 'zh' else ' ').join(parts)


def local_date_text(value: str | None) -> str:
    try:
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None:
            return '—'
        return instant.astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return '—'


def application_icon() -> QIcon:
    return QIcon(str(Path(__file__).with_name('assets') / 'agentrunner.ico'))


def lock_icon(locked: bool) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor('#1766d5' if locked else '#68778c'), 1.8))
    shackle = QPainterPath()
    if locked:
        shackle.moveTo(7, 10)
        shackle.lineTo(7, 7)
        shackle.cubicTo(7, 1, 17, 1, 17, 7)
        shackle.lineTo(17, 10)
    else:
        shackle.moveTo(11, 10)
        shackle.lineTo(11, 6)
        shackle.cubicTo(11, 1, 21, 1, 21, 6)
    painter.drawPath(shackle)
    painter.setBrush(QColor('#e8f0fb' if locked else '#f4f7fb'))
    painter.drawRoundedRect(4, 10, 15, 11, 2, 2)
    painter.drawEllipse(10, 14, 3, 3)
    painter.drawLine(11, 17, 11, 19)
    painter.end()
    return QIcon(pixmap)


class NoteDelegate(QStyledItemDelegate):
    opened = Signal(object)
    changed = Signal(str, str)
    closed = Signal()

    def createEditor(self, parent, option, index):
        editor = QPlainTextEdit(parent)
        editor.setProperty('job_id', index.data(Qt.ItemDataRole.UserRole))
        editor.textChanged.connect(lambda: self.changed.emit(editor.property('job_id'), editor.toPlainText()))
        editor.destroyed.connect(lambda: self.closed.emit())
        self.opened.emit(editor)
        return editor

    def setEditorData(self, editor, index):
        editor.blockSignals(True)
        editor.setPlainText(index.data(Qt.ItemDataRole.EditRole) or '')
        editor.blockSignals(False)

    def setModelData(self, editor, model, index):
        # The captured ID survives sorting or selection changes during editing.
        self.changed.emit(editor.property('job_id'), editor.toPlainText())
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)


class NameDelegate(NoteDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setProperty('job_id', index.data(Qt.ItemDataRole.UserRole))
        editor.textChanged.connect(lambda text: self.changed.emit(editor.property('job_id'), text))
        editor.destroyed.connect(lambda: self.closed.emit())
        self.opened.emit(editor)
        return editor

    def setEditorData(self, editor, index):
        editor.blockSignals(True)
        editor.setText(index.data(Qt.ItemDataRole.UserRole + 2) or '')
        editor.blockSignals(False)

    def setModelData(self, editor, model, index):
        self.changed.emit(editor.property('job_id'), editor.text())
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


class JobItem(QTableWidgetItem):
    def __init__(self, text: str, job_id: str, sort_value) -> None:
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, job_id)
        self.sort_value = sort_value

    def __lt__(self, other) -> bool:
        if isinstance(other, JobItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


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
        self._pending_notes: dict[str, str] = {}
        self._pending_names: dict[str, str] = {}
        self._note_job_id: str | None = None
        self._table_editor = None
        self.note_timer = QTimer(self)
        self.note_timer.setSingleShot(True)
        self.note_timer.setInterval(400)
        self.note_timer.timeout.connect(self._flush_notes)
        self._lock_icons = {locked: lock_icon(locked) for locked in (False, True)}
        self.setWindowTitle(f"AgentRunner {DISPLAY_VERSION}")
        self.setWindowIcon(application_icon())
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
        self._timing_jobs = {}
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self._refresh_elapsed)
        self.elapsed_timer.start(1000)
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
        self.help_button = QPushButton()
        self.help_button.clicked.connect(lambda: QMessageBox.information(self, self.tr('help'), HELP[self.language]))
        top.addWidget(self.language_label)
        top.addWidget(self.language_combo)
        top.addSpacing(20)
        top.addWidget(self.close_checkbox)
        top.addStretch()
        top.addWidget(self.help_button)
        top.addWidget(self.refresh_button)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.jobs_table = QTableWidget(0, 6)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed | QTableWidget.EditTrigger.AnyKeyPressed)
        self.jobs_table.itemSelectionChanged.connect(self._job_selected)
        self.jobs_table.cellClicked.connect(self._lock_clicked)
        self.note_delegate = NoteDelegate(self.jobs_table)
        self.note_delegate.opened.connect(self._note_editor_opened)
        self.note_delegate.changed.connect(self._queue_note)
        self.note_delegate.closed.connect(self._note_editor_closed)
        self.jobs_table.setItemDelegateForColumn(4, self.note_delegate)
        self.name_delegate = NameDelegate(self.jobs_table)
        self.name_delegate.opened.connect(self._note_editor_opened)
        self.name_delegate.changed.connect(self._queue_name)
        self.name_delegate.closed.connect(self._note_editor_closed)
        self.jobs_table.setItemDelegateForColumn(0, self.name_delegate)
        header = self.jobs_table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setStretchLastSection(True)
        self.jobs_table.setSortingEnabled(True)
        self.jobs_table.sortItems(2, Qt.SortOrder.DescendingOrder)
        saved_header = self.settings.value('jobs_header_v4')
        if saved_header is not None:
            header.restoreState(saved_header)
        else:
            old_six_header = self.settings.value('jobs_header_v3')
            old_header = self.settings.value('jobs_header_v2') or self.settings.value('jobs_header_v1')
            for column, width in enumerate((130, 78, 120, 36, 110, 100)):
                self.jobs_table.setColumnWidth(column, width)
            if old_six_header is not None:
                header.restoreState(old_six_header)
            elif old_header is not None:
                # Decode the five-column state separately: restoring it directly
                # into six sections can corrupt Qt's saved visual mapping.
                old_table = QTableWidget(0, 5)
                old = old_table.horizontalHeader()
                if old.restoreState(old_header):
                    for visual in range(5):
                        logical = old.logicalIndex(visual)
                        header.moveSection(header.visualIndex(logical), visual)
                        header.resizeSection(logical, old.sectionSize(logical))
                    header.setSortIndicator(old.sortIndicatorSection(), old.sortIndicatorOrder())
            else:
                header.moveSection(header.visualIndex(3), 0)
            if old_six_header is None:
                header.moveSection(header.visualIndex(5), header.visualIndex(4))
            for column, minimum in ((0, 160), (2, 170), (5, 130)):
                header.resizeSection(column, max(header.sectionSize(column), minimum))
        header.sectionMoved.connect(self._save_columns)
        header.sortIndicatorChanged.connect(self._save_columns)
        left_layout.addWidget(self.jobs_table)
        history_actions = QHBoxLayout()
        self.clean_button = QPushButton()
        self.clean_button.clicked.connect(self._clean_history)
        history_actions.addWidget(self.clean_button)
        left_layout.addLayout(history_actions)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.title_label = QLineEdit()
        self.title_label.textChanged.connect(self._detail_name_changed)
        self.title_label.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        self.job_id_label = QLabel()
        self.job_id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_label = QLabel()
        self.elapsed_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.progress = QProgressBar()
        right_layout.addWidget(self.title_label)
        right_layout.addWidget(self.job_id_label)
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(self.elapsed_label)
        self.note_input = QPlainTextEdit()
        self.note_input.setMaximumHeight(64)
        self.note_input.textChanged.connect(self._detail_note_changed)
        right_layout.addWidget(self.note_input)
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
        splitter.setSizes([520, 600])
        layout.addWidget(splitter)
        self.setCentralWidget(root)

    def _translate(self) -> None:
        self.language_label.setText(self.tr("language"))
        self.close_checkbox.setText(self.tr("close_to_tray"))
        self.refresh_button.setText(self.tr("refresh"))
        self.help_button.setText(self.tr('help'))
        self.clean_button.setText(self.tr('clean'))
        self.jobs_table.setHorizontalHeaderLabels([self.tr(key) for key in ('name', 'status', 'created', 'locked', 'note', 'elapsed')])
        self.jobs_table.horizontalHeaderItem(3).setText('L')
        self.jobs_table.horizontalHeaderItem(3).setToolTip(self.tr('lock'))
        self.note_input.setPlaceholderText(self.tr('note'))
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
        self.title_label.setPlaceholderText(self.tr("name"))
        if hasattr(self, "tray"):
            self.tray_open.setText(self.tr("open"))
            self.tray_exit.setText(self.tr("exit"))

    def _change_language(self) -> None:
        self.language = self.language_combo.currentData()
        self.settings.setValue("language", self.language)
        self._translate()
        self.refresh()

    def _save_columns(self, *args) -> None:
        self.settings.setValue('jobs_header_v4', self.jobs_table.horizontalHeader().saveState())

    def _lock_clicked(self, row: int, column: int) -> None:
        if column != 3:
            return
        job = store.get_job(self.jobs_table.item(row, column).data(Qt.ItemDataRole.UserRole))
        if job and not history.update(job['id'], locked=not bool(job['user_locked'])):
            self.statusBar().showMessage(self.tr('metadata_error'))
        self.refresh()

    def _note_editor_opened(self, editor) -> None:
        self._table_editor = editor

    def _note_editor_closed(self) -> None:
        self._table_editor = None
        self._flush_notes()
        QTimer.singleShot(0, self.refresh)

    def _queue_name(self, job_id: str, name: str) -> None:
        self._pending_names[job_id] = name
        self.note_timer.start()

    def _detail_name_changed(self, name: str) -> None:
        if self._note_job_id:
            self._queue_name(self._note_job_id, name)

    def _queue_note(self, job_id: str, note: str) -> None:
        self._pending_notes[job_id] = note
        self.note_timer.start()

    def _detail_note_changed(self) -> None:
        if self._note_job_id:
            self._queue_note(self._note_job_id, self.note_input.toPlainText())

    def _flush_notes(self) -> None:
        self.note_timer.stop()
        for job_id in set(self._pending_notes) | set(self._pending_names):
            changes = {}
            if job_id in self._pending_notes:
                changes['note'] = self._pending_notes[job_id]
            if job_id in self._pending_names:
                changes['name'] = self._pending_names[job_id]
            try:
                if history.update(job_id, **changes):
                    self._pending_notes.pop(job_id, None)
                    self._pending_names.pop(job_id, None)
                else:
                    self.statusBar().showMessage(self.tr('metadata_error'))
            except Exception as exc:
                self.statusBar().showMessage(str(exc))

    def _clean_history(self) -> None:
        self._flush_notes()
        if self._pending_notes or self._pending_names:
            QMessageBox.warning(self, self.tr('note'), self.tr('note_save_failed'))
            return
        if self.ask_worker is not None:
            QMessageBox.information(self, self.tr('clean'), self.tr('ask_busy'))
            return
        if QMessageBox.question(self, self.tr('clean'), self.tr('clean_confirm')) != QMessageBox.StandardButton.Yes:
            return
        try:
            result = history.clean()
            self.refresh()
            self.statusBar().showMessage(self.tr('clean_result').format(count=len(result['removed'])))
            if result['errors']:
                QMessageBox.warning(self, self.tr('clean'), self.tr('clean_error').format(errors='\n'.join(result['errors'])))
        except Exception as exc:
            QMessageBox.warning(self, self.tr('clean'), str(exc))

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
        self._flush_notes()
        if self._pending_notes or self._pending_names:
            QMessageBox.warning(self, self.tr('note'), self.tr('note_save_failed'))
            return
        if self.ask_worker is not None:
            QMessageBox.information(self, self.tr("exit"), self.tr("ask_busy"))
            return
        jobs = store.list_jobs()
        self._timing_jobs = {job["id"]: job for job in jobs}
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
        self._flush_notes()
        if self._pending_notes or self._pending_names:
            QMessageBox.warning(self, self.tr('note'), self.tr('note_save_failed'))
            event.ignore()
            return
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

    def _task_name(self, job: dict) -> str:
        return self._pending_names.get(job.get('id'), job.get('name')) or self.tr('workflow_task' if job.get('kind') == 'workflow' else 'command_task')

    def _set_elapsed_detail(self, job: dict, now: datetime | None = None) -> None:
        key = 'total_elapsed' if job['status'] in {'COMPLETED', 'FAILED', 'CANCELLED'} else 'elapsed'
        self.elapsed_label.setText(f"{self.tr(key)}: {duration_text(elapsed_seconds(job, now), self.language)}")

    def _refresh_elapsed(self) -> None:
        now = datetime.now(timezone.utc)
        table = self.jobs_table
        blocked = table.blockSignals(True)
        sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        for row in range(table.rowCount()):
            item = table.item(row, 5)
            if item is None:
                continue
            job = self._timing_jobs.get(item.data(Qt.ItemDataRole.UserRole))
            if job:
                seconds = elapsed_seconds(job, now)
                item.sort_value = seconds if seconds is not None else -1
                item.setText(duration_text(seconds, self.language))
        # Defer reordering until the inline note editor has closed.
        table.setSortingEnabled(sorting and self._table_editor is None)
        table.blockSignals(blocked)
        job = self._timing_jobs.get(self.selected_id)
        if job:
            self._set_elapsed_detail(job, now)

    def refresh(self) -> None:
        try:
            jobs = store.list_jobs()
            self._timing_jobs = {job["id"]: job for job in jobs}
            if self.selected_id not in {job['id'] for job in jobs}:
                self.selected_id = None
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
            if self._table_editor is not None:
                self._refresh_elapsed()
                # Rebuilding a table destroys its live editor and unsaved text.
                if self.selected_id:
                    self._show_detail()
                return
            self.jobs_table.blockSignals(True)
            self.jobs_table.setSortingEnabled(False)
            self.jobs_table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                values = (self._task_name(job), self.status_text(job['status']),
                          local_date_text(job['created_at']), '', self._pending_notes.get(job['id'], job['note']), duration_text(elapsed_seconds(job), self.language))
                sort_values = (values[0].casefold(), values[1], datetime.fromisoformat(job['created_at']).timestamp(),
                               job['user_locked'], values[4].casefold(), elapsed_seconds(job) if elapsed_seconds(job) is not None else -1)
                for col, value in enumerate(values):
                    item = JobItem(str(value), job['id'], sort_values[col])
                    if col not in (0, 4):
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole + 2, self._pending_names.get(job['id'], job.get('name')))
                        item.setToolTip(f"{value}\n{job['id']}")
                    if col == 2:
                        item.setToolTip(self.tr('local_time'))
                    if col == 3:
                        item.setIcon(self._lock_icons[bool(job['user_locked'])])
                        item.setToolTip(self.tr('locked_tip' if job['user_locked'] else 'unlocked_tip'))
                    if col == 4:
                        item.setToolTip(str(value))
                    self.jobs_table.setItem(row, col, item)
            self.jobs_table.setSortingEnabled(True)
            for row in range(self.jobs_table.rowCount()):
                if self.jobs_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.selected_id:
                    self.jobs_table.selectRow(row)
            self.jobs_table.blockSignals(False)
            if self.selected_id:
                self._show_detail()
            elif not jobs:
                self.title_label.blockSignals(True)
                self.title_label.clear()
                self.title_label.blockSignals(False)
                self.title_label.setEnabled(False)
                self.title_label.setToolTip('')
                self.job_id_label.clear()
                self.status_label.clear()
                self.elapsed_label.clear()
                self.error_label.clear()
                self._note_job_id = None
                self.note_input.blockSignals(True)
                self.note_input.clear()
                self.note_input.blockSignals(False)
                self.note_input.setEnabled(False)
                self.steps_table.setRowCount(0)
                for text in (self.output_text, self.events_text, self.artifacts_text, self.ask_info_label):
                    text.clear()
                self.progress.setRange(0, 1)
                self.progress.setValue(0)
                for button in (self.cancel_button, self.pause_button, self.continue_button, self.stop_button, self.folder_button, self.ask_button):
                    button.setEnabled(False)
                self.statusBar().showMessage(self.tr("no_data"))
        except Exception as exc:
            self.statusBar().showMessage(f"{type(exc).__name__}: {exc}")

    def _notify(self, job: dict, attention: bool = False) -> None:
        if not self.tray.isVisible() or not QSystemTrayIcon.supportsMessages():
            return
        key = "attention" if attention else {"COMPLETED": "completed", "FAILED": "failed", "CANCELLED": "cancelled"}[job["status"]]
        icon = QSystemTrayIcon.MessageIcon.Information if job["status"] == "COMPLETED" and not attention else QSystemTrayIcon.MessageIcon.Warning
        self.tray.showMessage(self.tr(key), self._task_name(job), icon, 8000)

    def _job_selected(self) -> None:
        self._flush_notes()
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
        name = self._pending_names.get(job['id'], job.get('name')) or ''
        if self._note_job_id != job['id'] or (not self.title_label.hasFocus() and self.title_label.text() != name):
            self.title_label.blockSignals(True)
            self.title_label.setText(name)
            self.title_label.blockSignals(False)
        self.title_label.setEnabled(True)
        self.title_label.setPlaceholderText(self.tr('workflow_task' if job['kind'] == 'workflow' else 'command_task'))
        self.title_label.setToolTip(self.selected_id)
        self.job_id_label.setText(f"{self.tr('job_id')}: {self.selected_id}")
        note = self._pending_notes.get(job['id'], job['note'])
        if self._note_job_id != job['id'] or (not self.note_input.hasFocus() and self.note_input.toPlainText() != note):
            self.note_input.blockSignals(True)
            self.note_input.setPlainText(note)
            self.note_input.blockSignals(False)
        self._note_job_id = job['id']
        self.note_input.setEnabled(True)
        control_state = (self.tr("stopping") if job["stop_after_current_requested"] else
                         self.tr("paused") if job["pause_requested"] else "")
        if job["callback_status"] == "UNKNOWN":
            control_state = f"{control_state} {self.tr('attention')}".strip()
        self._set_elapsed_detail(job)
        self.status_label.setText(f"{self.tr('status')}: {self.status_text(job['status'])} {control_state}".strip())
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
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('TaoMei.AgentRunner')
        app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setWindowIcon(application_icon())
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
