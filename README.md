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
- `cxsk_channels[*].can_mutate` is enforced for `request-mutation`.
- `cxsk_invoker.*` is returned to the cxsk_invoker, not injected into Codex prompts.
- `cxsk_channels[*].*` is injected only into the targeted Codex prompt.
- `shared_stages` may be shown on both sides.

## Commands

- `bin/codex-skill-init`
- `bin/codex-skill-chat`
- `bin/codex-skill-review-my-plan`
- `bin/codex-skill-review-my-work`
- `bin/codex-skill-work-sync`
- `bin/codex-skill-request-mutation`
- `bin/codex-skill-configure`
- `bin/codex-skill-update-config`
- `bin/codex-skill-dangerous-new-session`

All commands accept optional `--cxsk-channel <name>`. When omitted, the wrapper uses the `default` cxsk_channel.

Use:

- `configure` when you want to patch cxsk_invoker guidance, shared guidance, or cxsk_channel metadata with explicit JSON fields
- `update-config` when you want the wrapper to read whatever managed state already exists, normalize it, and rewrite the canonical config at `.codex-skill/cxsk_channels.json`

## Notes

- Use wrapper commands only. Do not call raw `codex` directly.
- Do not manually edit or delete the managed config.
- Legacy config is auto-migrated on first use.
