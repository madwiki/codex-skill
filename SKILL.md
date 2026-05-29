---
name: mad-agent-mesh
description: >
  Use /mad-agent-mesh to coordinate with one or more managed MAMS channels.
  Run init on every new shared task and after compact/context clear when shared context needs to be re-established.
---

# mad-agent-mesh

This skill is mams_invoker-agnostic. The mams_invoker may be Claude Code, Codex, OpenCode, or another tool that invokes the wrapper commands. The targeted managed channel does not speak to the end user directly. The mams_invoker remains responsible for user-facing conversation and for asking the user to decide unresolved issues.

Session continuity is wrapper-managed. Use only commands under `<skill_root>/bin/`. Do not call raw runner CLIs directly. Do not manually edit, delete, or replace `<repo>/.mad-agent-mesh/mams_channels.json`.

## Managed config

The managed config lives at `<repo>/.mad-agent-mesh/mams_channels.json`.

Top-level fields:

- `mams_invoker`
- `shared_stages`
- `mams_channels`

`mams_invoker` may store:

- `baseline`
- `working_style`
- `extra_context`
- `stage_guidance`
- `can_mutate`

`mams_channels[*]` may store:

- `name`
- `description`
- `focus`
- `baseline`
- `extra_context`
- `stage_guidance`
- `can_mutate`
- `runner`
- `runner_config`
- `session_id`
- `model`
- `reasoning_effort`
- `previous_session_ids`

`mams_invoker.can_mutate` is a reminder field only. The wrapper cannot enforce it because the mams_invoker is outside the managed runner runtime.

`mams_channels[*].can_mutate` is enforced. Only mams_channels with `can_mutate: true` may use `execute-this-plan` or `execute-this-plan-part`.

## Injection boundaries

- `mams_invoker.*` is mams_invoker-side guidance. It is returned to the mams_invoker in wrapper output and is not injected into managed channel prompts.
- `shared_stages` is common stage guidance. It may be shown on both sides.
- `mams_channels[*].*` is mams_channel-side guidance. It is injected only into the currently targeted managed channel prompt.
- Wrapper-injected system guidance is labeled `Mad Agent Mesh Reminder` and may use full or brief form.
- User-configured guidance is labeled `User Reminder` and remains the full configured content.
- Wrapper-generated blocks are boundary-tagged with `<<<NAME.BEGIN>>> ... <<<NAME.END>>>`.
- Block names use underscores; block state uses dotted suffixes such as `.BEGIN` and `.END`.
- `init` always carries the full Mad Agent Mesh Reminder and the full User Reminder.
- Ongoing turns use a 3-turn cadence only for the Mad Agent Mesh Reminder: full on turns 1, 4, 7, ... and brief on the two turns in between.
- The User Reminder always remains the full configured content; the Mad Agent Mesh Reminder brief form explicitly reminds that the full User Reminder still applies.

## References

Use the unified format `[[REF:<relative-path>]]` or `[[REF:<relative-path>::<locator>]]` when a guidance block needs to point at a large file instead of repeating full content.

- Prefer direct narrative text for short or medium guidance.
- Use `[[REF:...]]` only when the underlying material is large enough that repeating it every turn would waste context.
- The mams_invoker decides when to keep content inline and when to switch to `[[REF:...]]`.
- The wrapper never inlines referenced files automatically.
- If continuity loss means the targeted managed channel cannot confidently identify the referenced source and relevant content, it must re-read the referenced file before relying on it.

`.mad-agent-mesh/refs/` is the conventional place for long Mad Agent Mesh reference documents, but any workspace file may be referenced with the same syntax.

## Review and disagreement discipline

- Discuss before state-changing work until the next step is clear enough that both sides can defend it from evidence.
- Personally fact-check important claims instead of trusting summaries.
- Review whole-system coherence, not only the local edit idea.
- If either side raises or continues a disagreement, it must include evidence and citations when possible:
  - relevant files
  - relevant docs
  - line ranges when available
- Without evidence, a point should be framed only as `concern`, `hypothesis`, or `needs verification`, not as a settled blocker.
- Ask the user only when a real unresolved disagreement between the mams_invoker and the targeted managed channel has persisted for about 10 turns on the same issue.

## Commands

Use only one command per current workflow need.

| Situation | Guide |
| --- | --- |
| Replace or switch the current managed session for a mams_channel after explicit user authorization | `dangerous-new-session.md` |
| Patch mams_invoker guidance, shared stage guidance, or mams_channel metadata | `configure.md` |
| Normalize existing managed state and rewrite the canonical config | `update-config.md` |
| Bootstrap a new shared task or recover after compact/context clear | `init.md` |
| Drive one or more mams_channel calls through one blocking wrapper call | `invoke.md` |
| General discussion, coordination, disagreement handling, or review relay | `sync.md` |
| Review a submitted plan before any execution begins | `review-this-plan.md` |
| Review completed execution work before treating it as accepted or delivered | `review-this-work.md` |
| Execute one approved whole plan on a mutate-capable mams_channel | `execute-this-plan.md` |
| Execute one approved plan part on a mutate-capable mams_channel | `execute-this-plan-part.md` |

## Command model

- `init` is collaboration bootstrap only. It is not mutation.
- `invoke` is the preferred blocking wrapper entrypoint when the mams_invoker wants one or more mams_channel calls and does not want to poll.
- `sync` is coordination only. It is not approval and not mutation permission.
- `review-this-plan` is a hard gate before execution begins.
- `review-this-work` is a hard gate before accepted delivery.
- `execute-this-plan` is the whole-plan execution turn for a mutate-capable mams_channel.
- `execute-this-plan-part` is the plan-part execution turn for a mutate-capable mams_channel, and should be used only when the full plan is genuinely too large for one turn.

## Paths

- `<skill_root>` = the directory containing this `SKILL.md` (common: `~/.claude/skills/madagentmesh`)
- Guides live directly under `<skill_root>`.
- Commands live under `<skill_root>/bin/`.
