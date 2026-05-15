# review-my-work

Use this in **Claude-mutates** mode after Claude has performed state-changing work and before Claude says done or performs commit/PR/merge/release/deploy.

Claude owns mutation. Codex reviews Claude's work, may do read-only investigation, and must not edit files or change project/external state in this call.

## When to use

- Before claiming the task is complete
- Before commit, PR, merge, release, deploy, or other delivery step
- After a risky implementation step where an independent review is useful
- When Claude's self-check found uncertainty or weak evidence

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload rule, and add it if missing.
- If this call follows compaction or context reset, use `chat.md` for post-compact recovery sync before work review.
- State clearly that the current mode is Claude-mutates.
- Include enough evidence for Codex to review independently: changed files, test results, known risks, and unresolved assumptions.
- Ask Codex to read/search/inspect when needed and to look for holes rather than rubber-stamp the result.
- If Claude disagrees with Codex's findings, switch to `chat.md` and discuss evidence until consensus or user escalation.

## Message template

```text
## Background
<Durable project/task context Codex needs.>

## Current turn context
- What Claude told the user:
- What the user said since the last Codex call, if anything:
- Why the user said it / surrounding situation:
- What Claude changed:
- What Claude tested:
- Current state:

## Optional fresh user message
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words only when fresh user text exists>
<<<USER_MESSAGE_VERBATIM_END>>>

## Mutation ownership
Mode: Claude-mutates.
Codex may read/search/inspect but must not mutate state.

## Delivery summary
- Changed files:
- Behavioral change:
- Test evidence:
- Known risks:
- Rollback / recovery:

## Claude message to Codex
- Review focus:
- Where I want pushback:
- Where I agree/disagree with Codex so far:
- Minimum user decision if consensus cannot be reached:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-review-my-work < message.txt
```
