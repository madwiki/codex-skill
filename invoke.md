# invoke

Use `invoke` when you want one blocking wrapper call that drives one or more managed channels and waits for settled results.

## Accepted commands

- `sync`
- `review-this-plan`
- `review-this-work`
- `execute-this-plan`
- `execute-this-plan-part`

## Rules

- if all requests are read-only, `invoke` runs them concurrently
- if any request mutates, `invoke` runs all requests sequentially
- do not target the same channel twice in one `invoke` call
- the wrapper reply may prepend an Invoker-facing skill-usage reminder block; treat it as caller guidance, not as managed channel output

## Input

Single request:

```json
{
  "command": "review-this-plan",
  "mams_channel": "reviewer-a",
  "input": {
    "plan_for_review": "..."
  }
}
```

Multiple requests:

```json
{
  "requests": [
    {
      "command": "review-this-plan",
      "mams_channel": "reviewer-a",
      "input": {
        "plan_for_review": "..."
      }
    },
    {
      "command": "review-this-plan",
      "mams_channel": "reviewer-b",
      "input": {
        "plan_for_review": "..."
      }
    }
  ]
}
```
