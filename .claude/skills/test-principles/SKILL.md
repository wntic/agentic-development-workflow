---
name: test-principles
description: Reference skill that owns the catalog's paid-fixes guard — the machine inventory (`.claude/tools/test_skill_catalog.py`) that greps the whole skill catalog for every hard-won lesson by its content signature, so a later reword, split, or merge cannot silently drop one. Documents the guard, the families of lesson it inventories, and the append-only protocol for extending it. The testing constitution itself (the pyramid, the conftest hierarchy, the fixture-vs-builder rule, the no-mocks contract, per-layer speed targets) now lives in `testing-unit` and `testing-integration`; this skill is the guard, not the constitution.
when_to_use: Moving, merging, or rewording a hard-won lesson anywhere in the catalog (the guard must still find its phrase afterwards), or adding a newly closed lesson to the paid-fixes inventory. Not consulted to write a test file — reach for `testing-unit` or `testing-integration`.
---

# Test — Principles (the catalog's paid-fixes guard)

This skill owns one thing: the **catalog's own guard**, a machine inventory of every hard-won lesson so no reorganisation of the knowledge base can quietly lose one. The testing constitution it used to also carry — the pyramid, the conftest hierarchy, fixture-vs-builder, the no-mocks contract, per-layer speed targets — now lives with the tiers it governs, in `testing-unit` and `testing-integration`.

## When to use vs. neighbours

- Writing or modifying a test → `testing-unit` (fast, no-IO) or `testing-integration` (real backends). This skill produces no test file.
- A hard-won lesson (a phrase distilled from a real defect) is being moved, merged, or reworded across the catalog → the paid-fixes guard below must still find it afterwards; that is what this skill protects.
- Adding a newly closed lesson to the inventory → follow the extension protocol below.

## The catalog's paid-fixes guard

The knowledge base is a living document: skills get reworded, split, and merged. Every such move risks silently dropping a lesson that was expensive to learn — a defect surfaced once, its fix distilled into a distinctive sentence, and that sentence must never evaporate in an edit. Prose review ("I copied it all over, trust me") is not enough; the transfer is checked by a machine.

**The guard is `.claude/tools/test_skill_catalog.py`** — a pytest suite that, for each closed lesson, greps the *whole* catalog for the lesson's **content signature** (a distinctive phrase or code pattern), never its file path. Because the check is path-agnostic, a lesson may live in any skill and move to any other; the guard stays green as long as the phrase is carried over verbatim. If a phrase disappears, the matching test reds and names the lesson that was lost.

The families of lesson it inventories today (one test each, the test name citing the lesson's id) — described here as categories only, deliberately **without** quoting the grep phrases, so the exact signatures live in exactly one place, the skills that own the knowledge, and this summary can never satisfy the guard by accident:

- **Persistence & handler correctness** — the conftest-import discipline, the sanctioned failure-state exception path, the compensating-undo shapes, the copy-and-log fake behaviour, the concrete-service substitution rule, and auth-derived field stamping.
- **Type & import fragility** — the re-export-hop import rule, the version-robust route-internals access, the future-annotations ban, and the settings-prefix altitude.
- **Assert strength** — the seven recipes that keep a handler/manual-stub assert strong at authoring time.
- **Feature-conditional templates** — the auth-optional and relational-optional two-sub-template idioms (a contingent feature is never frozen as universal).
- **Standing bans & disciplined exceptions** — the Core-only rule, the single-pagination-shape rule, the substrate version-pin discipline, the inline type-suppression ban, and the two enabled bugbear lint rules.

**How to extend it when a new paid lesson lands.** Every time a defect is closed and its fix distilled into the catalog, add **one** test to `test_skill_catalog.py`:

1. Pick the most distinctive phrase or code pattern the fix introduced — one a plausibly-wrong rewrite would not accidentally reproduce.
2. Write `test_<id>_<slug>` that asserts that phrase (and any co-load-bearing phrase) is present somewhere in the catalog, via the suite's `_present(...)` helper. Cite the lesson's id in the test name.
3. Never assert on a file path, and never weaken an existing signature to make room — one entry per closed lesson, append-only.

The guard is deliberately rewritten **before** any large catalog reorganisation, not during it: the watcher must not be re-authored by the same hand, in the same pass, that moves what it watches.

## Hard stops

- You are about to reword or merge a skill and a paid-for phrase would change → stop; either keep the phrase verbatim or, if the lesson genuinely changed, update its guard test in the same commit (never weaken it silently).
- You reach for this skill to write a test → stop, it produces no test file; use `testing-unit` or `testing-integration`.
- You want to satisfy the guard by quoting a signature here in the summary → stop; the signatures live in the knowledge-owning skills, never in this overview.
