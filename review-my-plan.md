# review-my-plan

Use this in **Claude-mutates** mode before Claude performs meaningful state-changing work.

Claude owns mutation. Codex reviews Claude's intended plan, may do read-only investigation, and must not edit files or change project/external state in this call.

## When to use

- Before Claude starts implementation after discussion
- Before publishing a plan/design/architecture to the user
- Before ExitPlanMode when Claude will execute the work
- After requirements change enough that the old plan may be stale

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing.
- For a new shared task, or after compact/context clear, run `init.md` before plan review.
- This call is a hard gate. Claude must not mutate until Codex returns `approved_to_mutate: true`.
- Ask Codex to check requirements, assumptions, affected code, risks, and tests.
- Ask Codex to personally fact-check important claims and review whole-system coherence, not only the draft plan.
- If Claude disagrees with Codex's review, switch to `chat.md` and discuss evidence until consensus or user escalation.

## Input contract

Call `review-my-plan` with JSON on stdin.

Required:

```json
{
  "plan_for_review": "Describe Claude's intended plan here."
}
```

Optional additions:

```json
{
  "plan_for_review": "Describe Claude's intended plan here.",
  "new_information": "Only if something changed after init or after the last Codex turn.",
  "fresh_user_message": "Only if the user actually said new words that matter for this review."
}
```

Rules:

- `plan_for_review` is required
- `new_information` is optional
- `fresh_user_message` is optional
- no other top-level fields are accepted
- `plan_for_review` should include the intended change boundary, definition of done, and any known risks or uncertainties, because that is what Codex must review before Claude mutates

## Output contract

Codex must return exactly one JSON object with exactly these top-level fields:

```json
{
  "approved_to_mutate": true,
  "plan_review_reply": "..."
}
```

Meaning:

- `approved_to_mutate: true` means Claude may begin state-changing work
- `approved_to_mutate: false` means Claude must not mutate yet
- `plan_review_reply` contains Codex's reasoning, blockers, risks, disagreement, requested changes, and any minimum user decision if needed

## Run

```bash
<skill_root>/bin/codex-skill-review-my-plan < review-my-plan.json
```
