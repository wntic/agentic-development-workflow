"""Standing guard for the progressive-disclosure skill format (T13's contract, built T13b).

`CONVENTIONS.md` "Skill format" states three rules that had nothing behind them — by S4's litmus
they were prose. This suite is what physically happens when an author breaks one:

1. a bundled topic file carries **no frontmatter** (frontmatter belongs to `SKILL.md` alone, or the
   catalog listing advertises a phantom skill and one theme becomes two auto-invocation entries);
2. **every** topic file is pointed at by its own `SKILL.md` (the runtime injects `SKILL.md` alone,
   so an unreferenced topic is invisible to the agent — dead knowledge);
3. every pointer **resolves** to a file that exists (a dangling pointer sends the agent to nothing).

Not `test_skill_catalog.py`: that suite is T07's paid-fixes oracle, deliberately untouched, and it
asserts content *signatures*, never format. Two suites, two questions.

**What the imperative half of rule 3 can and cannot be checked as.** The contract's sharpest rule is
"a pointer is an instruction, not a summary" — "read `endpoint.md` now", never "see also
`endpoint.md`". Its *reachability* direction is checked here and is the load-bearing one: a topic
reached only by a soft cross-reference has **no** imperative pointer, so `unpointed_topic_violations`
reds. The converse — forbidding every soft mention of a topic file anywhere in a router — is **not**
checked, because legitimate routers do exactly that: `infra-persistence`'s `ConflictError` paragraph
cites `repository.md` as the translator's home, `testing-unit`'s pyramid table names its topic files
as table cells, and its constitution cites `fake.md` mid-sentence. A rule banning those would fire on
correct documents. What stays unguarded, and is stated rather than pretended: a router that keeps an
imperative pointer *and* summarises the topic's rules underneath it (the "router that summarises"
pitfall) passes here — only a reader catches that.

Discovery is a filesystem walk, never a list (the `test_self_lint.py` precedent): a skill or topic
added later is covered the moment it lands. `vacuity_violations` is the other half of that precedent
— an empty discovery set, or a pointer regex that silently stopped matching, must not read as
success.

The checks are plain functions over a skills root so their **red** paths are pinned against
synthetic trees below, not just asserted green against the real catalog. A guard nobody proved red
is decoration.
"""

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

# The router's one sanctioned pointer form (CONVENTIONS.md "Skill format", meta-skill-author
# "Where the body lives"). Matched over whitespace-squashed text: a pointer legally wraps lines.
POINTER = re.compile(r"\*\*read `([^`]+)` now\*\*")

# Skills whose SUBJECT is the pointer syntax itself, exempt from pointer *resolution* only.
# `meta-skill-author` teaches the router shape, so it quotes the exact production form in its
# template (`a.md`, `b.md`) and in its pitfalls prose (`endpoint.md`) — illustrations that resolve
# to nothing by design and are textually indistinguishable from real pointers. The exemption is
# narrow: the frontmatter and unpointed-topic checks still cover these skills, and
# `test_the_pointer_syntax_exemption_names_a_real_skill` fails if the name goes stale.
POINTER_SYNTAX_IS_THE_SUBJECT = frozenset({"meta-skill-author"})


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def skill_dirs(root: Path) -> list[Path]:
    """Every directory under `root` that holds skill Markdown.

    `CONVENTIONS.md` sits directly in `skills/` and is the format document, not a skill, so a
    top-level file is never discovered as one.
    """
    return sorted(d for d in root.iterdir() if d.is_dir() and any(d.rglob("*.md")))


def topic_files(skill_dir: Path) -> list[str]:
    """The theme's bundled topics: every `*.md` under the skill dir except its `SKILL.md`."""
    return sorted(p.relative_to(skill_dir).as_posix() for p in skill_dir.rglob("*.md") if p.name != "SKILL.md")


def pointers(skill_md: Path) -> list[str]:
    return POINTER.findall(_squash(skill_md.read_text(encoding="utf-8")))


