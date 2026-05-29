# execute-this-plan

Use this to authorize one approved plan on a mams_channel with `can_mutate: true`.

Use this when the approved plan is reasonably sized and should be executed as one substantial unit. Do not use plan-part mode unless the full plan is genuinely too large for one execution turn.

## Input contract

```json
{
  "approved_plan": "Describe the approved plan here."
}
```

Optional:

```json
{
  "approved_plan": "Describe the approved plan here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this execution.",
  "sandbox_mode": "full-access"
}
```

Rules:

- `approved_plan` is required
- `sandbox_mode` may only be `default` or `full-access`
- if the selected mams_channel has `can_mutate: false`, the wrapper rejects this command
- do not stop for trivial progress or incidental tiny edits
- finish the approved plan unless a real blocker prevents safe continuation
