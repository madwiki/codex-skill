# codex-skill

A cxsk_invoker-facing skill that lets the cxsk_invoker collaborate with one or more managed Codex cxsk_channels.

Main branch currently supports:

- cxsk_invoker-agnostic invocation
- Codex-managed cxsk_channels
- per-cxsk_channel `can_mutate`
- cxsk_invoker-side and cxsk_channel-side reminders
- managed session continuity

Main branch does **not** yet support non-Codex runners.

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## Config

The managed config lives at:

`<repo>/.codex-skill/cxsk_channels.json`

Top-level keys:

- `cxsk_invoker`
- `shared_stages`
- `cxsk_channels`

Important behavior:

- `cxsk_invoker.can_mutate` is reminder-only.
- `cxsk_channels[*].can_mutate` is enforced for `execute-this-plan` and `execute-this-plan-part`.
- `cxsk_invoker.*` is returned to the cxsk_invoker, not injected into Codex prompts.
- `cxsk_channels[*].*` is injected only into the targeted Codex prompt.
- `shared_stages` may be shown on both sides.

## Commands

- `bin/codex-skill-init`
- `bin/codex-skill-invoke`
- `bin/codex-skill-sync`
- `bin/codex-skill-review-this-plan`
- `bin/codex-skill-review-this-work`
- `bin/codex-skill-execute-this-plan`
- `bin/codex-skill-execute-this-plan-part`
- `bin/codex-skill-configure`
- `bin/codex-skill-update-config`
- `bin/codex-skill-dangerous-new-session`

All commands accept optional `--cxsk-channel <name>`. When omitted, the wrapper uses the `default` cxsk_channel.

Preferred calling pattern:

- use `invoke` when you want one blocking wrapper call that waits for one or more cxsk_channel results
- let `invoke` wait internally instead of wrapping raw `codex-skill-*` commands in external polling
- if all requests are read-only, `invoke` will fan them out concurrently and return the settled results together
- if any request mutates, `invoke` will still use one wrapper call, but it will run those requests sequentially

Use:

- `configure` when you want to patch cxsk_invoker guidance, shared guidance, or cxsk_channel metadata with explicit JSON fields
- `update-config` when you want the wrapper to read whatever managed state already exists, normalize it, and rewrite the canonical config at `.codex-skill/cxsk_channels.json`

## Notes

- Use wrapper commands only. Do not call raw `codex` directly.
- Do not manually edit or delete the managed config.
- Legacy config is auto-migrated on first use.
