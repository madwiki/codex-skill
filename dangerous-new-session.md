# dangerous-new-session

Use this only when the user explicitly wants to abandon the selected Codex cxsk_channel continuity and authorize a fresh managed Codex session for that cxsk_channel slot.

This is a dangerous command by design. Do not use it just because resume failed, the current session looks confusing, or the cxsk_invoker wants a clean slate. Only use it after the user explicitly asks for a fresh start, replacement, reset, switch, or continuity break.

The cxsk_invoker must not call raw `codex` directly and must not manually edit, delete, or replace `<repo>/.codex-skill/cxsk_channels.json`.

This command may target a specific managed cxsk_channel with `--cxsk-channel <name>`. When omitted, it operates on the `default` cxsk_channel.

## Input contract

Call `dangerous-new-session` with JSON on stdin:

```json
{
  "user_permission": "Quote or summarize the user's explicit instruction to abandon the current Codex continuity and start fresh.",
  "target_session_id": "Optional. If provided, switch the managed cxsk_channel to this specific existing session id instead of creating a fresh one.",
  "cxsk_channel_description": "Optional. Persist a description / responsibility for this cxsk_channel.",
  "model": "Optional. Persist the default model for this cxsk_channel.",
  "reasoning_effort": "Optional. Persist the default reasoning effort for this cxsk_channel."
}
```

Rules:

- `user_permission` is required and must be a non-empty string
- `target_session_id` is optional; when provided, it must be a non-empty string
- `cxsk_channel_description`, `model`, and `reasoning_effort` are optional; when provided, each must be a non-empty string
- use this only after explicit user permission
- if `target_session_id` is omitted, this command creates a fresh persistent managed Codex session immediately for the selected cxsk_channel
- if `target_session_id` is provided, this command switches the selected managed cxsk_channel to that specific session id
- this command records the previous and previous-previous session ids inside the selected cxsk_channel's `previous_session_ids`
- this command does not require `init`; `init` remains a separate collaboration bootstrap command

## Output contract

The wrapper replies in plain text. It should tell the cxsk_invoker:

- which cxsk_channel was updated
- the new current session id
- which previous session ids were recorded for recovery on that cxsk_channel

## Run

```bash
<skill_root>/bin/codex-skill-dangerous-new-session < dangerous-new-session.json
```

Named cxsk_channel example:

```bash
<skill_root>/bin/codex-skill-dangerous-new-session --cxsk-channel reviewer-a < dangerous-new-session.json
```
