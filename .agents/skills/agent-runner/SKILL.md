---
name: agent-runner
description: Hand a deterministic local command or workflow to AgentRunner when execution involves substantial waiting, and stop the Codex turn after Runner accepts ownership.
---

# AgentRunner local handoff

Use this skill for a local machine task whose commands and completion criteria can be prepared before execution. Keep research, design, interpretation, and decisions with Codex. A short command can run directly; an obviously long command uses `python -m agentrunner run`; uncertain duration uses `python -m agentrunner exec --adaptive`; a dependent or parallel DAG uses `python -m agentrunner submit workflow.yaml`.

Before submission, establish the command or Workflow, working directory, success and failure criteria, expected artifacts, required resources, observation points, timeout and cleanup/finalizers where relevant. Check inputs and executable paths. Do not submit paid remote work or an irreversible external action without the authorization that action itself requires. Pass only required environment names with `--pass-env` or the Workflow field; do not put secrets into the Workflow, command arguments, or callback text.

For a callback to the current Codex chat, provide its actual thread UUID with `--callback-thread`. If the thread UUID is unavailable, say that callback delivery is not configured for this Job; do not guess an ID. The local Service must be running for automatic retries of failed callback delivery. The callback Skill checks local Job identity and uses atomic claim/ack to suppress repeated follow-up; callback delivery and user-facing replies are still not exactly once.

Read the single submission response. On `ACCEPTED` or `PROMOTED_TO_BACKGROUND`, report the Job ID, handoff state, and how the user can inspect it, then end this turn. Do not start a status, log, file, process, SSH, or sleep-and-query loop. Runner owns mechanical execution; closing the UI or ending the Codex turn does not cancel it. On `COMPLETED`, use the returned exit status and perform only the remaining requested interpretation. On rejection or `UNKNOWN_SUBMISSION`, correct a clear validation error or inspect the identified Job once before deciding whether a new submission is safe; never blindly submit the same side-effecting task again.

After handoff, respond to a callback or a user-requested one-time diagnosis. A user query does not transfer Job ownership to Codex. For a Workflow whose supervisor is lost, use `reconcile` and the documented `UNKNOWN` resolution commands; never infer a step's outcome from missing output or retry an unconfirmed side effect.

See the project's [runtime README](../../../agentrunner/README.md) for supported commands and recovery limits.
