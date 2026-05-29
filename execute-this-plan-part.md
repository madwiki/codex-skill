# execute-this-plan-part

Use this to authorize one approved plan part on a mams_channel with `can_mutate: true`.

Use this only when the full plan is genuinely too large for one execution turn.

## Input contract

```json
{
  "approved_plan_part": "Describe the approved plan part here."
}
```

Optional:

```json
{
  "approved_plan_part": "Describe the approved plan part here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this execution.",
  "sandbox_mode": "full-access"
}
```

Rules:

- `approved_plan_part` is required
- `sandbox_mode` may only be `default` or `full-access`
- if the selected mams_channel has `can_mutate: false`, the wrapper rejects this command
- a plan part must still be a substantial coherent chunk, not a tiny fragment
- do not stop for incidental small edits
- stop only when the approved plan part is complete or a real blocker prevents safe continuation
