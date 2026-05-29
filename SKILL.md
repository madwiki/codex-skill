---
name: codex-skill
description: >
  Use /codex-skill to coordinate with one or more managed Codex cxsk_channels.
  Run init on every new shared task and after compact/context clear when shared context needs to be re-established.
---

# codex-skill

This skill is cxsk_invoker-agnostic. The cxsk_invoker may be Claude Code, Codex, OpenCode, or another tool that invokes the wrapper commands. Codex does not speak to the end user directly. The cxsk_invoker remains responsible for user-facing conversation and for asking the user to decide unresolved issues.

Session continuity is wrapper-managed. Use only `bin/codex-skill-*` commands. Do not call raw `codex` directly. Do not manually edit, delete, or replace `<repo>/.codex-skill/cxsk_channels.json`.

## Managed config

The managed config lives at `<repo>/.codex-skill/cxsk_channels.json`.

Top-level fields:

- `cxsk_invoker`
- `shared_stages`
- `cxsk_channels`

`cxsk_invoker` may store:

- `baseline`
- `working_style`
- `extra_context`
- `stage_guidance`
- `can_mutate`

`cxsk_channels[*]` may store:

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

`cxsk_invoker.can_mutate` is a reminder field only. The wrapper cannot enforce it because the cxsk_invoker is outside the managed Codex runtime.

`cxsk_channels[*].can_mutate` is enforced. Only cxsk_channels with `can_mutate: true` may use `execute-this-plan` or `execute-this-plan-part`.

## Injection boundaries

- `cxsk_invoker.*` is cxsk_invoker-side guidance. It is returned to the cxsk_invoker in wrapper output and is not injected into Codex prompts.
- `shared_stages` is common stage guidance. It may be shown on both sides.
- `cxsk_channels[*].*` is cxsk_channel-side guidance. It is injected only into the currently targeted Codex prompt.
- Wrapper-injected system guidance is labeled `Codex Skill Reminder` and may use full or brief form.
- User-configured guidance is labeled `User Reminder` and remains the full configured content.
- Wrapper-generated blocks are boundary-tagged with `<<<NAME.BEGIN>>> ... <<<NAME.END>>>`.
- Block names use underscores; block state uses dotted suffixes such as `.BEGIN` and `.END`.
- `init` always carries the full Codex Skill Reminder and the full User Reminder.
- Ongoing turns use a 3-turn cadence only for the Codex Skill Reminder: full on turns 1, 4, 7, ... and brief on the two turns in between.
- The User Reminder always remains the full configured content; the Codex Skill Reminder brief form explicitly reminds that the full User Reminder still applies.

## References

Use the unified format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` when a guidance block needs to point at a large file instead of repeating full content.

- Prefer direct narrative text for short or medium guidance.
- Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context.
- The cxsk_invoker decides when to keep content inline and when to switch to `[[REF:...]]`.
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
- Ask the user only when a real unresolved disagreement between the cxsk_invoker and Codex has persisted for about 10 turns on the same issue.

## Commands

Use only one command per current workflow need.

| Situation | Guide |
| --- | --- |
| Replace or switch the current managed session for a cxsk_channel after explicit user authorization | `dangerous-new-session.md` |
| Patch cxsk_invoker guidance, shared stage guidance, or cxsk_channel metadata | `configure.md` |
| Normalize existing managed state and rewrite the canonical config | `update-config.md` |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| Drive one or more cxsk_channel calls through one blocking wrapper call | `invoke.md` |
| General discussion, coordination, disagreement handling, or review relay | `sync.md` |
| Review a submitted plan before any execution begins | `review-this-plan.md` |
| Review completed execution work before treating it as accepted or delivered | `review-this-work.md` |
| Execute one approved whole plan on a mutate-capable cxsk_channel | `execute-this-plan.md` |
| Execute one approved plan part on a mutate-capable cxsk_channel | `execute-this-plan-part.md` |

## Command model

- `init` is collaboration bootstrap only. It is not mutation.
- `invoke` is the preferred blocking wrapper entrypoint when the cxsk_invoker wants one or more cxsk_channel calls and does not want to poll.
- `sync` is coordination only. It is not approval and not mutation permission.
- `review-this-plan` is a hard gate before execution begins.
- `review-this-work` is a hard gate before accepted delivery.
- `execute-this-plan` is the whole-plan execution turn for a mutate-capable cxsk_channel.
- `execute-this-plan-part` is the plan-part execution turn for a mutate-capable cxsk_channel, and should be used only when the full plan is genuinely too large for one turn.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/codex-skill`)
- Guides live directly under `<skill_root>`.
- Commands live under `<skill_root>/bin/`.
