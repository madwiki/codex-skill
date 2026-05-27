# work-sync

Use this in **codex-mutates** mode for every non-mutation turn.

`work-sync` is where Codex and the caller discuss the task, refine or challenge assumptions, respond to review feedback, and decide whether Codex is ready to propose a candidate plan. It is not a mutation turn.

## When to use

- After `init.md` when the task is on the codex-mutates path
- When the caller wants Codex to continue discussion or reconsider the next step
- When Codex may or may not be ready to propose a candidate plan
- When the caller has reviewed Codex's prior mutation result and wants Codex to respond before any further mutation

## Collaboration rules

- For a new shared task, or after compact/context clear, run `init.md` before `work-sync`.
- `work-sync` does not authorize mutation.
- Codex decides in this turn whether to keep discussing or to include a candidate `plan`.
- the caller cannot force plan output just by choosing this command name.
- If Codex includes a `plan`, the caller still must explicitly authorize mutation later through `request-mutation.md`.

## Input contract

Call `work-sync` with JSON on stdin.

Required:

```json
{
  "sync_message": "Write the caller's current sync message here."
}
```

Optional addition:

```json
{
  "sync_message": "Write the caller's current sync message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this sync."
}
```

Rules:

- `sync_message` is required
- `fresh_user_message` is optional
- no other top-level fields are accepted
- `sync_message` may contain task discussion, disagreement, plan feedback, or the caller's review feedback on Codex's prior mutation

## Output contract

Codex replies in markdown, not JSON.

Required section:

```md
## Discussion Reply
...
```

Optional section:

```md
## Plan
...
```

Rules:

- `## Discussion Reply` is required
- `## Plan` is optional
- if Codex is not ready to propose a plan, it must omit the `## Plan` section

## Run

```bash
<skill_root>/bin/codex-skill-work-sync < work-sync.json
```
