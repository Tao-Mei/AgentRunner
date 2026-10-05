"""Exercise metadata through real CLI parsing and persistence, without workers."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
from agentrunner import cli, history, store


def main():
    root = Path(__file__).parent / '.probe-state'
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='metadata-') as temporary, patch.dict(os.environ, {'AGENTRUNNER_HOME': temporary}):
        def launch(job_id, event_id, module):
            store.transition(job_id, 'RUNNING', 'test_start', started_at=store.utc_now())
            worker = MagicMock()
            def finish(*args, **kwargs):
                if kwargs.get('timeout') == 0:
                    raise subprocess.TimeoutExpired('fixture', 0)
                store.transition(job_id, 'COMPLETED', 'test_end', finished_at=store.utc_now(), exit_code=0)
                return 0
            worker.wait.side_effect = finish
            return {'status': 'ACCEPTED', 'job_id': job_id, 'event_id': event_id}, worker
        def invoke(args):
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                code = cli.main(args)
            return code, json.loads(output.getvalue()) if output.getvalue() else {}
        with patch('agentrunner.cli.launch_worker', side_effect=launch), patch('agentrunner.cli.reveal_installed_runner'):
            for action, extras in [('run', []), ('exec', []), ('exec', ['--adaptive', '--grace-seconds', '0'])]:
                code, result = invoke([action, '--cwd', temporary, '--name', '  生成安装包  ', '--note', '来源项目：AgentRunner', *extras, '--', sys.executable, '-c', 'pass'])
                assert code == 0
                job = store.get_job(result['job_id'])
                assert job['name'] == '生成安装包' and job['note'] == '来源项目：AgentRunner'
                assert job['command'] == [sys.executable, '-c', 'pass']
                assert next(row for row in store.list_jobs() if row['id'] == job['id'])['name'] == job['name']
                history.update(job['id'], note='我的备注')
                assert store.get_job(job['id'])['note'] == '我的备注'
            code, result = invoke(['run', '--cwd', temporary, '--', sys.executable, '-c', 'pass'])
            assert code == 0 and store.get_job(result['job_id'])['name'] is None and store.get_job(result['job_id'])['note'] == ''
            workflow = Path(temporary) / 'workflow.yaml'
            workflow.write_text(yaml.safe_dump({'version': 1, 'job': {'name': '原始名称'}, 'steps': [{'id': 'test', 'command': [sys.executable, '-c', 'pass']}]}), encoding='utf-8')
            for extra, expected in [([], '原始名称'), (['--name', '处理视频', '--note', '来源项目：课程录制'], '处理视频')]:
                code, result = invoke(['submit', str(workflow), '--cwd', temporary, *extra])
                assert code == 0
                job = store.get_job(result['job_id'])
                assert job['name'] == expected
                assert job['note'] == ('来源项目：课程录制' if extra else '')
            count = len(store.list_jobs())
            code, result = invoke(['run', '--cwd', temporary, '--name', ' ', '--', sys.executable, '-c', 'pass'])
            assert code != 0 and len(store.list_jobs()) == count
    print('CLI metadata: named run/exec/adaptive/workflow, defaults, note editing and invalid input passed')

if __name__ == '__main__':
    main()
