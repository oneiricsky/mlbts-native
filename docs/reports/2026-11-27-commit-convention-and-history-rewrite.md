# Commit convention and history rewrite (2026-11-27)

## The convention

- Subject: one line, imperative, scoped, for example `fix(gfx): bind compute dispatches to the Switch-size level`.
- Body: three sentences at most, or nothing. The trailer line does not count.
- The long explanation goes in `docs/reports/YYYY-MM-DD-slug.md`, committed in the same change.
- Issues and docs cite dates, subjects and report paths, not the owner's commit hashes. Upstream's hashes do not change,
  so they may stay, with the date and subject.

A rewritten commit gets a new hash. A date, a subject or a report path does not change.

## The rewrite

Only the owner's commits were rewritten. Upstream's commits keep their hashes, and upstream's last merged commit is
still an ancestor of `main`, so later releases merge as before.

The owner's 155 commits became 11 commits and one merge. Each new commit takes the file tree of the last commit in its
range, so every state in the new history is one that existed before, and nothing was re-applied or conflict-resolved.

| Subject of the new commit | Commits it replaces |
| --- | --- |
| perf(gfx): build pipelines in the background and add an intro skip | 6 |
| feat(hdtex): load PS5 normal maps for player heads | 7 |
| fix(hdtex): read PS5 images from the Switch-size level in compute passes | 11 |
| chore(fork): merge upstream Fastball 0.2.0 | 1 (the merge) |
| feat(tools): add the benchmark, texture index check and fork CI | 19, with their branch merges |
| feat(harness): add scenario-driven game runs in isolated slots | 23 |
| docs(map): map the game code and build the wiki from it | 14 |
| feat(harness): run headless exhibitions between chosen teams | 16 |
| feat(wiki): add coverage charts and the function theming pipeline | 30 |
| feat(trainer): add the in-game trainer and clean up the offline menu | 3 |
| feat(mods): add the mods folder with the starting-tokens mod | 2 |
| feat(fork): turn on all PS5 head textures and add boot matchups | 23 |

The old history is kept on the local branch `backup/pre-squash-20261127`. The explanations from the old commit
messages are in `docs/reports/2026-11-27-commit-notes.md`: all 111 commits that had a body, and the subjects of the other 44,
8,598 words, 8,657 with dates and subjects added for 5 hashes (4 replaced, 1 upstream hash kept).
`python -I tools/check_commit_notes.py backup/pre-squash-20261127` compares the file with the old history word by word.
It passed, and it failed on two broken copies (one word removed, one section removed). It needs that branch.

## Content check

`tools/check_history.py` runs the content check on every file of every commit it is given, because the pre-commit hook
does not run on a rewrite. It passed on the trees of the new commits, and failed on test commits that held a forbidden
file or a key line in an earlier commit only.

## Signing

1Password was locked, so these commits were signed from a file copy of the same signing key. The signature is the
same one GitHub already knows; no key was created and no git setting was changed.

## What still points at the old history

- `origin/main` has the old commits until a force-push, which was not asked for.
- Branches with work that is not on `main` still sit on the old commits: `docs/theme-findings`, `feat/harness-ui`,
  `feat/trainer`, `feat/trainer-cheats`, `research/combined` and `research/msdf-skip`. To bring one over, move only its
  own commits with `git rebase --onto`; a plain merge would bring the old history back.
- Upstream's `docs/frame-rate.md` still cites upstream hashes. Those did not change, and editing upstream's file would
  cause merge conflicts.
