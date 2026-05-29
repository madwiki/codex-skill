# init

Use this as the collaboration bootstrap entrypoint.

Session continuity is wrapper-managed. The mams_invoker must use wrapper commands and must not call raw runner CLIs directly or manually edit/delete `<repo>/.mad-agent-mesh/mams_channels.json`.

`init` may target a specific managed mams_channel with `--mams-channel <name>`. If that mams_channel does not exist yet, the wrapper creates it automatically and persists it in the structured managed config.

Use `init` in two cases:

- a new shared task is starting and the mams_invoker wants to brief the targeted managed channel on the task background
- the mams_invoker has just returned from compact or context clear and wants the targeted managed channel to help recover the working context

`init` is not a mutation step and not a discussion turn.

## Input contract

Call `init` with JSON on stdin. The JSON must contain exactly one background field.

New task:

```json
{
  "task_background": "Summarize the new task background for the targeted managed channel here."
}
```

Recovery:

```json
{
  "recovery_background": "Summarize the mams_invoker's tentative recovered background here."
}
```

Rules:

- `task_background` and `recovery_background` are mutually exclusive
- one of them is required
- after `init`, continue with whichever normal command fits the next step

## Output contract

The targeted managed channel replies in markdown, not JSON.

If the input used `task_background`, the targeted managed channel must include:

```md
## Task Understanding Reply
...
```

If the input used `recovery_background`, the targeted managed channel must include:

```md
## Context Recovery Reply
...
```
