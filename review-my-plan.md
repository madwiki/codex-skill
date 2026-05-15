# review-my-plan

Use this in **Claude-mutates** mode before Claude performs meaningful state-changing work.

Claude owns mutation. Codex reviews Claude's intended plan, may do read-only investigation, and must not edit files or change project/external state in this call.

## When to use

- Before Claude starts implementation after discussion
- Before publishing a plan/design/architecture to the user
- Before ExitPlanMode when Claude will execute the work
- After requirements change enough that the old plan may be stale

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload + recovery-sync + subtask-guide rule, and add it if missing.
- If this call follows compaction, context reset, model restart, or memory recovery, use `chat.md` for recovery sync before plan review.
- State clearly that the current mode is Claude-mutates.
- Ask Codex to check requirements, assumptions, affected code, risks, and tests.
- Ask Codex to personally fact-check important claims and review whole-system coherence, not only the draft plan.
- Treat Codex's response as peer review, not approval.
- If Claude disagrees with Codex's review, switch to `chat.md` and discuss evidence until consensus or user escalation.

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
Mode: Claude-mutates.
Codex may read/search/inspect but must not mutate state.

## Requirements interpretation
- My interpretation:
- Assumptions:
- Non-goals:

## Proposed plan
<Claude's draft plan>

## Claude message to Codex
- Review focus:
- Specific concerns:
- Facts I want independently checked:
- Whole-system coherence concerns:
- Where I want pushback:
- Where I agree/disagree with Codex so far:
- Minimum user decision if consensus cannot be reached:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-review-my-plan < message.txt
```
