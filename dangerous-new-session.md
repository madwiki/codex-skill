# dangerous-new-session

Use this only when the user explicitly wants to abandon the current Codex continuity and authorize a fresh managed Codex session for this workspace.

This is a dangerous command by design. Do not use it just because resume failed, the current session looks confusing, or Claude wants a clean slate. Only use it after the user explicitly asks for a fresh start, replacement, reset, switch, or continuity break.

Claude must not call raw `codex` directly and must not manually edit, delete, or replace `<repo>/.claude/codex_session.json`.

## Input contract

Call `dangerous-new-session` with JSON on stdin:

```json
{
  "user_permission": "Quote or summarize the user's explicit instruction to abandon the current Codex continuity and start fresh.",
  "target_session_id": "Optional. If provided, switch the managed session to this specific existing session id instead of creating a fresh one."
}
```

Rules:

- `user_permission` is required and must be a non-empty string
- `target_session_id` is optional; when provided, it must be a non-empty string
- use this only after explicit user permission
- if `target_session_id` is omitted, this command creates a fresh persistent managed Codex session immediately
- if `target_session_id` is provided, this command switches the current managed session to that specific session id
- this command records the previous and previous-previous session ids in `<repo>/.claude/codex_session_history.json`
- this command does not require `init`; `init` remains a separate collaboration bootstrap command

## Output contract

The wrapper replies in plain text. It should tell Claude:

- the new current session id
- which previous session ids were recorded for recovery

## Run

```bash
<skill_root>/bin/codex-skill-dangerous-new-session < dangerous-new-session.json
```
