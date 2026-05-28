# work-sync

Use this for a non-mutation sync turn on a managed Codex channel.

Typical uses:

- discussion
- disagreement handling
- candidate plan formation
- response to review feedback

`work-sync` does not authorize mutation.

## Input contract

```json
{
  "sync_message": "Write the caller's current sync message here."
}
```

Optional:

```json
{
  "sync_message": "Write the caller's current sync message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this sync."
}
```
