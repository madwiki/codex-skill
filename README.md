# codex-skill

A caller-facing skill that lets the caller collaborate with one or more managed Codex channels.

Main branch currently supports:

- caller-agnostic invocation
- Codex-managed channels
- per-channel `can_mutate`
- caller-side and channel-side reminders
- managed session continuity

Main branch does **not** yet support non-Codex runners.

## Install

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/madwiki/codex-skill ~/.claude/skills/codex-skill
```

## Config

The managed config lives at:

`<repo>/.codex-skill/codex_agents.json`

Top-level keys:

- `caller`
- `shared_stages`
- `agents`

Important behavior:

- `caller.can_mutate` is reminder-only.
- `agents[*].can_mutate` is enforced for `request-mutation`.
- `caller.*` is returned to the caller, not injected into Codex prompts.
- `agents[*].*` is injected only into the targeted Codex prompt.
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

All commands accept optional `--agent <name>`. When omitted, the wrapper uses the `default` channel.

Use:

- `configure` when you want to patch caller guidance, shared guidance, or channel metadata with explicit JSON fields
- `update-config` when you want the wrapper to read whatever managed state already exists, normalize it, and rewrite the canonical config at `.codex-skill/codex_agents.json`

## Notes

- Use wrapper commands only. Do not call raw `codex` directly.
- Do not manually edit or delete the managed config.
- Legacy config is auto-migrated on first use.
