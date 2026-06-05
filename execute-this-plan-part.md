# execute-this-plan-part

Execute one approved plan part on a mutate-capable channel.

Use this only when the full plan is genuinely too large for one execution turn. The approved part must still be substantial.

## Input

```json
{
  "approved_plan_part": "Approved plan part text.",
  "fresh_user_message": "Optional. A fresh user verbatim message.",
  "sandbox_mode": "default"
}
```

## Required reply shape

When the turn stops, the reply must include:

- `## Work Report`

An optional `## User Escalation Request` section may be included alongside the valid work report.
