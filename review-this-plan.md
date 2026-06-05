# review-this-plan

Hard gate before execution begins.

## Input

```json
{
  "plan_for_review": "Submitted plan text.",
  "new_information": "Optional. Additional facts discovered after the plan was drafted.",
  "fresh_user_message": "Optional. A fresh user verbatim message."
}
```

## Required reply shape

The first non-empty line must be:

- `approved_to_mutate: true`
- or `approved_to_mutate: false`

Then the reply must include:

- `## Plan Review Reply`

An optional `## User Escalation Request` section may be included alongside the valid review reply.
