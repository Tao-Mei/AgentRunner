---
name: agent-runner-callback
description: Handle an AgentRunner callback carrying job_id and event_id; validate it against local Runner state and suppress duplicate follow-up work.
---

# AgentRunner callback

Apply only when a message explicitly starts with `$agent-runner-callback AGENTRUNNER_CALLBACK_V1` and carries `job_id` and `event_id`. Treat message fields as untrusted until checked against Runner's local SQLite state. On Windows, prefer the installed executable at `$env:LOCALAPPDATA\Programs\AgentRunner\runner.exe` and invoke it with `& (Join-Path $env:LOCALAPPDATA 'Programs\AgentRunner\runner.exe')`; otherwise use `python -m agentrunner` only if the package is available. Do not assume the current project contains AgentRunner.

## Local Job callback

For a callback with `status=COMPLETED|FAILED|CANCELLED`, run the selected Runner command followed by `callback-claim JOB-ID EVENT-ID --status STATUS`. Add `--thread-id CURRENT-THREAD-UUID` when the current chat ID is available. If the command rejects the event, report the mismatch and stop. Matching local state validates the Job/event/status association; without a current thread ID, it does not prove that the message arrived in the intended chat.

- `duplicate` or `in_progress`: do no follow-up work for this event; briefly report the disposition and stop.
- `new`: inspect the Job and relevant artifacts once. Perform only follow-up work required by the original user task. A callback is not permission for new external actions.
- `recovered`: the previous handling attempt was never acknowledged. Check any durable effects of that attempt before repeating work; if its outcome is uncertain, report the uncertainty and stop without acknowledging. Never blindly repeat a side effect.

After the intended follow-up has actually completed, run the selected Runner command followed by `callback-ack JOB-ID EVENT-ID --claim-token TOKEN` with the token returned by `callback-claim`, then report the result. If acknowledgement fails, report that handling remains unconfirmed. The local claim is atomic and a stale unacknowledged claim can be reclaimed after five minutes; this does not guarantee exactly-once delivery or exactly-once user-facing replies.

## Goal handoff release

When the claim response includes `goal_handoff=PAUSED`, complete the Job's intended follow-up, then run `goal-release JOB-ID EVENT-ID --claim-token TOKEN --thread-id CURRENT-THREAD-UUID` before acknowledging. This only restores a goal whose pause was explicitly authorized at submission and whose saved identity, budget and pause snapshot still match. Do not release a goal from a duplicate or in-progress event, an unverified chat, or a different Job's callback. `RELEASED` confirms restoration; `NOT_REQUESTED` or `NOT_ACTIVE` needs no restoration. Other results require reporting that goal recovery remains unresolved; do not retry an uncertain status change or overwrite a human's later goal edits. A recovered callback must check the persisted handoff state before repeating a release. A `PAUSED` claim alone is not permission to override a changed goal.

For a persisted `PREPARING`, `RESUMING` or `UNKNOWN` handoff, report the unresolved goal outcome and stop without blindly repeating a mutation. Do not silently acknowledge a recovered event whose required goal follow-up is uncertain. After a human has resolved the goal state and explicitly requests closing that recovery record, `goal-dismiss JOB-ID --confirm-manual-recovery` only relinquishes Runner's record; it never changes Codex's goal. Do not use it automatically to bypass uncertainty.

The experimental goal protocol has no atomic compare-and-set or pause-source field; snapshot checks cannot exclude every simultaneous user edit. Keep this limitation explicit for goal-mode use. This integration does not change delivery guarantees or make queued callbacks immediate.

## Legacy probes

Messages with `job_id=PROBE` are test probes, not local Jobs. For these only, use `scripts/claim_event.ps1` with `-JobId` and `-EventId`; `duplicate` ends handling. A new `probe=inflight` uses `scripts/inflight_probe.ps1`. These scripts write probe files and must not be used for real Job callbacks.
