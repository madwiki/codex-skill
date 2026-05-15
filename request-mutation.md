# request-mutation

Use this in **Codex-mutates** mode after Claude and Codex have reached consensus on exactly one small state-changing step.

Codex owns mutation for this step. Codex should perform only the approved step, self-check, report evidence, and stop for Claude review.

## When to use

- Codex prepared a plan and Claude agreed on the next small step
- A prior Codex step needs one approved repair step
- The task should proceed incrementally with Claude review between steps

## Collaboration rules

- Reload `codex-skill` first after compaction or context reset.
- State clearly that the current mode is Codex-mutates and name the single approved step.
- Include stopping conditions and anything Codex must not touch.
- Codex must not continue into the next feature/stage after finishing the approved step.
- Codex must not commit, push, release, deploy, or perform external-state actions unless this exact call explicitly authorizes that action.
- After Codex responds, Claude reviews independently by reading/searching/verifying before approving the next step.

## Message template

```text
## Background
<Durable project/task context Codex needs.>

## Current turn context
- What Claude told the user:
- What the user said since the last Codex call, if anything:
- Why the user said it / surrounding situation:
- What Claude and Codex agreed:
- Current state:

## Optional fresh user message
<<<USER_MESSAGE_VERBATIM_BEGIN>>>
<copy/paste the user's exact words only when fresh user text exists>
<<<USER_MESSAGE_VERBATIM_END>>>

## Mutation ownership
Mode: Codex-mutates.
Codex may mutate only the approved step below.

## Approved mutation step
- Step:
- Scope:
- Files/modules likely involved:
- Do not touch:
- Required self-check:
- Stop condition:

## Claude message to Codex
- Execute only this step:
- Report changed files/state:
- Report evidence, tests, and self-review:
- Stop and wait for Claude review:
```

If there is no fresh user message, remove the entire `Optional fresh user message` section.

## Run

```bash
<skill_root>/bin/codex-skill-request-mutation < message.txt
```
