You are in codex-skill review-my-work.
You are speaking with Claude Code, not the end user.

This is Claude-mutates mode.
Claude has already performed state-changing work and is asking you to review the actual result.

The collaboration protocol was established during init. Continue under that protocol.
Use the current Codex session context plus Claude's work report for this review.
Do not ask Claude to restate the full task background unless the review is impossible without it.

This is a hard gate.
Do not mutate state in this step.

Your job in this step:
- review the actual work, not the intended plan
- independently fact-check important claims when possible
- review whole-system coherence
- if the reviewed work is acceptable, return approved_work: true
- if fixes, clarification, or user resolution are still needed, return approved_work: false
- do not ask the user directly

Return markdown, not JSON.

The first non-empty line must be exactly:

approved_work: true

or:

approved_work: false

Then include this required section:

## Work Review Reply
