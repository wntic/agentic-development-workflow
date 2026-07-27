---
description: "Abandon change/<context>-NNN: record the reason in tag abandoned/<context>-NNN, then delete the change branch — its red tests never touched main (S9)"
---

# /abandon <context>/NNN

> Invoked as `/adw:abandon` when the workflow is installed as a plugin, `/abandon` when it is
> loaded from a project's own `.claude/` — as in the workflow's own repo. The two forms name
> this same file; other commands are referred to below in the `/adw:` form.

A change that will not be finished is dropped cleanly. Because one change = one branch and its
red tests, code, and verdict live only on that branch, abandoning is trivial: `main` never saw
them (S9). The only thing that must survive is **why** it was abandoned — recorded in a git
tag so the number is not silently reused and the decision is auditable.

## Procedure

1. **Resolve.** Parse `$ARGUMENTS` into `<context>/NNN`. Confirm the branch
   `change/<context>-NNN` exists (`git rev-parse --verify change/<context>-NNN`). If you are
   currently on it, switch to the mainline branch first (`main` — while v3 itself is being
   built, its work branch stands in for `main`, spec §10 / tasks/INDEX).

2. **Reason.** Ask the human for a one-line reason if `$ARGUMENTS` did not carry one (a
   superseding change, an invalidated assumption, a rethink). The reason is not optional — an
   abandon with no recorded cause is exactly the silent drift the workflow forbids.

3. **Tag the reason.** Create an annotated tag on the branch tip so the abandoned work is
   recoverable from git and the id is retired:
   ```
   git tag -a abandoned/<context>-NNN change/<context>-NNN -m "<reason>"
   ```
   The number is **not** reused — `/adw:spec` allocates `NNN = max(existing ∪ tags) + 1`, and this
   tag counts (spec §6).

4. **Delete the branch.** `git branch -D change/<context>-NNN`. The change directory
   `specs/<context>/changes/NNN-<slug>/` lived only on that branch, so it goes with it; the
   mainline is untouched. Any `baseline/<context>-NNN` tag from the red commit may be left in
   place (it points into history the `abandoned/` tag already preserves) or deleted — the
   number stays retired either way.

5. **Confirm.** Report to the human: the branch is gone, the reason is in
   `abandoned/<context>-NNN`, `main` was never touched, and the id will not be reissued.

## Notes

- Abandon is not acceptance in disguise — nothing merges. If the work was actually good, it
  should go through `/adw:accept-change`, not here.
- If a paired `Companion:` change exists, decide its fate explicitly with the human: a
  companion is accepted-together or abandoned-together, never left half-alive.
