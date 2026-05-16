# init

Use this as the collaboration bootstrap entrypoint.

Claude should call `init` in two cases:

- a new shared task is starting and Claude wants to brief Codex on the task background
- Claude has just returned from compact or context clear and wants Codex to help recover the working context

`init` is not a mutation step and not a discussion turn. It exists to give Codex the collaboration protocol plus either the new-task background or the tentative recovery background.

## Input contract

Call `init` with JSON on stdin. The JSON must contain exactly one background field plus `mutation_owner`.

New task:

```json
{
  "task_background": "Summarize the new task background for Codex here.",
  "mutation_owner": "claude"
}
```

Recovery:

```json
{
  "recovery_background": "Summarize Claude's tentative recovered background here.",
  "mutation_owner": "codex"
}
```

Rules:

- `task_background` and `recovery_background` are mutually exclusive
- one of them is required
- `mutation_owner` is required and must be exactly `claude` or `codex`
- `init` privately injects the Codex collaboration protocol plus the role-specific path framing for the chosen mutation owner; Claude does not need to restate that in the input payload
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

That reply should tell Claude what Codex understands about the task, what risks or disagreements stand out, whether the chosen mutation-owner path looks problematic, and what Claude should know before continuing.

If the input used `recovery_background`, Codex must return:

```json
{
  "context_recovery_reply": "..."
}
```

That reply should tell Claude what Codex can recover, what remains uncertain, and where the workflow should resume on the chosen mutation-owner path, including which command seems appropriate next if Codex can tell.

If Codex does not have trustworthy prior context to add, it should say so plainly instead of pretending recovery happened.

## Run

```bash
<skill_root>/bin/codex-skill-init < init.json
```
