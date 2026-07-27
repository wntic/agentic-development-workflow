"""Machine inventory of the skill catalog's paid-for fixes (workflow v3, T07 / WP4a).

This suite is the catalog's GUARD, built BEFORE the thing it guards changes (V-07:
"the fox guarding the henhouse" otherwise). Every closed F/N finding from the dry-run remediation
(`notes/14_dryrun_fix_plan.md`) and the named minimum of the spec's skill-revision step
(§7, item 3) is asserted to still exist SOMEWHERE in the catalog by its CONTENT signature —
a distinctive phrase, never a file path. That is what lets the T08 merge (44 skills → ~13)
move and combine files freely: as long as the paid knowledge is carried over verbatim, this
suite stays green without a single edit. A phrase that vanishes reds the corresponding test
and names the finding it lost.

How to extend it when a new paid lesson lands: add one `test_<fnid>_*` function that greps
(via `_present`) for the distinctive phrase of the fix, and cite the F/N id in the test name.
One entry per closed finding. Never assert on a file path.

KNOWN WEAKNESS OF THE CORPUS (recorded by T13b, deliberately not fixed — see below).
`_load_catalog`'s `rglob("*.md")` is what makes bundled `<topic>.md` files covered for free after
the T14 split, and that is the property T13/T14 rest on. The same `rglob` also pulls in
`.claude/skills/CONVENTIONS.md` — the catalog's **format document**, not a skill. So a paid-for
needle could in principle be satisfied by a sentence in the format doc while the knowledge is
absent from every skill body, and this suite would still pass. Measured 2026-07-27: of the 51
needles, five (`conftest`, `re-raise`, `grandparent`, `sqlalchemy core`, `never the orm`) also occur
in CONVENTIONS.md, and **none** is satisfied by it alone, so nothing is currently propped up by the
format doc. Re-run that measurement before trusting a green run after a CONVENTIONS.md rewrite.
Left as documentation rather than an exclusion because this file's value is that nobody edits it:
the T08 merge and the T14 split both passed it without a single assertion change, and an exclusion
list is a second thing to keep true. The format rules themselves are guarded elsewhere, by
`test_skill_format.py`.
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _load_catalog() -> str:
    """Concatenate every Markdown file under `.claude/skills/`, lowercased.

    Path-agnostic on purpose: the assertions ask only whether the knowledge exists somewhere
    in the catalog, so they survive the T08 file merges unchanged.
    """
    parts: list[str] = []
    for md in sorted(SKILLS_DIR.rglob("*.md")):
        parts.append(md.read_text(encoding="utf-8"))
    text = "\n".join(parts)
    assert text.strip(), f"no skill Markdown found under {SKILLS_DIR}"
    return text.lower()


_CATALOG = _load_catalog()


def _present(*needles: str) -> None:
    """Assert every needle (case-insensitive substring) appears somewhere in the catalog."""
    missing = [n for n in needles if n.lower() not in _CATALOG]
    assert not missing, f"paid-for signature(s) lost from the catalog: {missing!r}"


# --- F-series: dry-run gate-integrity + skill/doc fixes (notes/14 P1/P2) --------------------


def test_f013_root_conftest_never_imports_create_app() -> None:
    # A root tests/conftest.py that imports create_app makes every unit collection pay the
    # whole infra import chain; a domain-VO red→green is then blocked by an unfilled sibling.
    _present("conftest", "must not import", "create_app")


def test_f015_failure_state_transition_then_reraise_is_sanctioned() -> None:
    # The second sanctioned try/except: record status=FAILED then re-raise (not the only
    # sanctioned one is compensating-tx).
    _present("failure-state transition", "re-raise")


def test_f016_best_effort_undo_is_optional_two_shapes() -> None:
    # The compensating-tx undo may be a dedicated *_best_effort method OR the plain protocol
    # method wrapped in a call-site swallow — the architect's choice, not an assumed method.
    _present("best_effort", "sanctioned shapes")


def test_f018_fake_stores_and_returns_copies_with_updated_log() -> None:
    # A fake that aliases the caller's entity lets a mutate-but-never-persist body pass green;
    # the fake stores/returns copies and records an `updated` call log.
    _present("copies", "updated", "mutate-but-never-persist")


def test_f019_concrete_service_dep_is_subclassed_not_type_ignored() -> None:
    # A handler dep typed as a concrete domain service can't be structurally faked; subclass
    # it or inject via a Protocol — never # type: ignore / Mock.
    _present("concrete domain service", "faked structurally", "subclass")


def test_f004_workspace_id_tenant_stamped_from_current_user() -> None:
    # Auth-derived fields beyond caller_id (workspace_id/tenant_id) stamp from CurrentUser,
    # never from the request body/path.
    _present("workspace_id", "currentuser", "stamped")


def test_f023_ban_inline_type_ignore_on_content_modules() -> None:
    # The pyproject [[tool.mypy.overrides]] block is the only sanctioned missing-stub silence;
    # an inline # type: ignore on a content module is banned.
    _present("inline `# type: ignore`", "content module")


# --- N-series: post-PR findings surfaced driving a fresh scaffold to green ------------------


def test_n01_import_from_immediate_parent_not_grandparent() -> None:
    # A name two `from .subpkg import *` hops deep is not statically resolvable (computed
    # __all__); import from the package that DIRECTLY contains the defining module.
    _present("directly contains", "grandparent", "attr-defined")


def test_n02_getattr_on_fastapi_route_internals() -> None:
    # Discovery tests reach FastAPI route internals via getattr (version-robust across the
    # 0.137 change) and guard route.methods (typed set[str] | None).
    _present("getattr(route", "route.methods or set()")


def test_n03_ban_from_future_import_annotations() -> None:
    # from __future__ import annotations breaks runtime annotation introspection (Pydantic,
    # dependency-injector, dataclass __post_init__); banned project-wide.
    _present("prohibition on `from __future__ import annotations`")
    _present("no `from __future__ import annotations`")


def test_n04_env_prefix_stems_on_product_not_bounded_context() -> None:
    # env_prefix is an app/product namespace, never a bounded-context/epic name — shared
    # substrate collapses across contexts, so a context-named prefix is incoherent.
    _present("application / product", "bounded context", "epic")


# --- §9 residual: assert-strength recipes (7) ----------------------------------------------


def test_assert_strength_seven_recipes_present() -> None:
    # Each recipe keeps a manual-stub / handler assert strong at authoring time; a wrong body
    # must FAIL it. All seven distilled from real weak asserts the adversarial pass caught.
    _present(
        "pin persisted state",  # 1 — persisted state via updated log + read-back
        "survivor present",  # 2 — drop/skip with a survivor, never empty
        "non-boundary case",  # 3 — exercise a non-boundary tier/value
        "distinguish `total`",  # 4 — total vs len(items) with page < matches
        "prove scoping or a join",  # 5 — ≥2 rows to prove scoping/joins
        "echoed / derived field",  # 6 — non-constant value for an echoed field
        "assert no side effect",  # 7 — guard/reject path asserts no write
    )


# --- Two-sub-template idioms (C6 altitude: feature-conditional, not frozen) -----------------


def test_two_sub_template_auth_optional() -> None:
    # Auth is a contingent feature: templates show both the authenticated form and the
    # auth-free form, gated on whether the app declares auth — never frozen as universal.
    _present("when the app declares auth", "declares no auth")


def test_two_sub_template_relational_optional() -> None:
    # A relational store is contingent: the relational substrate (postgres container, engine,
    # sf) is emitted only for relational apps / a bootstrap store.
    _present("relational apps", "bootstrap store")


# --- Standing bans / disciplined exceptions ------------------------------------------------


def test_ban_orm_use_sqlalchemy_core_only() -> None:
    _present("sqlalchemy core", "never the orm")


def test_pagination_pick_one_never_both() -> None:
    # NOTE (finding): the spec §7 / task lists "cursor-pagination" among the bans, but the
    # catalog does NOT ban cursor pagination — it is a sanctioned alternative to limit/offset.
    # The load-bearing paid rule is mutual exclusivity: pick one, never both.
    _present("pick one", "never both", "cursor")


def test_b8_no_versions_in_substrate_floors_are_the_lone_exception() -> None:
    # No baked-in version pins in the substrate (uv.lock is the only home); a requires_packages
    # >= floor is the lone disciplined exception, only at a known breaking-version boundary.
    _present("no versions in the substrate")
    _present("requires_packages", "breaking-version boundary")


def test_b006_ruff_flags_mutable_default_argument() -> None:
    _present("b006", "mutable default argument")


def test_b904_raise_from_cause_inside_except() -> None:
    _present("b904", "from exc")
