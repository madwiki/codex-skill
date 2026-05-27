# review-my-plan

Use this in **caller-mutates** mode before the caller performs meaningful state-changing work.

The caller owns mutation. Codex reviews the caller's intended plan, may do read-only investigation, and must not edit files or change project/external state in this call.

## When to use

- Before the caller starts implementation after discussion
- Before publishing a plan/design/architecture to the user
- Before ExitPlanMode when the caller will execute the work
- After requirements change enough that the old plan may be stale

## Collaboration rules

- For a new shared task, or after compact/context clear, run `init.md` before plan review.
- This call is a hard gate. The caller must not mutate until Codex returns `approved_to_mutate: true`.
- Ask Codex to check requirements, assumptions, affected code, risks, and tests.
- Ask Codex to personally fact-check important claims and review whole-system coherence, not only the draft plan.
- If the caller disagrees with Codex's review, switch to `chat.md` and discuss evidence until consensus or user escalation.

## Input contract

Call `review-my-plan` with JSON on stdin.

Required:

```json
{
  "plan_for_review": "Describe the caller's intended plan here."
}
```

Optional additions:

```json
{
  "plan_for_review": "Describe the caller's intended plan here.",
  "new_information": "Only if something changed after init or after the last Codex turn.",
  "fresh_user_message": "Only if the user actually said new words that matter for this review."
}
```

Rules:

- `plan_for_review` is required
- `new_information` is optional
- `fresh_user_message` is optional
- no other top-level fields are accepted
- `plan_for_review` should include the intended change boundary, definition of done, and any known risks or uncertainties, because that is what Codex must review before caller mutates

## Output contract

Codex replies in markdown, not JSON.

The first non-empty line must be:

```md
approved_to_mutate: true
```

or:

```md
approved_to_mutate: false
```

Then Codex must include this required section:

```md
## Plan Review Reply
...
```

Meaning:

- `approved_to_mutate: true` means the caller may begin state-changing work
- `approved_to_mutate: false` means the caller must not mutate yet
- `## Plan Review Reply` contains Codex's reasoning, blockers, risks, disagreement, requested changes, and any minimum user decision if needed

## Run

```bash
<skill_root>/bin/codex-skill-review-my-plan < review-my-plan.json
```
