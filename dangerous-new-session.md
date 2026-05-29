# dangerous-new-session

Use this only when the user explicitly wants to abandon the selected managed-channel continuity and authorize a fresh managed runner session for that mams_channel slot.

This is a dangerous command by design. Do not use it just because resume failed, the current session looks confusing, or the mams_invoker wants a clean slate. Only use it after the user explicitly asks for a fresh start, replacement, reset, switch, or continuity break.

The mams_invoker must not call raw runner CLIs directly and must not manually edit, delete, or replace `<repo>/.mad-agent-mesh/mams_channels.json`.

This command may target a specific managed mams_channel with `--mams-channel <name>`. When omitted, it operates on the `default` mams_channel.

## Input contract

Call `dangerous-new-session` with JSON on stdin:

```json
{
  "user_permission": "Quote or summarize the user's explicit instruction to abandon the current managed continuity and start fresh.",
  "target_session_id": "Optional. If provided, switch the managed mams_channel to this specific existing session id instead of creating a fresh one.",
  "mams_channel_description": "Optional. Persist a description / responsibility for this mams_channel.",
  "model": "Optional. Persist the default model for this mams_channel.",
  "reasoning_effort": "Optional. Persist the default reasoning effort for this mams_channel."
}
```

Rules:

- `user_permission` is required and must be a non-empty string
- `target_session_id` is optional; when provided, it must be a non-empty string
- `mams_channel_description`, `model`, and `reasoning_effort` are optional; when provided, each must be a non-empty string
- use this only after explicit user permission
- if `target_session_id` is omitted, this command creates a fresh persistent managed runner session immediately for the selected mams_channel
- if `target_session_id` is provided, this command switches the selected managed mams_channel to that specific session id
- this command records the previous and previous-previous session ids inside the selected mams_channel's `previous_session_ids`
- this command does not require `init`; `init` remains a separate collaboration bootstrap command

## Output contract

The wrapper replies in plain text. It should tell the mams_invoker:

- which mams_channel was updated
- the new current session id
- which previous session ids were recorded for recovery on that mams_channel

## Run

```bash
<skill_root>/bin/dangerous-new-session < dangerous-new-session.json
```

Named mams_channel example:

```bash
<skill_root>/bin/dangerous-new-session --mams-channel reviewer-a < dangerous-new-session.json
```