def frontmatter_violations(root: Path) -> list[str]:
    out: list[str] = []
    for skill in skill_dirs(root):
        for rel in topic_files(skill):
            lines = (skill / rel).read_text(encoding="utf-8").lstrip("\ufeff").splitlines()
            if lines and lines[0].strip() == "---":
                out.append(
                    f"{skill.name}/{rel} opens with a `---` frontmatter block. Frontmatter lives in "
                    f"SKILL.md alone — a `name:` here advertises a phantom skill and splits one "
                    f"theme into two auto-invocation entries. Start the topic at its `# ` title."
                )
    return out


def unpointed_topic_violations(root: Path) -> list[str]:
    out: list[str] = []
    for skill in skill_dirs(root):
        topics = topic_files(skill)
        router = skill / "SKILL.md"
        if not router.is_file():
            if topics:
                out.append(
                    f"{skill.name}/ has topic files {topics} and no SKILL.md — nothing routes to "
                    f"them, and the runtime injects SKILL.md alone, so the whole theme is invisible."
                )
            continue
        pointed = set(pointers(router))
        for rel in topics:
            if rel not in pointed:
                out.append(
                    f"{skill.name}/{rel} is not pointed at by {skill.name}/SKILL.md. Only SKILL.md "
                    f'is injected, so an unpointed topic is dead knowledge. Add "→ **read '
                    f'`{rel}` now**" — an instruction, not a "see also".'
                )
    return out


def dangling_pointer_violations(root: Path) -> list[str]:
    out: list[str] = []
    for skill in skill_dirs(root):
        if skill.name in POINTER_SYNTAX_IS_THE_SUBJECT:
            continue
        router = skill / "SKILL.md"
        if not router.is_file():
            continue
        for target in pointers(router):
            if not (skill / target).is_file():
                out.append(
                    f"{skill.name}/SKILL.md points at `{target}`, which does not exist. The pointer "
                    f"is an instruction to read the file — a dangling one sends the agent to nothing."
                )
    return out


def vacuity_violations(root: Path) -> list[str]:
    """The discovery set must be non-empty and must actually contain the shape being guarded."""
    out: list[str] = []
    skills = skill_dirs(root)
    if not skills:
        out.append(f"no skill directories discovered under {root} — the walk broke; nothing is guarded")
        return out
    if not any(topic_files(s) for s in skills):
        out.append(
            "no skill bundles topic files, so the router rules pin an empty set. Either the catalog "
            "has no multi-topic theme (then this guard is inoperative) or discovery broke."
        )
    found = sum(len(pointers(s / "SKILL.md")) for s in skills if (s / "SKILL.md").is_file())
    if not found:
        out.append(
            f"the pointer pattern {POINTER.pattern!r} matched nothing in the whole catalog — "
            f"the router form changed or the regex broke, and the resolution check now passes "
            f"vacuously over an empty pointer list."
        )
    return out


# --- the real catalog ----------------------------------------------------------------------


def test_no_topic_file_carries_frontmatter() -> None:
    assert frontmatter_violations(SKILLS_DIR) == []


def test_every_topic_file_is_pointed_at_by_its_router() -> None:
    assert unpointed_topic_violations(SKILLS_DIR) == []


def test_every_router_pointer_resolves() -> None:
    assert dangling_pointer_violations(SKILLS_DIR) == []


def test_the_guard_is_not_vacuous() -> None:
    assert vacuity_violations(SKILLS_DIR) == []


def test_the_pointer_syntax_exemption_names_a_real_skill() -> None:
    """A stale exemption is a hole nobody sees; a renamed skill must fail here, not go unchecked."""
    for name in POINTER_SYNTAX_IS_THE_SUBJECT:
        assert (SKILLS_DIR / name / "SKILL.md").is_file(), (
            f"{name} is exempt from pointer resolution but no longer exists — drop the exemption or "
            f"fix the name, or its successor is silently unguarded"
        )


# --- the red paths, against synthetic trees --------------------------------------------------


