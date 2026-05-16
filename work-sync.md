# work-sync

Use this in **Codex-mutates** mode for every non-mutation turn.

`work-sync` is where Codex and Claude discuss the task, refine or challenge assumptions, respond to review feedback, and decide whether Codex is ready to propose a candidate plan. It is not a mutation turn.

## When to use

- After `init.md` when the task is on the Codex-mutates path
- When Claude wants Codex to continue discussion or reconsider the next step
- When Codex may or may not be ready to propose a candidate plan
- When Claude has reviewed Codex's prior mutation result and wants Codex to respond before any further mutation

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing.
- For a new shared task, or after compact/context clear, run `init.md` before `work-sync`.
- `work-sync` does not authorize mutation.
- Codex decides in this turn whether to keep discussing or to include a candidate `plan`.
- Claude cannot force plan output just by choosing this command name.
- If Codex includes a `plan`, Claude still must explicitly authorize mutation later through `request-mutation.md`.

## Input contract

Call `work-sync` with JSON on stdin.

Required:

```json
{
  "sync_message": "Write Claude's current sync message here."
}
```

Optional addition:

```json
{
  "sync_message": "Write Claude's current sync message here.",
  "fresh_user_message": "Only if the user actually said new words that matter for this sync."
}
```

Rules:

- `sync_message` is required
- `fresh_user_message` is optional
- no other top-level fields are accepted
- `sync_message` may contain task discussion, disagreement, plan feedback, or Claude's review feedback on Codex's prior mutation

## Output contract

Codex must return JSON with:

```json
{
  "discussion_reply": "..."
}
```

Optional:

```json
{
  "discussion_reply": "...",
  "plan": "..."
}
```

Rules:

- `discussion_reply` is required
- `plan` is optional
- if Codex is not ready to propose a plan, it must omit `plan`

## Run

```bash
<skill_root>/bin/codex-skill-work-sync < work-sync.json
```
