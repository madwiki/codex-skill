# chat

Use this as the general discussion command.

Use it for:

- routine progress sync
- requirements discussion
- disagreements
- stuck or unclear states
- preparing the smallest useful user-facing decision when consensus is not reachable

`chat` is discussion only. It does not authorize mutation.

## Input contract

```json
{
  "message_for_codex": "Write the caller's discussion message here."
}
```

Optional:

```json
{
  "message_for_codex": "Write the caller's discussion message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this discussion."
}
```
