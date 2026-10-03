"""History cleanup must preserve execution, callbacks and user locks."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from agentrunner import history, store


def seed(number, status='COMPLETED', callback=False):
    job_id = f'JOB-{number:012x}'
    store.create_job({'id': job_id, 'command': ['cmd.exe', '/c', 'echo hello'],
                      'cwd': str(Path.cwd()), 'event_id': f'EVT-{number:016x}',
                      'callback_thread': 'test-chat' if callback else None})
    with store.connect() as con:
        con.execute('UPDATE jobs SET status=?, callback_status=? WHERE id=?',
                    (status, 'SENT' if callback else 'NOT_REQUESTED', job_id))
    (store.job_dir(job_id) / 'stdout.log').write_text('hello')
    return job_id


def handled(job_id):
    job = store.get_job(job_id)
    with store.connect() as con:
        con.execute("INSERT INTO callback_receipts (job_id,event_id,state,claim_token,claimed_at,claims) "
                    "VALUES (?,?,'HANDLED','token',?,1)", (job_id, job['event_id'], store.utc_now()))


def main():
    root = Path(__file__).parent / '.probe-state'
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='history-') as temporary:
        with patch.dict(os.environ, {'AGENTRUNNER_HOME': temporary}):
            done = seed(1)
            locked = seed(2)
            running = seed(3, 'RUNNING')
            unhandled = seed(4, callback=True)
            paused = seed(5, callback=True)
            released = seed(6, callback=True)
            failed = seed(7, 'FAILED')
            leased = seed(8, 'CANCELLED')
            handled(paused)
            handled(released)
            with store.connect() as con:
                for job_id, state in ((paused, 'PAUSED'), (released, 'RELEASED')):
                    job = store.get_job(job_id)
                    con.execute('INSERT INTO goal_handoffs (job_id,event_id,thread_id,state) VALUES (?,?,?,?)',
                                (job_id, job['event_id'], job_id, state))
                con.execute('INSERT INTO resource_leases VALUES (?,?,?,?)', ('example', 0, leased, 'work'))
            assert history.update(locked, locked=True, note='保留结果')
            assert store.get_job(locked)['note'] == '保留结果'
            # A cleanup failure must be visible and safely retryable.
            with patch('agentrunner.history.shutil.rmtree', side_effect=PermissionError('busy')):
                result = history.clean()
            assert set(result['removed']) == {done, released, failed}, result
            assert len(result['errors']) == 3, result
            assert {j['id'] for j in store.list_jobs()} == {locked, running, unhandled, paused, leased}
            assert store.job_dir(released).exists()
            assert not history.update(released, note='cannot resurrect')
            assert history.clean() == {'removed': [], 'errors': []}
            assert not store.job_dir(released).exists()
            job = store.get_job(released)
            assert store.claim_callback_event(released, job['event_id'], 'COMPLETED', 'test-chat')['result'] == 'duplicate'
            assert store.list_events(released) == []
            assert store.get_job(locked)['user_locked'] == 1
            assert history.update(locked, locked=False)
            assert history.clean()['removed'] == [locked]
    print('History: locks, pending callbacks, goal recovery, leases, notes, retry and deduplication passed')


if __name__ == '__main__':
    main()
