# request-mutation

Use this to authorize one approved mutation step on a cxsk_channel with `can_mutate: true`.

This is the only mutation permission turn.

## Input contract

```json
{
  "approved_mutation": "Describe the single approved mutation step here."
}
```

Optional:

```json
{
  "approved_mutation": "Describe the single approved mutation step here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this mutation.",
  "sandbox_mode": "full-access"
}
```

Rules:

- `approved_mutation` is required
- `sandbox_mode` may only be `default` or `full-access`
- if the selected cxsk_channel has `can_mutate: false`, the wrapper rejects this command
