# chat

Use this as the default collaboration mode. It is the normal way for Claude Code to brief Codex, continue shared context, ask for judgment, or coordinate the next step.

## When to use

- Routine progress sync that you would otherwise summarize only to the user
- Requirements discussion or understanding checks
- Mid-implementation changes, new constraints, or user changes of direction
- Disagreements between your current view and Codex's prior advice
- Stuck, unclear, unresolved, risky, or confusing states

## Collaboration rules

- Treat each message as a continuation of the same Codex collaboration session.
- Always explain what happened since the last Codex reply.
- Include what you told the user if that affects the current state.
- Include a verbatim user message only if the user actually said something new since the last Codex call.
- If there is no new user message, omit the verbatim user block entirely.
- Do not fabricate, summarize-as-verbatim, or reuse stale user text just to satisfy the template.

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

## Agent message to Codex
- My current view:
- What I need from Codex:
- Where I want pushback:

## Questions
- My questions for Codex:
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
<skill_root>/bin/codex-skill-chat < message.txt
```

`<skill_root>` is typically `~/.claude/skills/codex-skill`.

The command may take a long time. Wait for Codex to finish unless the process clearly fails.
