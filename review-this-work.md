# review-this-work

Hard gate for reviewing completed execution work.

## Input

```json
{
  "work_for_review": "Submitted work report text.",
  "new_information": "Optional. Additional facts discovered after execution.",
  "fresh_user_message": "Optional. A fresh user verbatim message."
}
```

## Required reply shape

The first non-empty line must be:

- `approved_work: true`
- or `approved_work: false`

Then the reply must include:

- `## Work Review Reply`

An optional `## User Escalation Request` section may be included alongside the valid review reply.
