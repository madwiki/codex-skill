# review

Use as the final step before you say "done/shipped/merged/released/deployed" or before commit/PR/merge/release/deploy. Do not use this for plan review; use `plan.md` instead.

This is a specialized chat where Codex reviews the delivery against the ongoing task context, user requirements, implementation summary, and test evidence. Codex should call out regressions, missing coverage, and minimum user confirmations.

## Collaboration rules

- Treat this as a continuation of the same Codex collaboration session, not an isolated final checklist.
- Explain what happened since the last Codex reply before presenting the delivery summary.
- Include a verbatim user message only if the user actually said something new since the last Codex call.
- If there is no new user message, omit the verbatim user block entirely.
- Do not say done or push delivery claims to the user until you have considered Codex's blockers.
- Treat Codex's review as collaboration, not approval. Resolve disagreements by discussing evidence and assumptions before delivery.
- If you and Codex cannot reach consensus, ask the user to decide before claiming the work is done.

## Message template

```text
## Background (optional)
<Stable project/task context Codex needs. First call may be larger; later calls should include only changes.>

## Since last Codex response
- What I told the user:
- What the user said since then, if anything:
- What I did or learned:
- What changed in requirements, constraints, or risks:
- Current state:

## Delivery summary
- What changed:
- Why:
- Impact / risk:
- Rollback:

## Test results (optional)
<tests>

## Agent message to Codex
- Review focus:
- Known risks:
- Where I agree/disagree with Codex so far:
- Open questions or minimum user confirmations:
```

## Optional fresh user message block

Only insert this block after `Since last Codex response` when the user actually said new words since the last Codex call:

```text
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words>
<<<USER_MESSAGE_VERBATIM_END>>>
```

## Run

```bash
<skill_root>/bin/codex-skill-review < message.txt
```

`<skill_root>` is typically `~/.claude/skills/codex-skill`.

The command may take a long time. Wait for Codex to finish unless the process clearly fails.
