# update-config

Use this command when the cxsk_invoker wants the wrapper to materialize the current managed state into the canonical config location without hand-editing files.

This command does **not** mutate task files and does **not** change current session continuity by itself.

## What it does

- reads any currently discoverable managed state
- normalizes legacy or stale structure
- rewrites the canonical config at `.codex-skill/cxsk_channels.json`

Typical use:

- right after updating the skill
- when a new cxsk_invoker takes over and first needs the canonical config in the right place
- when legacy `.claude/...` state still exists and should be folded into the canonical config

## Input contract

This command accepts **empty stdin only**.

Example:

```bash
<skill_root>/bin/codex-skill-update-config --cwd <workspace>
```

## Output

The wrapper reports:

- whether it created a canonical config
- whether it normalized legacy or stale state
- the canonical config path
- the currently known managed cxsk_channel names

## Scope

`update-config` does **not** patch reminder text or cxsk_channel metadata. Use `configure` for explicit cxsk_invoker or cxsk_channel edits.
