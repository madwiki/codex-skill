# dangerous-new-session

Use this only when the user explicitly wants to abandon the selected Codex agent continuity and authorize a fresh managed Codex session for that agent slot.

This is a dangerous command by design. Do not use it just because resume failed, the current session looks confusing, or the caller wants a clean slate. Only use it after the user explicitly asks for a fresh start, replacement, reset, switch, or continuity break.

The caller must not call raw `codex` directly and must not manually edit, delete, or replace `<repo>/.codex-skill/codex_agents.json`.

This command may target a specific managed agent with `--agent <name>`. When omitted, it operates on the `default` agent.

## Input contract

Call `dangerous-new-session` with JSON on stdin:

```json
{
  "user_permission": "Quote or summarize the user's explicit instruction to abandon the current Codex continuity and start fresh.",
  "target_session_id": "Optional. If provided, switch the managed agent to this specific existing session id instead of creating a fresh one.",
  "agent_description": "Optional. Persist a description / responsibility for this agent.",
  "model": "Optional. Persist the default model for this agent.",
  "reasoning_effort": "Optional. Persist the default reasoning effort for this agent."
}
```

Rules:

- `user_permission` is required and must be a non-empty string
- `target_session_id` is optional; when provided, it must be a non-empty string
- `agent_description`, `model`, and `reasoning_effort` are optional; when provided, each must be a non-empty string
- use this only after explicit user permission
- if `target_session_id` is omitted, this command creates a fresh persistent managed Codex session immediately for the selected agent
- if `target_session_id` is provided, this command switches the selected managed agent to that specific session id
- this command records the previous and previous-previous session ids inside the selected agent's `previous_session_ids`
- this command does not require `init`; `init` remains a separate collaboration bootstrap command

## Output contract

The wrapper replies in plain text. It should tell the caller:

- which agent was updated
- the new current session id
- which previous session ids were recorded for recovery on that agent

## Run

```bash
<skill_root>/bin/codex-skill-dangerous-new-session < dangerous-new-session.json
```

Named agent example:

```bash
<skill_root>/bin/codex-skill-dangerous-new-session --agent reviewer-a < dangerous-new-session.json
```
