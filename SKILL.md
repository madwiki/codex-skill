---
name: codex-skill
description: >
  On every new shared task, after compact or context clear, and whenever mutation ownership reverses, load /codex-skill and run init before continuing collaborative coding work.
  Use /codex-skill to coordinate with one or more managed Codex agents for caller-mutates and codex-mutates workflows, discussion, review, and controlled mutation steps.
---

# codex-skill

This skill is caller-agnostic. The caller may be Claude Code, Codex, OpenCode, or another tool that invokes the wrapper commands. Codex does not speak to the end user directly. The caller remains responsible for user-facing conversation and for asking the user to decide unresolved issues.

Session continuity is wrapper-managed. The caller must use `bin/codex-skill-*` commands instead of calling raw `codex` directly. The caller must not manually edit, delete, or replace `<repo>/.claude/codex_agents.json`.

The managed config lives at `<repo>/.claude/codex_agents.json`. It contains:

- top-level `caller` text fields for caller baseline, working style, extra context, and stage guidance
- top-level `shared_stages`
- top-level `work_modes`
- an `agents` array

Each agent may store:

- `name`
- `description`
- `focus`
- `baseline`
- `extra_context`
- `stage_guidance`
- `session_id`
- `model`
- `reasoning_effort`
- `previous_session_ids`

All wrapper commands accept optional `--agent <name>` to target a specific managed agent. The default agent name is `default`.

## Injection boundaries

- `caller.*` is caller-side guidance. It is returned to the caller in wrapper output and is not injected into Codex prompts.
- `shared_stages` and `work_modes.*.stages` are common stage guidance. They may be shown on both sides.
- `agents[*].*` is agent-side guidance. It is injected only into the currently targeted Codex agent prompt.
- Wrapper-injected system guidance is labeled `Codex Skill Reminder`.
- User-configured guidance is labeled `User Reminder`.
- `init` always carries full reminders.
- Normal ongoing turns use a 3-turn cadence per agent: full reminder on turns 1, 4, 7, ... and brief reminder on the two turns in between.

If the workspace still has legacy config state, the wrapper auto-migrates it once into the latest `codex_agents.json` format and surfaces a migration notice in that command's output so the caller knows the storage model changed. This includes both:

- legacy single-session files (`codex_session.json` and optional `codex_session_history.json`)
- older structured configs that still use legacy caller field names or mode names

## References

