# review-my-work

Use this after state-changing work has happened and before the caller treats that work as accepted or delivered.

This is a hard gate.

`approved_work: true` accepts the reviewed step only. If more agreed steps remain, continue to the next step instead of stopping.

## Input contract

```json
{
  "work_for_review": "Describe the actual work, validation, and remaining concerns here."
}
```

Optional:

```json
{
  "work_for_review": "Describe the actual work, validation, and remaining concerns here.",
  "new_information": "Only if something changed after the work was done or after the last Codex turn.",
  "fresh_user_message": "Only if the user actually said new words that matter for this review."
}
```
