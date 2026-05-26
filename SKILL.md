---
name: codex-skill
description: >
  Every new shared task, every return from compact or context clear, and every mutation-owner path reversal must load /codex-skill and run init before continuing collaborative coding work.
  On load, first verify durable memory or CLAUDE.md contains the reload rule, init rule, and instruction to load subtask guide MD files only when needed; add or update it if missing.
  Use /codex-skill to coordinate with a Codex peer collaborator whose prior session context may be recoverable or may be fresh for this task, for context sync, disagreements, consensus-building,
  new-task kickoff, user-facing decision preparation, and Claude-mutates or Codex-mutates workflows.
---

# codex-skill

This skill is for Claude Code. Claude invokes Codex as a peer collaborator. Codex may resume useful prior session context for the task, or it may be effectively fresh; the workflow must handle both cases without inventing continuity.

Codex is invoked by Claude; Codex does not speak to the user directly. Claude remains responsible for user-facing conversation and for asking the user to decide unresolved issues. This does not make Claude's judgment higher than Codex's judgment.

Session continuity is wrapper-managed. Claude must use the `bin/codex-skill-*` commands instead of calling raw `codex` directly. Claude must not manually edit, delete, or replace `<repo>/.claude/codex_agents.json`. The wrapper automatically resumes the selected managed agent session when it exists, and automatically creates a new managed session when that agent does not exist yet. If the user explicitly wants to abandon an existing continuity and replace it, Claude must use `dangerous-new-session.md`.

The managed config is a structured object under `<repo>/.claude/codex_agents.json`. It contains:

- top-level `claude` text fields for Claude baseline, working style, and stage guidance
- top-level `shared_stages`
- top-level `work_modes`
- an `agents` array

Each agent may store its `name`, `description`, `focus`, `baseline`, `extra_context`, `stage_guidance`, `session_id`, `model`, `reasoning_effort`, and `previous_session_ids`. All wrapper commands accept optional `--agent <name>` to target a specific managed agent; the default agent name is `default`.

If the workspace still has the legacy single-session files (`codex_session.json` and optional `codex_session_history.json`), the wrapper auto-migrates them once into `codex_agents.json`, continues from the migrated `default` agent, and surfaces a migration notice in that command's output so Claude knows the storage model changed.

