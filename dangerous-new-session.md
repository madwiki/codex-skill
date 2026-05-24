# dangerous-new-session

Use this only when the user explicitly wants to abandon the current Codex continuity and authorize a fresh managed Codex session for this workspace.

This is a dangerous command by design. Do not use it just because resume failed, the current session looks confusing, or Claude wants a clean slate. Only use it after the user explicitly asks for a fresh start, replacement, reset, switch, or continuity break.

Claude must not call raw `codex` directly and must not manually edit, delete, or replace `<repo>/.claude/codex_session.json`.

## Input contract

Call `dangerous-new-session` with JSON on stdin:

```json
{
  "user_permission": "Quote or summarize the user's explicit instruction to abandon the current Codex continuity and start fresh."
}
```

Rules:

- `user_permission` is required and must be a non-empty string
- use this only after explicit user permission
- this command does not talk to Codex
- if a managed session file exists, this command archives it to `~/.Trash`
- this command writes a one-time authorization that allows the next `init` call to create a fresh managed Codex session
- after this command succeeds, Claude must run `init` next
- do not use any other codex-skill command before that `init`

## Output contract

The wrapper replies in plain text. It should tell Claude:

- whether a prior managed session file was archived
- that a dangerous new session has been authorized
- that `init` must be the next command

## Run

```bash
<skill_root>/bin/codex-skill-dangerous-new-session < dangerous-new-session.json
```
