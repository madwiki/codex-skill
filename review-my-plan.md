# review-my-plan

Use this before any approved mutation step begins.

This is a hard gate. The caller must not treat discussion as approval.

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
  "new_information": "Only if something changed after init or the last Codex turn.",
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

Then Codex must include:

```md
## Plan Review Reply
...
```
