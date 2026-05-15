# review

Legacy alias for `review-my-work.md`.

Use this only when older instructions or habits say `review`. It means **Claude-mutates** mode: Claude owned the state-changing work, and Codex reviews Claude's work before delivery without mutating state.

For the current workflow, read `review-my-work.md` and run:

```bash
<skill_root>/bin/codex-skill-review-my-work < message.txt
```

Compatibility command:

```bash
<skill_root>/bin/codex-skill-review < message.txt
```
