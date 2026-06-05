# execute-this-plan

Execute one approved whole plan on a mutate-capable channel.

## Input

```json
{
  "approved_plan": "Approved plan text.",
  "fresh_user_message": "Optional. A fresh user verbatim message.",
  "sandbox_mode": "default"
}
```

`sandbox_mode` may be:

- `default`
- `full-access`

## Required reply shape

When the turn stops, the reply must include:

- `## Work Report`

An optional `## User Escalation Request` section may be included alongside the valid work report.
