---
description: "Accept change/<context>-NNN into the base branch: run accept.py's gates, hunt corpus contradictions, get the human's eyes on the merge diff + every [m], then accept.py --execute (merge, tag, delete the change dir) and relay the drift check"
---

# /accept-change <context>/NNN

The human-facing acceptance flow (spec §6). The deterministic core is **`accept.py`** — every
gate that can be a script IS one; this command adds only the parts a script cannot do: the LLM
contradiction hunt, the human's review of the merge diff, and the explicit human confirmation
of each `[m]` and of any multi-file invariant placement (spec §5.4, the 5.4.5b split). You do
**not** restate accept.py's gates as prose or re-judge them (S4/S8) — you run the script and
relay its verdict; where a gate is not the script's, this command says whose it is.

Trust is `accept.py` re-running `gate.py` against the git baseline, not what any prior agent
reported (S8). You never hand-edit `src/**`, `tests/**`, or the canonical capability files —
writing invariants into the spec is `accept.py`'s job alone (§5.4), and `main` receives only the
green merge it performs (S9).

## 0. Orient

Parse `$ARGUMENTS` into `<context>/NNN`. Confirm the change branch `change/<context>-NNN` exists
and carries `specs/<context>/changes/NNN-<slug>/` with `change.md`, `criteria.md`, `verdict.md`.
If the change is not yet through `/implement` (no `verdict.md`), stop and say so.

## 1. Run the gates (accept.py, check mode)

```
uv run .claude/tools/accept.py <context>/NNN
```

This runs the deterministic §5.4 preconditions and prints the prepared merge diff without
touching anything: criteria complete + junit-backed, `gate.py` GREEN re-run on the branch,
verdict freshness, Companion, Affects-intersection, merge-fidelity, spec-lint, orphan sweep
(removal), and the adversarial-pass presence check (spec §6 step 4). **Read its output; do not
re-derive any of these yourself.**

- **Any `[FAIL]` / `verdict: DENIED`** → stop here. Relay the failing gate(s) verbatim to the
  human; acceptance cannot proceed until `/implement` (or the human) resolves them. A present
  `ESCALATE` file only the human removes.
- **`verdict: ACCEPTABLE`** → carry the printed merge diff and every `[FLAG]` line
  (Affects-intersection, spec-lint, merge.placement, a SKIPPED Docker tier) forward into the
  review material below — flags never block, but the human decides on them.

## 2. Contradiction hunt (the LLM slice of §5.4 gate 5)

`accept.py`'s spec-lint covers the mechanical half of gate 5 (dangling refs, duplicates,
oversize, unlisted capabilities). The corpus-contradiction half needs a reader — that is you.

Read the prepared merge diff and the affected context's spec files (`specs/<context>/overview.md`
and the capability files the change touches — the affected context only, not the whole corpus).
List every existing corpus statement the delta would contradict, as:

- **(file · quoted statement · why it conflicts)**

An **empty list is a valid, expected result** — most changes contradict nothing. Append the list
(empty or not) to the review material for step 5; do not resolve conflicts yourself.

## 3. Enumerate every `[m]` for explicit human confirmation

`criteria_guard` cannot tell a human from an agent, so nothing structurally stops an evaluator
agent from self-certifying an `[m]` and writing its own justification into `verdict.md`
(`gate.py`/`accept.py` only check that the entry *exists*). The human-in-the-loop check lives
**here**: for **each** `[m]` criterion in `criteria.md`, surface the criterion text **and** its
`verdict.md` justification, and ask the human to confirm each one explicitly — do not bury them
in the diff. No `[m]` reaches the base branch without the human having eyeballed it. If there are
no `[m]` criteria, say so and move on.

## 4. Multi-target invariant placement (only when accept.py flags it)

If step 1 printed a `merge.placement` `[FLAG]` (a multi-target `Affects`), invariant distribution
is a semantic act, not a deterministic one (spec §5.4): `accept.py` refuses to place a multi-target
merge until this command hands it an approved map, and it will never dump every invariant into the
first `Affects` file. Propose, for each proven criterion, which capability file its invariant
belongs in (read the criteria against the target files), and present the mapping to the human to
approve or edit. Single-target is fully deterministic — `accept.py` places it and this command just
relays; do nothing here.

Record the human-approved mapping as a JSON object keyed by AC-id — the exact **placement map**
you will pass to `--execute` in step 6:

```
{"AC-1": "<capability-a>.md", "AC-2": "<capability-b>.md"}
```

Every proven criterion must map to one of the files on the change's `Affects` line (a map naming a
file outside `Affects` is refused by `accept.py`). Distributing one change's invariants across its
`Affects` files is this map; splitting the work itself into *separate changes* is instead the
`/spec` re-cut path (§2.1) — keep the two distinct, and never hand-edit capability files here (the
spec-write owners are `accept.py` and `/spec` only).

## 5. Human review of the merge

Present to the human, together: the prepared merge diff (criteria → capability invariants), the
contradiction-hunt list from step 2, every `[FLAG]` from step 1 (Affects-intersection, spec-lint,
placement, a SKIPPED Docker tier — accepting a skipped tier is a conscious call, T04b), and the
confirmed `[m]` set from step 3. Ask for explicit approval to merge. On anything short of a clear
yes, stop — nothing is written.

## 6. Execute (accept.py) and relay the drift check

On the human's approval:

```
uv run .claude/tools/accept.py <context>/NNN --execute
```

For a **multi-target** change, pass the human-approved placement map from step 4 so `accept.py`
writes each invariant to its file (without it, a multi-target `--execute` is refused):

```
uv run .claude/tools/accept.py <context>/NNN --execute --placement '{"AC-1": "<capability-a>.md", "AC-2": "<capability-b>.md"}'
```

`accept.py` re-checks that no gate FAILs, writes the invariants into the capability files with
provenance (single-target deterministically, multi-target per the approved map), merges the branch
into the base, tags `change/<context>-NNN`, deletes the change dir,
and prints the §5.5 drift check. **Relay that drift report to the human verbatim** — src commits
on the base not tied to a `change/*` tag are the signal of an unlegalised hotfix (§5.5); the
OpenAPI route⊆operation half surfaces via `/orient`. Confirm to the human: merged, tagged, change
dir gone.

For an abandoned change instead of an accepted one, that is `/abandon <context>/NNN`, not this
command.
