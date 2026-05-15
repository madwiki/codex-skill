# request-plan

Use this in **Codex-mutates** mode when Claude wants Codex to prepare the implementation plan.

Codex will own future mutation, but this call is planning only. Codex may do read-only investigation and must not edit files or change project/external state in this call.

## When to use

- Claude wants Codex to perform the implementation work
- The agents have discussed the goal enough to ask Codex for a concrete plan
- Claude needs the first small Codex mutation step to review before work begins

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload rule, and add it if missing.
- If this call follows compaction or context reset, use `chat.md` for post-compact recovery sync before requesting a plan.
- State clearly that the current mode is Codex-mutates, planning phase.
- Ask Codex to inspect relevant code before proposing risky steps.
- Codex should propose a plan plus the first small mutation step, then wait.
- If Claude disagrees with the plan, use `chat.md`. Do not approve mutation until consensus or user escalation.

## Message template

```text
## Background
<Durable project/task context Codex needs.>

## Current turn context
- What Claude told the user:
- What the user said since the last Codex call, if anything:
- Why the user said it / surrounding situation:
- What Claude did or learned:
- Current state:

## Optional fresh user message
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words only when fresh user text exists>
<<<USER_MESSAGE_VERBATIM_END>>>

## Mutation ownership
Mode: Codex-mutates, planning phase.
Codex may read/search/inspect but must not mutate state in this call.

## Requirements and constraints
- User goal:
- Hard constraints:
- Non-goals:
- Known risks:

## Claude message to Codex
- Please prepare the implementation plan:
- Code areas worth inspecting:
- Where I want pushback:
- What counts as the first small mutation step:
- Minimum user decision if consensus cannot be reached:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-request-plan < message.txt
```
