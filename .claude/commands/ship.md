---
description: Prepare a version bump for the marketplace plugins by the recorded rule — collect the shipping diff since the last bump, classify it against the movement table read from plan/INDEX.md at run time, propose; the human decides. Nothing moves without their word.
argument-hint: "[adw | run-report | empty — both]"
---

# /ship — version bump by the recorded rule, decided by the human

You are the main session of this repository. Your work here is to prepare a decision, not to make
one. The movement rule lives in `plan/INDEX.md`, section «Версия плагина — правило движения» — that
section is read **at run time, every run**, and this file carries no copy of it: a standing copy
diverges silently (the F-132 class). From `$ARGUMENTS` take the plugin — `adw`, `run-report`, or
empty meaning both; each plugin's version lives in its own
`plugins/<name>/.claude-plugin/plugin.json` and each has its own count, so run the steps per plugin.

## Steps

1. **Find the last version movement.**
   `git log -S '"version"' --oneline -- plugins/<name>/.claude-plugin/plugin.json` — the first
   commit in the list is the last time this plugin's version moved.

2. **Collect the shipping diff since then.**
   `git log --oneline <sha>..HEAD -- plugins/<name>/`. If it is empty, say "nothing to ship" for
   this plugin and stop here.

3. **Classify line by line against the table.** Open `plan/INDEX.md`, section «Версия плагина —
   правило движения», and put each diff line into one of its rows — the table is the only source
   of criteria; do not invent any of your own. The version moves by the **strongest** class found
   in the accumulated diff; edits that touch only the dev record do not count toward the bump.

4. **Propose to the human.** Current version → proposed version, with the justification laid out
   per diff line and the class of each. `AskUserQuestion` is fine here. The human may override any
   single classification and the overall result; their answer is what gets executed, not yours.
   Without their decision nothing moves.

5. **On their decision.** Edit `version` in the plugin's `plugin.json`; for `run-report` also
   add a section to its `CHANGELOG.md`, since that plugin keeps one — `adw` has no changelog and
   does not get one. Commit in English. **Push only on the human's explicit word**, asked as a
   separate confirmation: publication is an external action.

## Boundaries

- No criteria are invented — the table in `plan/INDEX.md` is the only classification source, read
  fresh each run.
- The decision is always the human's: there is no branch of this command where the version moves
  on its own.
- The version does not move "along with" a wave or a pass — only through this command, at
  publication.
