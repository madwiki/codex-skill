# init

Use this as the collaboration bootstrap entrypoint.

Claude should call `init` in two cases:

- a new shared task is starting and Claude wants to brief Codex on the task background
- Claude has just returned from compact or context clear and wants Codex to help recover the working context

`init` is not a mutation step and not a discussion turn. It exists to give Codex the collaboration protocol plus either the new-task background or the tentative recovery background.

## Input contract

Call `init` with JSON on stdin. The JSON must contain exactly one top-level field.

New task:

```json
{
  "task_background": "Summarize the new task background for Codex here."
}
```

Recovery:

```json
{
  "recovery_background": "Summarize Claude's tentative recovered background here."
}
```

Rules:

- `task_background` and `recovery_background` are mutually exclusive
- one of them is required
- `init` privately injects the Codex collaboration protocol; Claude does not need to restate it in the input payload
- after `init`, Claude resumes the appropriate path:
  - `chat.md` / `review-my-plan.md` / `review-my-work.md` for Claude-mutates
  - `work-sync.md` / `request-mutation.md` for Codex-mutates

## Output contract

If the input used `task_background`, Codex must return:

```json
{
  "task_understanding_reply": "..."
}
```

That reply should tell Claude what Codex understands about the task, what risks or disagreements stand out, what collaboration path seems more appropriate if that is already apparent, and what Claude should know before continuing.

If the input used `recovery_background`, Codex must return:

```json
{
  "context_recovery_reply": "..."
}
```

That reply should tell Claude what Codex can recover, what remains uncertain, and where the workflow should resume, including which path or command seems appropriate next if Codex can tell.

If Codex does not have trustworthy prior context to add, it should say so plainly instead of pretending recovery happened.

## Run

```bash
<skill_root>/bin/codex-skill-init < init.json
```
