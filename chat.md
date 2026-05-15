# chat

Use this as the shared collaboration mode. It is the normal way for Claude to brief Codex, preserve context, discuss uncertainty, resolve disagreement, prepare user questions, or decide which mutation-owner workflow to use next.

If Codex prepared a plan and Claude disagrees, use `chat`. Do not move to mutation until the disagreement is resolved or the user decides.

## When to use

- Routine progress sync that would otherwise be told only to the user
- Requirements discussion or understanding checks
- Choosing between Claude-mutates and Codex-mutates mode
- Mid-task changes, new constraints, or user changes of direction
- Disagreements between Claude and Codex
- Stuck, unclear, unresolved, risky, or confusing states
- Preparing the smallest user-facing decision when consensus is not reachable

## Collaboration rules

- Treat each message as a continuation of the same Codex collaboration session.
- Reload `codex-skill` first after compaction or context reset.
- Include what happened since the last Codex reply, including what Claude told the user when it affects the current state.
- Include a verbatim user message only if the user actually said something new since the last Codex call.
- If there is no new user message, omit the verbatim user block entirely.
- Do not fabricate, summarize-as-verbatim, or reuse stale user text to satisfy a template.
- Treat Codex as a peer collaborator, not an authority. Codex can be wrong; Claude can be wrong.
- Use read-only investigation and concrete evidence to test both agents' claims.
- Chat is not the normal place for state-changing work. Prefer the dedicated mutation-owner entrypoint once consensus exists.

## Message template

```text
## Background
<Durable project/task context Codex needs. First call may be larger; later calls should include only changes.>

## Current turn context
- What Claude told the user:
- What the user said since the last Codex call, if anything:
- Why the user said it / surrounding situation:
- What Claude did or learned:
- What changed in requirements, constraints, or risks:
- Current state:

## Optional fresh user message
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words only when fresh user text exists>
<<<USER_MESSAGE_VERBATIM_END>>>

## Claude message to Codex
- My current view:
- What I need from Codex:
- Where I want pushback:
- Where I agree/disagree with Codex so far:
- Proposed next mode or next step:

## User decision, if needed
- Minimum questions Claude should ask the user:
- Options, risks, and recommendation:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-chat < message.txt
```

`<skill_root>` is typically `~/.claude/skills/codex-skill`.

The command may take a long time. Wait for Codex to finish unless the process clearly fails.
