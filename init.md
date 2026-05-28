# init

Use this as the collaboration bootstrap entrypoint.

Session continuity is wrapper-managed. The cxsk_invoker must use wrapper commands and must not call raw `codex` directly or manually edit/delete `<repo>/.codex-skill/cxsk_channels.json`.

`init` may target a specific managed cxsk_channel with `--cxsk-channel <name>`. If that cxsk_channel does not exist yet, the wrapper creates it automatically and persists it in the structured managed config.

Use `init` in two cases:

- a new shared task is starting and the cxsk_invoker wants to brief Codex on the task background
- the cxsk_invoker has just returned from compact or context clear and wants Codex to help recover the working context

`init` is not a mutation step and not a discussion turn.

## Input contract

Call `init` with JSON on stdin. The JSON must contain exactly one background field.

New task:

```json
{
  "task_background": "Summarize the new task background for Codex here."
}
```

Recovery:

```json
{
  "recovery_background": "Summarize the cxsk_invoker's tentative recovered background here."
}
```

Rules:

- `task_background` and `recovery_background` are mutually exclusive
- one of them is required
- after `init`, continue with whichever normal command fits the next step

## Output contract

Codex replies in markdown, not JSON.

If the input used `task_background`, Codex must include:

```md
## Task Understanding Reply
...
```

If the input used `recovery_background`, Codex must include:

```md
## Context Recovery Reply
...
```
