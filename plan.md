# plan

Use before you publish any plan/design/architecture (including before ExitPlanMode). This is a specialized chat where Codex reviews your intended plan in the context of the ongoing collaboration thread.

Codex should help detect missing requirements, misunderstanding risks, unsafe assumptions, and the minimum clarifying questions plus acceptance checklist.

## Collaboration rules

- Treat this as a continuation of the same Codex collaboration session, not an isolated plan review.
- Explain what happened since the last Codex reply before presenting the plan.
- Include a verbatim user message only if the user actually said something new since the last Codex call.
- If there is no new user message, omit the verbatim user block entirely.
- Do not publish the plan to the user until you have considered Codex's blockers and minimum questions.
- Treat Codex's review as collaboration, not approval. Resolve disagreements by discussing evidence and assumptions before presenting the plan.
- If you and Codex cannot reach consensus, ask the user to choose between the smallest useful set of options before moving forward.

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

## Requirements interpretation
- My interpretation:
- Assumptions:
- Non-goals:

## Proposed plan
<your draft plan>

## Agent message to Codex
- Review focus:
- Specific concerns:
- Where I agree/disagree with Codex so far:
- If user input is required, list the minimum questions for the user:
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
<skill_root>/bin/codex-skill-plan < message.txt
```

`<skill_root>` is typically `~/.claude/skills/codex-skill`.

The command may take a long time. Wait for Codex to finish unless the process clearly fails.
