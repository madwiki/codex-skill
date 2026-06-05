# sync

Use `sync` for managed discussion turns.

This command is read-only. It is not approval and not mutation permission.

## Input

```json
{
  "sync_message": "Discussion / clarification / review relay / plan repair context.",
  "fresh_user_message": "Optional. A fresh user verbatim message.",
  "stage_context": "plan"
}
```

`stage_context` may be:

- `plan`
- `execution`

It controls which configured stage prompt block is injected for the target channel.
