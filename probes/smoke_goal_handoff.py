"""Exercise persistent pause ownership without changing a real Codex goal."""
import copy
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from agentrunner import cli, goal_handoff, goal_rpc, store

THREAD = "11111111-1111-1111-1111-111111111111"


class FakeGoal:
    def __init__(self):
        self.goal = {"threadId": THREAD, "objective": "keep original", "createdAt": 1,
                     "updatedAt": 1, "status": "active", "tokenBudget": 1000}
        self.writes = []

    def exchange(self, thread, status=None, expected=None):
        assert thread == THREAD
        if status:
            assert goal_rpc.matches(self.goal, expected)
            self.goal["status"] = status
            self.goal["updatedAt"] += 1
            self.writes.append(status)
        return copy.deepcopy(self.goal)


def job(name):
    store.create_job({"id": name, "event_id": "EVT-" + name, "command": ["unused"],
                      "cwd": str(store.home()), "callback_thread": THREAD})
    with store.connect() as con:
        con.execute("UPDATE jobs SET status='RUNNING' WHERE id=?", (name,))


def terminal_claim(name):
    with store.connect() as con:
        con.execute("UPDATE jobs SET status='COMPLETED',exit_code=0,callback_status='SENT' WHERE id=?", (name,))
    return store.claim_callback_event(name, "EVT-" + name, "COMPLETED", THREAD)["claim_token"]


def main():
    root = Path(__file__).resolve().parent / ".probe-state"
    root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix="goal-handoff-") as temporary:
        with patch.dict(os.environ, {"AGENTRUNNER_HOME": temporary}):
            fake = FakeGoal()
            with patch("agentrunner.goal_rpc.exchange", side_effect=fake.exchange):
                job("JOB-normal")
                assert goal_handoff.pause("JOB-normal")["status"] == "PAUSED"
                job("JOB-other")
                try:
                    goal_handoff.pause("JOB-other")
                except ValueError:
                    pass
                else:
                    raise AssertionError("Two Jobs claimed the same paused goal")
                token = terminal_claim("JOB-normal")
                assert goal_handoff.release("JOB-normal", "EVT-JOB-normal", token, THREAD)["status"] == "BLOCKED"
                terminal_claim("JOB-other")
                try:
                    goal_handoff.release("JOB-normal", "EVT-JOB-normal", "wrong", THREAD)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Wrong callback claim resumed a goal")
                assert fake.writes == ["paused"]
                with store.connect() as con:
                    con.execute("UPDATE goal_handoffs SET event_id='EVT-wrong' WHERE job_id='JOB-normal'")
                try:
                    goal_handoff.release("JOB-normal", "EVT-JOB-normal", token, THREAD)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Corrupt ownership event resumed a goal")
                assert fake.writes == ["paused"]
                with store.connect() as con:
                    con.execute("UPDATE goal_handoffs SET event_id='EVT-JOB-normal' WHERE job_id='JOB-normal'")
                assert goal_handoff.release("JOB-normal", "EVT-JOB-normal", token, THREAD)["status"] == "RELEASED"
                assert goal_handoff.release("JOB-normal", "EVT-JOB-normal", token, THREAD)["status"] == "RELEASED"
                assert fake.writes == ["paused", "active"]
                assert fake.goal["objective"] == "keep original" and fake.goal["tokenBudget"] == 1000
                assert store.acknowledge_callback_event("JOB-normal", "EVT-JOB-normal", token)
                assert store.claim_callback_event("JOB-normal", "EVT-JOB-normal", "COMPLETED", THREAD)["result"] == "duplicate"

                job("JOB-changed")
                assert goal_handoff.pause("JOB-changed")["status"] == "PAUSED"
                fake.goal["updatedAt"] += 1  # User action after this handoff.
                token = terminal_claim("JOB-changed")
                assert goal_handoff.release("JOB-changed", "EVT-JOB-changed", token, THREAD)["status"] == "CHANGED"
                assert fake.goal["status"] == "paused"
                job("JOB-user-paused")
                assert goal_handoff.pause("JOB-user-paused")["status"] == "NOT_ACTIVE"

            # Unconfirmed mutation must never be automatically replayed.
            fake.goal["status"] = "active"
            job("JOB-unconfirmed")
            def lose_response(thread, status=None, expected=None):
                result = fake.exchange(thread, status, expected)
                if status:
                    raise TimeoutError("Response lost after side effect")
                return result
            with patch("agentrunner.goal_rpc.exchange", side_effect=lose_response):
                assert goal_handoff.pause("JOB-unconfirmed")["status"] == "UNKNOWN"
            token = terminal_claim("JOB-unconfirmed")
            with patch("agentrunner.goal_rpc.exchange") as rpc:
                assert goal_handoff.release("JOB-unconfirmed", "EVT-JOB-unconfirmed", token, THREAD)["status"] == "UNKNOWN"
                rpc.assert_not_called()

            with patch("agentrunner.cli.submit") as submit:
                assert cli.main(["run", "--pause-goal", "--", "unused"]) == 2
                submit.assert_not_called()
            # Exercise the actual CLI branches with detached execution substituted.
            with patch("agentrunner.goal_rpc.exchange") as rpc:
                assert goal_handoff.dismiss("JOB-unconfirmed")["status"] == "ABANDONED"
                rpc.assert_not_called()
            terminal_claim("JOB-user-paused")
            fake.goal["status"] = "active"
            job("JOB-cli")
            with patch("agentrunner.goal_rpc.exchange", side_effect=fake.exchange), patch(
                "agentrunner.cli.submit", return_value=({"status": "ACCEPTED", "job_id": "JOB-cli"}, None)
            ), patch("agentrunner.cli.reveal_installed_runner"):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    assert cli.main(["run", "--pause-goal", "--callback-thread", THREAD, "--", "unused"]) == 0
                assert json.loads(output.getvalue())["goal_handoff"]["status"] == "PAUSED"
                token = terminal_claim("JOB-cli")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    assert cli.main(["goal-release", "JOB-cli", "EVT-JOB-cli", "--claim-token", token, "--thread-id", THREAD]) == 0
                assert json.loads(output.getvalue())["status"] == "RELEASED"
    print("Goal handoff: ownership, duplicate, concurrent Job, changed goal, lost response, CLI preflight passed")


if __name__ == "__main__":
    main()
