# review-your-work

Use this in **Codex-mutates** mode when Claude has reviewed Codex's prior mutation step and wants Codex to respond to the review.

This call is for review discussion, not mutation. Codex should answer with evidence, agreements/disagreements, and the smallest next repair or continuation step if needed. Use `request-mutation.md` for the next approved state-changing step.

## When to use

- Claude reviewed Codex's changed files and found issues, risks, or questions
- Claude wants Codex to explain why a change is safe
- Claude wants Codex to compare evidence before deciding whether to approve the next step
- A disagreement needs discussion before another mutation

## Collaboration rules

- Reload `codex-skill` first after compaction or context reset.
- State clearly that the current mode is Codex-mutates, review/discussion phase.
- Include Claude's independent review evidence, not only impressions.
- Codex should not mutate state in this call.
- If a repair is needed, Codex proposes the next small mutation step for Claude to approve.
- If disagreement remains or both agents are unsure, Claude asks the user to decide.

## Message template

```text
## Background
<Durable project/task context Codex needs.>

## Current turn context
- What Claude told the user:
- What the user said since the last Codex call, if anything:
- Why the user said it / surrounding situation:
- What Codex changed previously:
- What Claude inspected:
- Current state:

## Optional fresh user message
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words only when fresh user text exists>
<<<USER_MESSAGE_VERBATIM_END>>>

## Mutation ownership
Mode: Codex-mutates, review/discussion phase.
Codex must not mutate state in this call.

## Claude review findings
- Confirmed correct:
- Concerns / suspected issues:
- Evidence:
- Questions:

## Claude message to Codex
- Respond to this review:
- Explain agreements/disagreements with evidence:
- Propose the smallest next repair or continuation step if needed:
- Say whether user escalation is needed:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-review-your-work < message.txt
```
