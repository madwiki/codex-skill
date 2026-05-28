# invoke

Use `invoke` as the preferred wrapper command when the cxsk_invoker wants one blocking call that drives one or more cxsk_channels and waits for settled results.

## When to use it

- one long `sync`
- one long `review-this-plan`
- one long `review-this-work`
- fanout to multiple reviewers or planners without external polling
- a single execution call when you still want the same blocking wrapper entrypoint

## Why use it

- the wrapper blocks once and waits internally
- read-only fanout can run concurrently
- mutating requests still run through the same wrapper entrypoint
- the cxsk_invoker does not need to poll for status
- the wrapper watches process health while waiting

## Input

`invoke` reads JSON from stdin.

Single request:

```json
{
  "command": "review-this-plan",
  "cxsk_channel": "reviewer-a",
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
      "cxsk_channel": "reviewer-a",
      "input": {
        "plan_for_review": "..."
      }
    },
    {
      "command": "review-this-plan",
      "cxsk_channel": "reviewer-b",
      "input": {
        "plan_for_review": "..."
      }
    }
  ]
}
```

## Rules

- `invoke` accepts:
  - `init`
  - `sync`
  - `review-this-plan`
  - `review-this-work`
  - `execute-this-plan`
  - `execute-this-plan-part`
- if all requests are read-only, `invoke` fans them out concurrently
- if any request is mutating, `invoke` runs the requests sequentially
- do not target the same `cxsk_channel` twice in one `invoke` call

## Usage

```bash
bin/codex-skill-invoke --cwd <repo> <<'JSON'
{
  "requests": [
    {
      "command": "sync",
      "cxsk_channel": "planner",
      "input": {
        "sync_message": "..."
      }
    },
    {
      "command": "review-this-plan",
      "cxsk_channel": "reviewer-a",
      "input": {
        "plan_for_review": "..."
      }
    }
  ]
}
JSON
```
