---
name: logical-commits
description: >-
  Split current work into a trail of small, coherent git commits.
  Use only when the user explicitly asks to create logical commits or
  invokes the logical commit skill.
disable-model-invocation: true
---

# Logical commits

When this skill is invoked, turn the current uncommitted work into a sequence of logical commits. Do not push.

## What counts as one commit

Each commit is one coherent unit of work — something you can describe in one short message (e.g. "add user model", "wire login route to session", "add tests for login validation"). A multi-step feature usually becomes several commits; how many depends on the work, not a fixed count.

Prefer commits that leave the repo in a sensible state (tests passing for what that commit adds). Avoid half-wired broken middles unless you truly cannot avoid them. Prefer coherent chunks over both mega-commits and meaningless one-line typo commits.

## Commit messages

Write complete sentences: a short subject stating what changed and why it matters (focus on "why" over "what").

## How to run

1. Inspect the full working tree (`git status`, `git diff`, recent `git log` for message style).
2. Group the changes into logical units. Stage and commit one unit at a time.
3. After each commit, confirm the message matches that unit only.
4. Stop when the working tree is clean (or only unrelated leftover files remain). Report the commits you created. Never push unless the user explicitly asks.
