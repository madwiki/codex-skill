# review-my-work

Use this in **Claude-mutates** mode after Claude has performed state-changing work and before Claude says done or performs commit/PR/merge/release/deploy.

Claude owns mutation. Codex reviews Claude's work, may do read-only investigation, and must not edit files or change project/external state in this call.

## When to use

- Before claiming the task is complete
- Before commit, PR, merge, release, deploy, or other delivery step
- After a risky implementation step where an independent review is useful
- When Claude's self-check found uncertainty or weak evidence

## Collaboration rules

- Run the persistence bootstrap in `SKILL.md` first: verify durable memory/`CLAUDE.md` contains the reload + init + subtask-guide rule, and add it if missing.
- For a new shared task, or after compact/context clear, run `init.md` before work review.
- This call is a hard gate. Claude must not treat the work as accepted until Codex returns `approved_work: true`.
- Include enough evidence for Codex to review independently: changed files, test results, known risks, and unresolved assumptions.
- Ask Codex to read/search/inspect when needed and to look for holes rather than rubber-stamp the result.
- Ask Codex to personally fact-check important claims and review whole-system coherence across affected code, tests, docs, prompts, memory, and artifacts.
- If Claude disagrees with Codex's findings, switch to `chat.md` and discuss evidence until consensus or user escalation.

## Input contract

Call `review-my-work` with JSON on stdin.

Required:

```json
{
  "work_for_review": "Describe Claude's actual work, validation, and remaining concerns here."
}
```

Optional additions:

```json
{
  "work_for_review": "Describe Claude's actual work, validation, and remaining concerns here.",
  "new_information": "Only if something changed after the work was done or after the last Codex turn.",
  "fresh_user_message": "Only if the user actually said new words that matter for this review."
}
```

Rules:

- `work_for_review` is required
- `new_information` is optional
- `fresh_user_message` is optional
- no other top-level fields are accepted
- `work_for_review` should include what Claude changed, what was verified, any known deviations from the earlier approved plan, and any remaining risks or uncertainty

## Output contract

Codex replies in markdown, not JSON.

The first non-empty line must be:

```md
approved_work: true
```

or:

```md
approved_work: false
```

Then Codex must include this required section:

```md
## Work Review Reply
...
```

Meaning:

- `approved_work: true` means Claude may treat the reviewed work as accepted
- `approved_work: false` means Claude must not treat the work as accepted yet
- `## Work Review Reply` contains Codex's reasoning, blockers, risks, disagreement, requested fixes, and any minimum user decision if needed

## Run

```bash
<skill_root>/bin/codex-skill-review-my-work < review-my-work.json
```
