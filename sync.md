# sync

Use this as the general sync and coordination command.

Use it for:

- routine coordination
- discussion and clarification
- plan repair
- disagreement handling
- relaying review outcomes
- escalating a blocker back to the planner or executor

`sync` does not authorize mutation.

## Input contract

```json
{
  "sync_message": "Write the cxsk_invoker's sync message here."
}
```

Optional:

```json
{
  "sync_message": "Write the cxsk_invoker's sync message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this sync."
}
```

## Output contract

Codex replies in markdown, not JSON.

Required:

```md
## Discussion Reply
...
```

Optional when a revised or newly proposed plan is genuinely ready:

```md
## Plan
...
```