def _valid_theme(root: Path) -> Path:
    """A minimal conforming router + topic — the control for every planted break below."""
    skill = root / "theme"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: theme\ndescription: x\nwhen_to_use: y\n---\n"
        "# Theme\n\n## When to use vs. neighbours\n\n"
        "- Writing a foo → **read `foo.md`\n  now**.\n",  # deliberately wrapped: pointers do wrap
        encoding="utf-8",
    )
    (skill / "foo.md").write_text("# Foo\n\nbody\n", encoding="utf-8")
    return skill


def _all_violations(root: Path) -> list[str]:
    return (
        frontmatter_violations(root)
        + unpointed_topic_violations(root)
        + dangling_pointer_violations(root)
        + vacuity_violations(root)
    )


def test_the_control_theme_is_clean(tmp_path: Path) -> None:
    _valid_theme(tmp_path)
    assert _all_violations(tmp_path) == []


def test_frontmatter_in_a_topic_file_reds(tmp_path: Path) -> None:
    skill = _valid_theme(tmp_path)
    (skill / "foo.md").write_text("---\nname: foo\n---\n# Foo\n", encoding="utf-8")
    assert frontmatter_violations(tmp_path)
    assert unpointed_topic_violations(tmp_path) == []
    assert dangling_pointer_violations(tmp_path) == []


def test_an_unreferenced_topic_file_reds(tmp_path: Path) -> None:
    skill = _valid_theme(tmp_path)
    (skill / "bar.md").write_text("# Bar\n", encoding="utf-8")
    violations = unpointed_topic_violations(tmp_path)
    assert violations and "bar.md" in violations[0]
    assert frontmatter_violations(tmp_path) == []
    assert dangling_pointer_violations(tmp_path) == []


def test_a_soft_cross_reference_does_not_count_as_a_pointer(tmp_path: Path) -> None:
    """The imperative half, in the direction that is checkable: "see also" leaves the topic unread."""
    skill = _valid_theme(tmp_path)
    (skill / "SKILL.md").write_text(
        "---\nname: theme\n---\n# Theme\n\n- Writing a foo — see also `foo.md` for detail.\n",
        encoding="utf-8",
    )
    assert unpointed_topic_violations(tmp_path)


def test_a_pointer_to_a_nonexistent_file_reds(tmp_path: Path) -> None:
    skill = _valid_theme(tmp_path)
    with (skill / "SKILL.md").open("a", encoding="utf-8") as fh:
        fh.write("- Writing a ghost → **read `ghost.md` now**.\n")
    violations = dangling_pointer_violations(tmp_path)
    assert violations and "ghost.md" in violations[0]
    assert frontmatter_violations(tmp_path) == []
    assert unpointed_topic_violations(tmp_path) == []


def test_topic_files_with_no_router_at_all_red(tmp_path: Path) -> None:
    skill = _valid_theme(tmp_path)
    (skill / "SKILL.md").unlink()
    violations = unpointed_topic_violations(tmp_path)
    assert violations and "no SKILL.md" in violations[0]


def test_an_empty_discovery_set_reds_the_non_vacuity_guard(tmp_path: Path) -> None:
    assert vacuity_violations(tmp_path)
    # ...and so does a catalog of single-topic skills only, where the router rules pin nothing.
    single = tmp_path / "solo"
    single.mkdir()
    (single / "SKILL.md").write_text("---\nname: solo\n---\n# Solo\n", encoding="utf-8")
    assert vacuity_violations(tmp_path)


def test_a_broken_pointer_pattern_reds_the_non_vacuity_guard(tmp_path: Path) -> None:
    """If the router form drifts, resolution would pass over an empty list — that must be loud."""
    skill = _valid_theme(tmp_path)
    (skill / "SKILL.md").write_text(
        "---\nname: theme\n---\n# Theme\n\n- Writing a foo → consult foo.md.\n", encoding="utf-8"
    )
    assert any("matched nothing" in v for v in vacuity_violations(tmp_path))
