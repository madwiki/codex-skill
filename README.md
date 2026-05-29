# mad-agent-mesh

A mams_invoker-facing skill that lets the mams_invoker collaborate with one or more managed MAMS channels.

This branch currently supports:

- mams_invoker-agnostic invocation
- Codex and Claude Code as managed runners
- per-mams_channel `can_mutate`
- per-mams_channel `runner` and `runner_config`
- mams_invoker-side and mams_channel-side reminders
- managed session continuity

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/madagentmesh ~/.claude/skills/madagentmesh
```

## Config

The managed config lives at:

`<repo>/.mad-agent-mesh/mams_channels.json`

Top-level keys:

- `mams_invoker`
- `shared_stages`
- `mams_channels`

Each `mams_channel` may declare:

- `runner`
  - currently supported: `codex`, `claude-code`
- `runner_config`
  - optional runner-specific adapter config

Important behavior:

- `mams_invoker.can_mutate` is reminder-only.
- `mams_channels[*].can_mutate` is enforced for `execute-this-plan` and `execute-this-plan-part`.
- `mams_invoker.*` is returned to the mams_invoker, not injected into managed channel prompts.
- `mams_channels[*].*` is injected only into the targeted managed channel prompt.
- `shared_stages` may be shown on both sides.
- wrapper-generated blocks are boundary-tagged with `<<<NAME.BEGIN>>> ... <<<NAME.END>>>`
- block names use underscores; block state uses dotted suffixes such as `.BEGIN` and `.END`

## Commands

- `bin/init`
- `bin/invoke`
- `bin/sync`
- `bin/review-this-plan`
- `bin/review-this-work`
- `bin/execute-this-plan`
- `bin/execute-this-plan-part`
- `bin/configure`
- `bin/update-config`
- `bin/dangerous-new-session`

All commands accept optional `--mams-channel <name>`. When omitted, the wrapper uses the `default` mams_channel.

Preferred calling pattern:

- use `invoke` when you want one blocking wrapper call that waits for one or more mams_channel results
- let `invoke` wait internally instead of wrapping raw wrapper commands in external polling
- if all requests are read-only, `invoke` will fan them out concurrently and return the settled results together
- if any request mutates, `invoke` will still use one wrapper call, but it will run those requests sequentially

Use:

- `configure` when you want to patch mams_invoker guidance, shared guidance, or mams_channel metadata with explicit JSON fields
- `update-config` when you want the wrapper to read whatever managed state already exists, normalize it, and rewrite the canonical config at `.mad-agent-mesh/mams_channels.json`

## Notes

- Use wrapper commands only. Do not call raw runner CLIs directly.
- Do not manually edit or delete the managed config.
- Legacy config is auto-migrated on first use.