Use the unified format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` when a guidance block needs to point at a large file instead of repeating full content.

- Prefer direct narrative text for short or medium guidance.
- Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context.
- The caller decides when to keep content inline and when to switch to `[[REF:...]]`.
- The wrapper provides only the reference protocol and reminder behavior.
- The wrapper never inlines referenced files automatically.
- If continuity loss means Codex cannot confidently identify the referenced source and relevant content, Codex must re-read the referenced file before relying on it.

`.claude/codex-skill-refs/` is the conventional place for long Codex Skill reference documents, but any workspace file may be referenced with the same syntax.

## Init

Use `init.md` to bootstrap Codex collaboration in exactly three cases:

- a new shared task is starting and the caller wants to brief Codex on the task background
- the caller has just returned from compact or context clear and wants Codex to help recover the working context
- mutation ownership is switching between the caller and Codex, and the caller needs to re-bootstrap Codex under the new path before continuing

`init` is not a discussion turn and not a mutation turn. The caller must send exactly one init input shape:

- `task_background` plus `mutation_owner`: for a new task brief
- `recovery_background` plus `mutation_owner`: for tentative recovered context after compact/context clear

`mutation_owner` must be exactly `caller` or `codex`.

`init` privately injects the Codex collaboration protocol and the role-specific framing for the chosen mutation-owner path. The caller does not need to restate the peer relationship, review discipline, disagreement protocol, or path-specific Codex role in the init payload.

After `init`, the caller resumes the appropriate workflow based on Codex's reply. That may be `chat.md`, `review-my-plan.md`, `review-my-work.md`, `work-sync.md`, or `request-mutation.md`, depending on the chosen mutation-owner path and task state.

If mutation ownership reverses during the same task segment, stop the old path, rerun `init` with the new `mutation_owner`, and only then continue on the new path.

## Core model

The caller and Codex are peers in judgment. The modes below define only mutation ownership: which side is allowed to perform state-changing work in the workspace or external systems.

State-changing work includes file edits, generated artifacts, write-formatters, dependency changes, migrations, commands that update snapshots, caches, databases, services, commits, pushes, releases, deploys, and any command that changes external state.

Both sides may do read-only investigation in any mode: read files, search the repository, inspect diffs, inspect docs, reason about tests, and verify claims. If a command might write or affect shared state, it belongs to the mutation owner for the current mode.

The wrapper enforces sandbox policy:

- `init.md`, `chat.md`, `review-my-plan.md`, `review-my-work.md`, and `work-sync.md` run with `read-only`
- `request-mutation.md` runs with `workspace-write` by default
- if the caller decides the approved mutation step genuinely needs more than the default mutation sandbox, the caller may resend `request-mutation.md` with `sandbox_mode: "full-access"`, which maps to `danger-full-access`

## Review and consensus discipline

- Discuss before state-changing work until the plan and next step are clear enough that both sides can support it.
- Review rigorously. Look for requirement gaps, hallucinated assumptions, regressions, edge cases, and weak evidence.
- During review, personally fact-check important claims using read-only investigation when possible. Do not accept the other side's summary as evidence.
- Review the coherence of the whole affected system, not only the other side's task slice.
- The mutation owner must self-check with the same fact-checking and coherence standards before asking the other side to review.
- Do not blindly accept Codex, and do not silently ignore Codex.
- If either side believes the other is wrong, it should try to persuade with evidence and concrete reasoning. Do not concede just to move the workflow forward.
- Consensus means both sides can defend the same next action from evidence. It is not a procedural compromise made only to move forward.
- Do not ask the user merely because the next execution step is unclear.
- Ask the user only when there is a real unresolved disagreement between the caller and Codex and it has persisted for about 10 turns on the same issue.
- Either side may request escalation, but the caller performs the user-facing question. Present the smallest useful set of options, risks, and a recommendation when one is defensible.

## Choose the workflow

Use only one mutation owner for a task segment to avoid conflicting edits and process collisions.

| Situation | Guide |
| --- | --- |
| The user explicitly wants to abandon continuity and replace the current managed Codex agent session, either with a fresh one or a specific target session id | `dangerous-new-session.md` |
| The caller wants to update the managed config: caller baseline text, shared stage guidance, workflow-stage guidance, or agent focus/baseline text | `configure.md` |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| Normal sync, requirement changes, uncertainty, stuck states, disagreements, or consensus-building on the caller-mutates path | `chat.md` |
| The caller will own state-changing work and wants Codex to review the plan before caller mutation | `review-my-plan.md` |
| The caller owned state-changing work and wants Codex to review before delivery, commit, PR, merge, release, deploy, or "done" | `review-my-work.md` |
| Codex will own state-changing work and the agents need a non-mutation sync turn | `work-sync.md` |
| Codex will own state-changing work and the caller has approved one small mutation step | `request-mutation.md` |

Use the guide whose name matches the current workflow.

## codex-mutates loop

1. On a new shared task, after compact or context clear, and whenever switching into codex-mutates from caller-mutates, run `init.md` first.
2. Use `work-sync.md` for every non-mutation turn: discussion, disagreement, plan output, plan correction, or Codex's response to the caller's review of prior mutation work.
3. If Codex includes a candidate `plan` in `work-sync.md` and the caller agrees on one step, use `request-mutation.md` for exactly one approved mutation.
4. The caller reviews the mutation result independently by reading, searching, and verifying.
5. If more discussion, correction, or another candidate plan is needed, return to `work-sync.md`.
6. Repeat small steps. Codex must stop after each mutation for caller review.

## caller-mutates loop

1. On a new shared task, after compact or context clear, and whenever switching into caller-mutates from codex-mutates, run `init.md` first.
2. Use `chat.md` until the broad direction is understood.
3. Use `review-my-plan.md` before the caller performs meaningful state-changing work.
4. If Codex disagrees, use `chat.md` to resolve the disagreement or prepare a user decision.
5. The caller performs the agreed mutation step and self-checks.
6. Use `review-my-work.md` before final delivery or before any commit, PR, merge, release, or deploy claim.

## Message continuity

Every Codex call should feel like the next message in the same collaboration thread:

- Background is optional. Include durable task or project context on the first call of a task, when it changed, or when Codex lacks context needed for review. Do not resend stable background every round.
- In codex-mutates mode, `work-sync.md` handles discussion and candidate plan output. `request-mutation.md` should normally include only the approved mutation step plus any fresh user message that matters for that step.
- In caller-mutates mode, the caller may include enough background for Codex to review the caller's plan or work, because the caller owns the changes. After caller compact or context clear, first run `init.md` with `recovery_background` plus `mutation_owner: "caller"`, then continue.
- Current turn context explains what happened since the last Codex reply: what the caller told the user, what the user said, what the caller did, what changed, and what the caller now believes.
- Include verbatim user text only when the user actually said something new since the last Codex call. If there is no fresh user message, omit the block entirely.
- When verbatim user text is included, explain why the user said it and what situation surrounded it.
- The caller's direct message to Codex contains the caller's view, request, concerns, disagreements, and requested pushback.

## Patience

Codex may inspect files, reason through a large context, compact or resume its own session, or run verification. Treat the command as a long-running collaboration turn, not a short RPC. The default timeout is intentionally broad.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/codex-skill`)
- Guides live directly under `<skill_root>`.
- Commands live under `<skill_root>/bin/`.
