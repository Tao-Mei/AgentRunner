"""Verify real Qt sorting and selection with isolated settings and task data."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import QAbstractItemDelegate, QApplication, QMessageBox
from PySide6.QtTest import QTest
from agentrunner import store
from agentrunner.desktop import RunnerWindow, application_icon, elapsed_seconds, duration_text
from datetime import datetime, timezone, timedelta


def main():
    root = Path(__file__).parent / '.probe-state'
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='desktop-history-') as temporary:
        settings = QSettings(str(Path(temporary) / 'settings.ini'), QSettings.Format.IniFormat)
        with patch.dict(os.environ, {'AGENTRUNNER_HOME': temporary}), patch('agentrunner.desktop.QSettings', return_value=settings):
            app = QApplication([])
            # Offscreen Qt has no native font provider; load the Windows font for the preview.
            font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
            if font_path.is_file():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    app.setFont(QFont(families[0], 10))
            assert not application_icon().isNull()
            ids = ['JOB-000000000001', 'JOB-000000000002']
            for job_id, name, date in zip(ids, ['Zulu', 'Alpha'], ['2026-09-30T01:00:00+00:00', '2026-09-29T23:30:00-04:00']):
                store.create_job({'id': job_id, 'command': ['cmd'], 'cwd': temporary, 'event_id': 'EVT-'+job_id})
                with store.connect() as con:
                    con.execute("UPDATE jobs SET name=?,created_at=?,status='COMPLETED' WHERE id=?", (name, date, job_id))
            start = '2026-10-04T00:00:00+00:00'
            end = '2026-10-04T01:02:03+00:00'
            for status in ('COMPLETED', 'FAILED', 'CANCELLED'):
                fixture = dict(status=status, started_at=start, finished_at=end)
                assert elapsed_seconds(fixture) == 3723
                assert duration_text(elapsed_seconds(fixture)) == '01:02:03'
            assert duration_text(90061) == '25:01:01'
            assert elapsed_seconds(dict(status='RUNNING', started_at='2026-10-04T08:00:00+08:00'), datetime.fromisoformat(end)) == 3723
            assert elapsed_seconds(dict(status='UNKNOWN', started_at=start)) is None
            assert elapsed_seconds(dict(status='COMPLETED', started_at=start, finished_at=None)) is None
            assert elapsed_seconds(dict(status='CREATED', started_at=None)) is None
            assert elapsed_seconds(dict(status='RUNNING', started_at='invalid')) is None
            assert elapsed_seconds(dict(status='RUNNING', started_at=end), datetime.fromisoformat(start)) == 0
            with store.connect() as con:
                con.execute("UPDATE jobs SET started_at=?,finished_at=? WHERE id=?", (start, end, ids[0]))
                con.execute("UPDATE jobs SET status='RUNNING',started_at=? WHERE id=?", (store.utc_now(), ids[1]))
            # Simulate existing five-column preferences before migration.
            from PySide6.QtWidgets import QTableWidget
            old_table = QTableWidget(0, 5)
            old_header = old_table.horizontalHeader()
            old_header.setSectionsMovable(True)
            old_header.moveSection(old_header.visualIndex(1), 0)
            settings.setValue('jobs_header_v2', old_header.saveState())
            window = RunnerWindow(ids[0])
            window.show()
            app.processEvents()
            assert window.jobs_table.horizontalHeader().visualIndex(1) == 0, 'Preserve old column order'
            assert window.jobs_table.item(0, 5) is not None
            assert window.elapsed_label.text().endswith('01:02:03')
            assert window.jobs_table.horizontalHeaderItem(3).text() == 'L'
            assert window.jobs_table.horizontalHeaderItem(3).toolTip() == window.tr('lock')
            assert not hasattr(window, 'note_button') and not hasattr(window, 'lock_button')
            window.jobs_table.sortItems(5, Qt.SortOrder.DescendingOrder)
            assert window.jobs_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == ids[0]
            fixed_text = window.elapsed_label.text()
            running_start = datetime.fromisoformat(store.get_job(ids[1])['started_at'])
            with patch('agentrunner.desktop.datetime') as clock:
                clock.fromisoformat.side_effect = datetime.fromisoformat
                clock.now.return_value = running_start + timedelta(seconds=10)
                window._refresh_elapsed()
                running_item = next(window.jobs_table.item(row, 5) for row in range(2)
                                    if window.jobs_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == ids[1])
                assert running_item.text() == '00:00:10'
                clock.now.return_value = running_start + timedelta(seconds=11)
                window._refresh_elapsed()
                assert running_item.text() == '00:00:11'
            assert window.elapsed_label.text() == fixed_text
            window.jobs_table.sortItems(0, Qt.SortOrder.AscendingOrder)
            window.refresh()
            assert window.jobs_table.item(0, 0).text() == 'Alpha'
            assert window.selected_id == ids[0] and window.title_label.text() == 'Zulu'
            window.jobs_table.sortItems(2, Qt.SortOrder.AscendingOrder)
            window.refresh()
            assert window.jobs_table.item(0, 0).data(Qt.ItemDataRole.UserRole) == ids[0], 'Dates must sort by instant, not text'
            header = window.jobs_table.horizontalHeader()
            header.moveSection(header.visualIndex(1), 0)
            def row_for(job_id):
                return next(row for row in range(window.jobs_table.rowCount())
                            if window.jobs_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == job_id)
            # Exercise the real inline editor while refresh and sort happen.
            window.jobs_table.editItem(window.jobs_table.item(row_for(ids[0]), 4))
            app.processEvents()
            editor = window._table_editor
            assert editor is not None
            QTest.keyClicks(editor, 'inline note')
            editor.insertPlainText('\n测试备注')
            window.refresh()
            assert window._table_editor is editor and editor.toPlainText() == 'inline note\n测试备注'
            window.jobs_table.sortItems(0, Qt.SortOrder.AscendingOrder)
            window.refresh()
            assert editor.toPlainText() == 'inline note\n测试备注'
            window._lock_clicked(row_for(ids[0]), 3)
            window._lock_clicked(row_for(ids[0]), 3)
            assert editor.toPlainText() == 'inline note\n测试备注'
            window._flush_notes()
            assert store.get_job(ids[0])['note'] == 'inline note\n测试备注'
            assert store.get_job(ids[1])['note'] == ''
            window.jobs_table.commitData(editor)
            window.jobs_table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            assert window._table_editor is None
            window.refresh()
            assert window.note_input.toPlainText() == 'inline note\n测试备注'
            # Right-hand draft survives automatic refresh and saves to the original ID on selection change.
            window.note_input.setFocus()
            window.note_input.setPlainText('右侧输入')
            QTest.qWait(450)
            assert store.get_job(ids[0])['note'] == '右侧输入', 'Debounced auto-save must run'
            window.refresh()
            assert window.note_input.toPlainText() == '右侧输入'
            window.jobs_table.selectRow(row_for(ids[1]))
            assert store.get_job(ids[0])['note'] == '右侧输入'
            assert window.note_input.toPlainText() == ''
            window.note_input.setPlainText('另一个任务')
            window.jobs_table.selectRow(row_for(ids[0]))
            assert store.get_job(ids[1])['note'] == '另一个任务'
            assert window.note_input.toPlainText() == '右侧输入'
            window._lock_clicked(row_for(ids[0]), 3)
            assert store.get_job(ids[0])['user_locked']
            assert not window.jobs_table.item(row_for(ids[0]), 3).icon().isNull()
            window.grab().save(str(root / 'inline-history-preview.png'))
            with patch('agentrunner.desktop.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                with store.connect() as con:
                    con.execute("UPDATE jobs SET status='COMPLETED',finished_at=? WHERE id=?", (store.utc_now(), ids[1]))
                window._clean_history()
            assert window.jobs_table.rowCount() == 1 and window.selected_id == ids[0]
            restored = RunnerWindow()
            assert restored.note_input.toPlainText() == '右侧输入'
            assert restored.jobs_table.horizontalHeader().visualIndex(1) == 0
            assert restored.jobs_table.horizontalHeader().sortIndicatorSection() == 0
            assert restored.tray.icon().cacheKey() == restored.windowIcon().cacheKey()
            window.note_input.setPlainText('closing draft')
            with patch('agentrunner.desktop.history.update', side_effect=OSError('save unavailable')), patch('agentrunner.desktop.QMessageBox.warning'):
                close_event = QCloseEvent()
                window.closeEvent(close_event)
                assert not close_event.isAccepted() and window._pending_notes
            window._flush_notes()
            assert store.get_job(ids[0])['note'] == 'closing draft'
            window._lock_clicked(row_for(ids[0]), 3)
            with patch('agentrunner.desktop.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                with store.connect() as con:
                    con.execute("UPDATE jobs SET status='COMPLETED',finished_at=? WHERE id=?", (store.utc_now(), ids[1]))
                window._clean_history()
            assert window.selected_id is None and window.jobs_table.rowCount() == 0
            assert not window.ask_button.isEnabled() and not window.folder_button.isEnabled()
            for item in (window, restored):
                item.timer.stop()
                item.show_timer.stop()
                item.note_timer.stop()
                item.tray.hide()
            app.quit()
    print('Desktop: icon, reorder persistence, chronological sorting, selection, lock, note and cleanup passed')


if __name__ == '__main__':
    main()