When baseline text references a file, use the unified format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]`. The wrapper does not inline referenced files automatically. Instead it injects a reference-handling notice and a referenced-materials list so Codex knows that, after compaction or continuity loss, it must re-read the referenced file before relying on that content.

Prefer direct narrative text for short or medium guidance. Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context. Claude decides when to index content this way; the wrapper only provides the reference protocol and reminder behavior.

## Persistence bootstrap

This is the first required action every time this skill is loaded, before choosing `chat`, planning, mutating, reviewing, or declaring completion.

1. Check durable project memory and the nearest applicable `CLAUDE.md` for a concrete rule that says: on a new shared task, after compact or context clear, and whenever mutation ownership reverses between Claude and Codex, Claude must reload `codex-skill` and run `init` before continuing collaborative coding work.
2. If the rule is missing, add or update the smallest durable reminder in project memory if available; otherwise update or create the nearest project `CLAUDE.md` allowed by workspace policy.
3. The durable reminder must also say to run `init` before planning, chatting, mutating, reviewing, or declaring completion when Claude is entering a new shared task, returning from compact/context clear, or switching mutation ownership between Claude and Codex, and to load the subtask guide MD files only when the workflow needs them.
4. The reminder should be concrete, for example: `On every new shared task, after compact or context clear, and whenever mutation ownership switches between Claude and Codex, reload codex-skill and run init before continuing collaborative coding work. Follow SKILL.md first and load subtask guide MD files only when that workflow is needed. Claude and Codex must continue the collaboration protocol instead of working solo.`
5. This bootstrap is a protocol-preservation write. It is allowed before selecting Claude-mutates or Codex-mutates mode, but it must be narrowly scoped to memory/`CLAUDE.md` and must not modify task files.
6. If durable storage is ambiguous or workspace policy forbids the write, ask the user where to store the reminder before continuing collaborative work.

## Init

Use `init.md` to bootstrap Codex collaboration in exactly three cases:

- a new shared task is starting and Claude wants to brief Codex on the task background
- Claude has just returned from compact or context clear and wants Codex to help recover the working context
- the task is switching mutation-owner path and Claude needs to re-bootstrap Codex under the new path before continuing

`init` is not a discussion turn and not a mutation turn. Claude must send exactly one init input shape:

- `task_background` plus `mutation_owner`: for a new task brief
- `recovery_background` plus `mutation_owner`: for tentative recovered context after compact/context clear

`mutation_owner` must be exactly `claude` or `codex`.

`init` privately injects the Codex collaboration protocol and the role-specific framing for the chosen mutation-owner path. Claude does not need to restate the peer relationship, review discipline, disagreement protocol, or path-specific Codex role in the init payload.

`init` is only the collaboration bootstrap. It is not the session-management layer. Session creation or resume happens automatically inside the wrapper before `init` or any other workflow command runs.

After `init`, Claude resumes the appropriate workflow based on Codex's reply. That may be `chat.md`, `review-my-plan.md`, `review-my-work.md`, `work-sync.md`, or `request-mutation.md`, depending on the chosen mutation-owner path and task state.

If mutation ownership reverses during the same task segment, stop the old path, rerun `init` with the new `mutation_owner`, and only then continue on the new path.

## Core model

Claude and Codex are peers in judgment. The modes below define only **mutation ownership**: which agent is allowed to perform state-changing work in the workspace or external systems.

State-changing work includes file edits, generated artifacts, write-formatters, dependency changes, migrations, commands that update snapshots/caches/databases/services, commits, pushes, releases, deploys, and any command that changes external state.

Both agents may do read-only investigation in any mode: read files, search the repository, inspect diffs, inspect docs, reason about tests, and verify claims. If a command might write or affect shared state, it belongs to the mutation owner for the current mode.

The wrapper also enforces a sandbox policy:

- `init.md`, `chat.md`, `review-my-plan.md`, `review-my-work.md`, and `work-sync.md` run with `read-only`
- `request-mutation.md` runs with `workspace-write` by default
- if Claude decides the approved mutation step genuinely needs more than the default mutation sandbox, Claude may resend `request-mutation.md` with `sandbox_mode: "full-access"`, which maps to `danger-full-access`

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
| The user explicitly wants to abandon continuity and replace the current managed Codex agent session, either with a fresh one or a specific target session id | `dangerous-new-session.md` |
| Claude wants to update the managed config: Claude baseline text, shared stage guidance, workflow-stage guidance, or agent focus/baseline text | `configure.md` |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| Normal sync, requirement changes, uncertainty, stuck states, disagreements, or consensus-building on the Claude-mutates path | `chat.md` |
| Claude will own state-changing work and wants Codex to review the plan before Claude mutates | `review-my-plan.md` |
| Claude owned state-changing work and wants Codex to review before delivery, commit, PR, merge, release, deploy, or "done" | `review-my-work.md` |
| Codex will own state-changing work and the agents need a non-mutation sync turn | `work-sync.md` |
| Codex will own state-changing work and Claude has approved one small mutation step | `request-mutation.md` |

Use the guide whose name matches the current workflow.

## Codex-mutates loop

1. On a new shared task, after compact or context clear, and whenever switching into Codex-mutates from Claude-mutates, run `init.md` first.
2. Use `work-sync.md` for every non-mutation turn: discussion, disagreement, plan output, plan correction, or Codex's response to Claude's review of prior mutation work.
3. If Codex includes a candidate `plan` in `work-sync.md` and Claude agrees on one step, use `request-mutation.md` for exactly one approved mutation.
4. Claude reviews the mutation result independently by reading/searching/verifying.
5. If more discussion, correction, or another candidate plan is needed, return to `work-sync.md`.
6. Repeat small steps. Codex must stop after each mutation for Claude review.

## Claude-mutates loop

1. On a new shared task, after compact or context clear, and whenever switching into Claude-mutates from Codex-mutates, run `init.md` first.
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
