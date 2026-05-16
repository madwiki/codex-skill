---
name: codex-skill
description: >
  Every new shared task, and every return from compact or context clear, must load /codex-skill and run init before continuing collaborative coding work.
  On load, first verify durable memory or CLAUDE.md contains the reload rule, init rule, and instruction to load subtask guide MD files only when needed; add or update it if missing.
  Use /codex-skill to coordinate with a Codex peer collaborator whose prior session context may be recoverable or may be fresh for this task, for context sync, disagreements, consensus-building,
  new-task kickoff, user-facing decision preparation, and Claude-mutates or Codex-mutates workflows.
---

# codex-skill

This skill is for Claude Code. Claude invokes Codex as a peer collaborator. Codex may resume useful prior session context for the task, or it may be effectively fresh; the workflow must handle both cases without inventing continuity.

Codex is invoked by Claude; Codex does not speak to the user directly. Claude remains responsible for user-facing conversation and for asking the user to decide unresolved issues. This does not make Claude's judgment higher than Codex's judgment.

## Persistence bootstrap

This is the first required action every time this skill is loaded, before choosing `chat`, planning, mutating, reviewing, or declaring completion.

1. Check durable project memory and the nearest applicable `CLAUDE.md` for a concrete rule that says: on a new shared task, and after compact or context clear, Claude must reload `codex-skill` and run `init` before continuing collaborative coding work.
2. If the rule is missing, add or update the smallest durable reminder in project memory if available; otherwise update or create the nearest project `CLAUDE.md` allowed by workspace policy.
3. The durable reminder must also say to run `init` before planning, chatting, mutating, reviewing, or declaring completion when Claude is entering a new shared task or returning from compact/context clear, and to load the subtask guide MD files only when the workflow needs them.
4. The reminder should be concrete, for example: `On every new shared task, and after compact or context clear, reload codex-skill and run init before continuing collaborative coding work. Follow SKILL.md first and load subtask guide MD files only when that workflow is needed. Claude and Codex must continue the collaboration protocol instead of working solo.`
5. This bootstrap is a protocol-preservation write. It is allowed before selecting Claude-mutates or Codex-mutates mode, but it must be narrowly scoped to memory/`CLAUDE.md` and must not modify task files.
6. If durable storage is ambiguous or workspace policy forbids the write, ask the user where to store the reminder before continuing collaborative work.

## Init

Use `init.md` to bootstrap Codex collaboration in exactly two cases:

- a new shared task is starting and Claude wants to brief Codex on the task background
- Claude has just returned from compact or context clear and wants Codex to help recover the working context

`init` is not a discussion turn and not a mutation turn. Claude must send exactly one init input shape:

- `task_background` plus `mutation_owner`: for a new task brief
- `recovery_background` plus `mutation_owner`: for tentative recovered context after compact/context clear

`mutation_owner` must be exactly `claude` or `codex`.

`init` privately injects the Codex collaboration protocol and the role-specific framing for the chosen mutation-owner path. Claude does not need to restate the peer relationship, review discipline, disagreement protocol, or path-specific Codex role in the init payload.

After `init`, Claude resumes the appropriate workflow based on Codex's reply. That may be `chat.md`, `review-my-plan.md`, `review-my-work.md`, `work-sync.md`, or `request-mutation.md`, depending on the chosen mutation-owner path and task state.

## Core model

Claude and Codex are peers in judgment. The modes below define only **mutation ownership**: which agent is allowed to perform state-changing work in the workspace or external systems.

State-changing work includes file edits, generated artifacts, write-formatters, dependency changes, migrations, commands that update snapshots/caches/databases/services, commits, pushes, releases, deploys, and any command that changes external state.

Both agents may do read-only investigation in any mode: read files, search the repository, inspect diffs, inspect docs, reason about tests, and verify claims. If a command might write or affect shared state, it belongs to the mutation owner for the current mode.

Do not repeat the full peer-collaboration charter in every ordinary Codex call. Establish it through `init` when the shared task begins, and again when Claude returns from compact or context clear, then continue with concise task-specific briefs.

Do not repeat durable background in every call. In normal ongoing work, Codex should use whatever current session context is actually available plus Claude's current delta. Use `init` to establish a new task brief or to recover from compact/context clear; use the other workflow guides for normal follow-up turns.

