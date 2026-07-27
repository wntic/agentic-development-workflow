# T18 — Once installed, almost nothing protects the plugin's own files

## Goal
The S8 trust model says: hooks are ergonomics, **trust is the post-hoc check against the git
baseline**. In a consumer project with the plugin installed, that check very nearly does not exist.

Measured (T16 finding F-02, sharpened by T15's probes):

- The plugin lives outside the consumer repo (`~/.claude/plugins/cache/…`, or wherever
  `--plugin-dir` points). `bash_guard` anchors to the **consumer's** root, so a write to the
  plugin's own `tools/`, `hooks/` or `plugin.json` resolves *outside* the root and is **allowed** —
  by absolute path and through a symlink alike.
- `gate.py`'s `integrity.protected-trees` diffs `.claude/tools` / `.claude/hooks` /
  `.claude/settings.json` **inside the consumer tree**, where they do not exist, so it passes
  **vacuously**. Of the protected set, only `pyproject.toml` is genuinely covered in a consumer.
- What remains is `check_self_hash`, and it covers **`gate.py` + `criteria_lint.py` only**.

So `accept.py`, `red_check.py`, all four hooks, and **`plugin.json` itself** are unprotected.
`plugin.json` is the sharpest of those: it names the components, so tampering with it silently
unhooks everything — and nothing would notice.

This is not a packaging defect (T15's layout is right, and its whole-repo-source rule is what keeps
`check_self_hash` alive at all). It is an unanswered **trust-model question**: *which files are
integrity anchors, and what does the gate do when it cannot vouch for one?*

## Depends on
T15 (the layout and distribution shape must be settled first — this task is about what the shipped
artifact protects, and "shipped artifact" has to exist), T04 (`gate.py`'s integrity block), T04e /
T06h (the `escalate-intact` check and the ESCALATE lock, which is the other half of the same
question).

## Read first
- `notes/20_consumer_trial_venue.md` finding F-02, and T15's escalation report (D5) — the measurement.
- `.claude/tools/gate.py` — `SELF_INTEGRITY_FILES`, `check_self_hash` (note it resolves the git
  toplevel of the directory `gate.py` lives in, which is why it survives both this repo and a split
  plugin repo), and `PROTECTED_PATHS` / `check_protected_trees`.
- `.claude/hooks/bash_guard.py` — `_repo_root()` and `_repo_relative()`: why an out-of-repo target
  never fires (T06e, deliberately).
- `PRINCIPLES.md` S8 and A3's second half ("the verification verifies the integrity of its own
  inputs"), `workflow_v3_spec.md §5.1`.

## Deliverables
Design-sensitive; the shape is the deliverable, not a patch. Answer these three, then implement:

1. **Which files are anchors?** The candidate set is everything a consumer's trust rests on:
   `gate.py`, `criteria_lint.py` (already), `accept.py`, `red_check.py`, the four hooks, and
   `plugin.json`. Adding all of them to `SELF_INTEGRITY_FILES` is the obvious move — state the cost
   (every edit to any of them in this repo must be committed before a gate run passes; that is
   already true of `gate.py` and has been mildly annoying, see T06j finding 6).
2. **What happens when the plugin is not a git repository at all?** T15's rule (whole-repo source)
   keeps `.git` present, but `--plugin-dir` at an arbitrary path, a vendored copy, or a future
   install mode may not. `check_self_hash` currently FAILs in that case — which is the right
   direction, but it means the gate is unusable rather than degraded. Decide: hard FAIL (trust
   requires provenance), or a loud, recorded degradation. **Prefer FAIL** unless there is a concrete
   legitimate mode it breaks — a silently degraded trust anchor is the `notes/19` fail-open class.
3. **Does anything protect the hooks at all in a consumer?** They are ergonomics under S8, so a
   tampered hook should be *survivable* — but only if the gate still catches what the hook would
   have prevented. Walk each hook and say what backstops it: `criteria_guard` → `integrity.criteria-flips`;
   `bash_guard` → the protected-tree diff (**but see above: vacuous in a consumer**);
   `subagent_stop` → nothing obvious; `session_stop` → ?. Where the answer is "nothing", that is a
   finding worth more than the fix.
- Tests for whatever lands, plus a case that a tampered anchor FAILs with a message naming the file.

## Verification
- `uv run pytest .claude/tools` green.
- Each new anchor demonstrably FAILs the gate when its work-tree content differs from HEAD, with the
  file named — and PASSes untouched.
- **In a consumer**: install the plugin per T15's rule into T16's venue, tamper with one newly
  anchored file, and confirm the gate goes RED there. This is the case the whole task exists for; a
  test that only passes in the workflow's own repo does not discharge it.
- The workflow's own repo still gates GREEN with a clean tree.

## Out of scope / Escalate if
- Do NOT try to make `bash_guard` protect the plugin's own directory. It is anchored to the project
  root on purpose (T06e), and re-widening it would resurrect the false-positive family T06i is about.
  The answer here is post-hoc integrity, not prevention — that *is* S8.
- Do NOT fold in the ESCALATE lock (T06h). Same family, separate decision, and T06h is larger.
- **Escalate if** answering (1) means anchoring a file that legitimately changes during a cycle. That
  would mean the anchor set and the cycle's write lanes disagree, which is a canon question about
  ownership (D4), not an integrity detail.
