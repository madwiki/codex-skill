# review-this-work

Use this after execution work has happened and before the cxsk_invoker treats that work as accepted or delivered.

This is a hard gate.

`approved_work: true` accepts the reviewed execution scope only. If more agreed plan scope remains, continue instead of stopping.

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