## Review and consensus discipline

- Discuss before state-changing work until the plan and next step are clear enough that both agents can support it.
- Review rigorously. Each agent should look for requirement gaps, hallucinated assumptions, regressions, edge cases, and weak evidence. Pushback is for better information and a better result, not for winning.
- During review, personally fact-check important claims using read-only investigation when possible. Do not accept the other agent's summary as evidence.
- Review the coherence of the whole affected system, not only the other agent's task slice. Check whether code, tests, docs, prompts, durable memory/`CLAUDE.md`, generated artifacts, and workflow instructions still fit together without contradictions.
- When the task changes this skill, treat the whole skill as the affected system: check `SKILL.md`, guide files, CLI prompt generation, wrapper scripts, README, command names, and generated prompt text for consistency.
- The mutation owner must self-check with the same fact-checking and coherence standards before asking the other agent to review.
- Do not blindly accept Codex, and do not silently ignore Codex. If you disagree, use the discussion command for the current path: `chat.md` on Claude-mutates, `work-sync.md` on Codex-mutates.
- If either agent believes the other is wrong, it should try to persuade with evidence and concrete reasoning. Do not concede just to move the workflow forward.
- If Codex proposes a plan on the Codex-mutates path and Claude disagrees, use `work-sync.md`. Do not proceed to mutation until real consensus is reached or the user decides.
- Consensus means both agents can defend the same next action from evidence. It is not a procedural compromise made only to move forward.
- If consensus cannot be reached, or both agents are unsure, Claude asks the user. Either agent may request escalation, but Claude performs the user-facing question. Present the smallest useful set of options, risks, and a recommendation when one is defensible.

## Choose the workflow

Use only one mutation owner for a task segment to avoid conflicting edits and process collisions.

| Situation | Guide |
| --- | --- |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| Normal sync, requirement changes, uncertainty, stuck states, disagreements, or consensus-building on the Claude-mutates path | `chat.md` |
| Claude will own state-changing work and wants Codex to review the plan before Claude mutates | `review-my-plan.md` |
| Claude owned state-changing work and wants Codex to review before delivery, commit, PR, merge, release, deploy, or "done" | `review-my-work.md` |
| Codex will own state-changing work and the agents need a non-mutation sync turn | `work-sync.md` |
| Codex will own state-changing work and Claude has approved one small mutation step | `request-mutation.md` |

Use the guide whose name matches the current workflow.

## Codex-mutates loop

1. On a new shared task, and after compact or context clear, run `init.md` first.
2. Use `work-sync.md` for every non-mutation turn: discussion, disagreement, plan output, plan correction, or Codex's response to Claude's review of prior mutation work.
3. If Codex includes a candidate `plan` in `work-sync.md` and Claude agrees on one step, use `request-mutation.md` for exactly one approved mutation.
4. Claude reviews the mutation result independently by reading/searching/verifying.
5. If more discussion, correction, or another candidate plan is needed, return to `work-sync.md`.
6. Repeat small steps. Codex must stop after each mutation for Claude review.

## Claude-mutates loop

1. On a new shared task, and after compact or context clear, run `init.md` first.
2. Use `chat.md` until the broad direction is understood.
3. Use `review-my-plan.md` before Claude performs meaningful state-changing work.
4. If Codex disagrees, use `chat.md` to resolve the disagreement or prepare a user decision.
5. Claude performs the agreed mutation step and self-checks.
6. Use `review-my-work.md` before final delivery or before any commit/PR/merge/release/deploy claim.

## Message continuity

Every Codex call should feel like the next message in the same collaboration thread:

- Background is optional. Include durable task/project context on the first call of a task, when it changed, or when Codex lacks context needed for review. Do not resend stable background every round.
- In Codex-mutates mode, `work-sync.md` handles discussion and candidate plan output. `request-mutation.md` should normally include only the approved mutation step plus any fresh user message that matters for that step.
- In Claude-mutates mode, Claude may include enough background for Codex to review Claude's plan or work, because Claude owns the changes. After Claude compact/context clear, first run `init.md` with `recovery_background` plus `mutation_owner: "claude"`, then continue.
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
