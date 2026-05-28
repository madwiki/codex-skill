---
name: codex-skill
description: >
  Use /codex-skill to coordinate with one or more managed Codex channels.
  Run init on every new shared task and after compact/context clear when shared context needs to be re-established.
---

# codex-skill

This skill is caller-agnostic. The caller may be Claude Code, Codex, OpenCode, or another tool that invokes the wrapper commands. Codex does not speak to the end user directly. The caller remains responsible for user-facing conversation and for asking the user to decide unresolved issues.

Session continuity is wrapper-managed. Use only `bin/codex-skill-*` commands. Do not call raw `codex` directly. Do not manually edit, delete, or replace `<repo>/.codex-skill/codex_agents.json`.

## Managed config

The managed config lives at `<repo>/.codex-skill/codex_agents.json`.

Top-level fields:

- `caller`
- `shared_stages`
- `agents`

`caller` may store:

- `baseline`
- `working_style`
- `extra_context`
- `stage_guidance`
- `can_mutate`

`agents[*]` may store:

- `name`
- `description`
- `focus`
- `baseline`
- `extra_context`
- `stage_guidance`
- `can_mutate`
- `session_id`
- `model`
- `reasoning_effort`
- `previous_session_ids`

`caller.can_mutate` is a reminder field only. The wrapper cannot enforce it because the caller is outside the managed Codex runtime.

`agents[*].can_mutate` is enforced. Only channels with `can_mutate: true` may use `request-mutation`.

## Injection boundaries

- `caller.*` is caller-side guidance. It is returned to the caller in wrapper output and is not injected into Codex prompts.
- `shared_stages` is common stage guidance. It may be shown on both sides.
- `agents[*].*` is channel-side guidance. It is injected only into the currently targeted Codex prompt.
- Wrapper-injected system guidance is labeled `Codex Skill Reminder`.
- User-configured guidance is labeled `User Reminder`.
- `init` always carries full reminders.
- Ongoing turns use a 3-turn cadence per channel: full reminder on turns 1, 4, 7, ... and brief reminder on the two turns in between.

## References

Use the unified format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` when a guidance block needs to point at a large file instead of repeating full content.

- Prefer direct narrative text for short or medium guidance.
- Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context.
- The caller decides when to keep content inline and when to switch to `[[REF:...]]`.
- The wrapper never inlines referenced files automatically.
- If continuity loss means Codex cannot confidently identify the referenced source and relevant content, Codex must re-read the referenced file before relying on it.

`.codex-skill/refs/` is the conventional place for long Codex Skill reference documents, but any workspace file may be referenced with the same syntax.

## Review and disagreement discipline

- Discuss before state-changing work until the next step is clear enough that both sides can defend it from evidence.
- Personally fact-check important claims instead of trusting summaries.
- Review whole-system coherence, not only the local edit idea.
- If either side raises or continues a disagreement, it must include evidence and citations when possible:
  - relevant files
  - relevant docs
  - line ranges when available
- Without evidence, a point should be framed only as `concern`, `hypothesis`, or `needs verification`, not as a settled blocker.
- Ask the user only when a real unresolved disagreement between the caller and Codex has persisted for about 10 turns on the same issue.

## Commands

Use only one command per current workflow need.

| Situation | Guide |
| --- | --- |
| Replace or switch the current managed session for a channel after explicit user authorization | `dangerous-new-session.md` |
| Update caller guidance, shared stage guidance, or channel metadata | `configure.md` |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| General discussion, sync, disagreement handling, or context clarification | `chat.md` |
| Review a proposed plan before any approved mutation step begins | `review-my-plan.md` |
| Review completed work before treating it as accepted or delivered | `review-my-work.md` |
| Non-mutation sync turn for a managed Codex channel | `work-sync.md` |
| Execute one approved mutation step on a mutate-capable channel | `request-mutation.md` |

## Command model

- `init` is collaboration bootstrap only. It is not mutation.
- `chat` is discussion only. It is not approval and not mutation permission.
- `review-my-plan` is a hard gate before any approved mutation step begins.
- `review-my-work` is a hard gate before accepted delivery.
- `work-sync` is a non-mutation sync turn.
- `request-mutation` is the only mutation permission turn, and only for a channel with `can_mutate: true`.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/codex-skill`)
- Guides live directly under `<skill_root>`.
- Commands live under `<skill_root>/bin/`.
