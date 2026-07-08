---
description: Cut a release — bump version, roll CHANGELOG from commits, commit, tag, and push
argument-hint: "[patch|minor|major|auto] [--dry-run] [--no-push]"
allowed-tools: Bash(bash scripts/release.sh:*), Bash(git status:*), Bash(git log:*)
---

Run the release automation, forwarding any arguments verbatim:

```
bash scripts/release.sh $ARGUMENTS
```

Rules:
- If no bump argument is given, default to a **patch** release.
- The script generates the new CHANGELOG section from Conventional-Commit messages
  since the last tag, bumps `VERSION` + `frontend/package.json`, commits
  `chore(release): vX.Y.Z`, creates an annotated tag `vX.Y.Z`, and pushes it.
- For a real (non `--dry-run`) release, first run `git status --short` and confirm the
  working tree is what the user expects — a release commit includes any pending changes.
- After it runs, report the new version, the tag, and whether the push succeeded.
