# dangerous-new-session

Use this only when the user explicitly authorizes abandoning the current managed session continuity for a channel slot.

## Input

```json
{
  "user_permission": "Quote or summarize the user's explicit authorization.",
  "target_session_id": "Optional. Switch to this existing session id instead of creating a fresh one.",
  "mams_channel_description": "Optional. Persist a public description for this channel.",
  "model": "Optional. Persist the default model for this channel.",
  "reasoning_effort": "Optional. Persist the default reasoning effort for this channel."
}
```

Rules:

- `user_permission` is required
- `target_session_id` is optional
- if `target_session_id` is omitted, the wrapper creates a fresh managed runner session immediately
- if `target_session_id` is provided, the wrapper switches the channel slot to that session id
- the wrapper records previous session ids in `previous_session_ids`
- the wrapper resets stage reminder state for the replacement session
