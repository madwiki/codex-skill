---
name: codex-skill
description: >
  [AUTO-TRIGGER] Use /codex-skill when Claude Code should collaborate with a persistent Codex session instead of working alone.
  Always reload this skill after compaction or context reset. Use chat for normal context sync, disagreements, consensus-building,
  and user-facing decision preparation. Choose Claude-mutates or Codex-mutates mode when any state-changing work is needed.
---

# codex-skill

This skill is for Claude Code. Claude invokes Codex as a persistent peer collaborator so both agents can work toward the user's goal, challenge each other's assumptions, and avoid solo-agent blind spots.

Codex is invoked by Claude; Codex does not speak to the user directly. Claude remains responsible for user-facing conversation and for asking the user to decide unresolved issues. This does not make Claude's judgment higher than Codex's judgment.

## Non-forgettable protocol

After every compaction, context reset, model restart, or memory recovery, the first collaboration action is to reload this `codex-skill` before planning, mutating, reviewing, or declaring completion.

Keep a durable reminder in project memory or `CLAUDE.md` when possible: after compact, reload `codex-skill`. If this protocol is lost, Claude may accidentally continue as a solo implementer, which violates the collaboration model.

## Core model

Claude and Codex are peers in judgment. The modes below define only **mutation ownership**: which agent is allowed to perform state-changing work in the workspace or external systems.

State-changing work includes file edits, generated artifacts, write-formatters, dependency changes, migrations, commands that update snapshots/caches/databases/services, commits, pushes, releases, deploys, and any command that changes external state.

Both agents may do read-only investigation in any mode: read files, search the repository, inspect diffs, inspect docs, reason about tests, and verify claims. If a command might write or affect shared state, it belongs to the mutation owner for the current mode.

## Consensus discipline

- Discuss before state-changing work until the plan and next step are clear enough that both agents can support it.
- Review rigorously. Each agent should look for requirement gaps, hallucinated assumptions, regressions, edge cases, and weak evidence. Pushback is for better information and a better result, not for winning.
- Do not blindly accept Codex, and do not silently ignore Codex. If you disagree, use `chat.md` to compare evidence, assumptions, tradeoffs, and user constraints.
- If Codex prepares a plan and Claude disagrees, use `chat.md`. Do not proceed to mutation until consensus is reached or the user decides.
- If consensus cannot be reached, or both agents are unsure, Claude asks the user. Present the smallest useful set of options, risks, and a recommendation when one is defensible.

## Choose the workflow

Use only one mutation owner for a task segment to avoid conflicting edits and process collisions.

| Situation | Guide |
| --- | --- |
| Normal sync, requirement changes, uncertainty, stuck states, disagreements, or consensus-building | `chat.md` |
| Claude will own state-changing work and wants Codex to review the plan before Claude mutates | `review-my-plan.md` |
| Claude owned state-changing work and wants Codex to review before delivery, commit, PR, merge, release, deploy, or "done" | `review-my-work.md` |
| Codex will own state-changing work and Claude wants Codex to prepare the plan | `request-plan.md` |
| Codex will own state-changing work and Claude has approved one small mutation step | `request-mutation.md` |
| Codex owned prior state-changing work and Claude wants Codex to respond to Claude's review | `review-your-work.md` |

Legacy aliases remain available for older habits:

- `plan.md` means `review-my-plan.md` (Claude-mutates).
- `review.md` means `review-my-work.md` (Claude-mutates).

## Codex-mutates loop

1. Use `chat.md` until the broad direction is understood.
2. Use `request-plan.md` for Codex to propose a plan and the first small mutation step.
3. If Claude disagrees with the plan, use `chat.md` to resolve the disagreement or prepare a user decision.
4. Once there is consensus, use `request-mutation.md` for exactly one approved step.
5. Claude reviews independently by reading/searching/verifying. Use `review-your-work.md` to send review findings to Codex.
6. Repeat small steps. Codex must stop after each step for Claude review.

## Claude-mutates loop

1. Use `chat.md` until the broad direction is understood.
2. Use `review-my-plan.md` before Claude performs meaningful state-changing work.
3. If Codex disagrees, use `chat.md` to resolve the disagreement or prepare a user decision.
4. Claude performs the agreed mutation step and self-checks.
5. Use `review-my-work.md` before final delivery or before any commit/PR/merge/release/deploy claim.

## Message continuity

Every Codex call should feel like the next message in the same collaboration thread:

- Background is durable task/project context. The first call may need more; later calls should include only new or changed background.
- Current turn context explains what happened since the last Codex reply: what Claude told the user, what the user said, what Claude did, what changed, and what Claude now believes.
- Include verbatim user text only when the user actually said something new since the last Codex call. If there is no fresh user message, omit the block entirely.
- When verbatim user text is included, explain why the user said it and what situation surrounded it.
- Claude's direct message to Codex contains Claude's view, request, concerns, disagreements, and requested pushback.

## Patience

Codex may inspect files, reason through a large context, compact/resume its own session, or run verification. Treat the command as a long-running collaboration turn, not a short RPC. The default timeout is intentionally broad.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/codex-skill`)
- Guides live directly under `<skill_root>`.
- Commands live under `<skill_root>/bin/`.
