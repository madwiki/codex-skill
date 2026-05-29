# review-this-plan

Use this to review a submitted plan before any execution begins.

This is a hard gate. The mams_invoker must not treat discussion as approval.

## Input contract

```json
{
  "plan_for_review": "Describe the intended plan here."
}
```

Optional:

```json
{
  "plan_for_review": "Describe the intended plan here.",
  "new_information": "Only if something changed after init or the last managed-channel turn.",
  "fresh_user_message": "Only if the user actually said new words that matter for this review."
}
```

## Output contract

The first non-empty line must be:

```md
approved_to_mutate: true
```

or:

```md
approved_to_mutate: false
```

Then the targeted managed channel must include:

```md
## Plan Review Reply
...
```
