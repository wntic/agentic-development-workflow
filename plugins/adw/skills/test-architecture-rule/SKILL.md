---
name: test-architecture-rule
description: Apply when extending `tests/unit/test_architecture.py` with a new grep-firewall rule — a "thou shalt not import X in layer Y" invariant the codebase needs enforced automatically. Produces one new `def test_no_<thing>` (or `test_<layer>_has_no_<thing>`) function using the standard `_grep(pattern, *paths)` shape, with an optional in-test allow-list for legitimate exceptions. Does not produce runtime tests (use `test-domain-entity` / `test-domain-value-object` / `test-domain-enum` / `test-domain-service` / `test-repository-contract` / `test-restapi-endpoint`), type-correctness rules (use `mypy` / `pyright`), or style rules (use `ruff`).
---

# Test — Architectural Firewall Rule

`tests/unit/test_architecture.py` is a static grep firewall. Each function greps the source tree for a forbidden pattern and asserts the result is empty. Adding a rule here is cheaper than catching the same mistake repeatedly in code review.

## When to use vs. neighbours

- A static, absolute "do not import X in layer Y" invariant the codebase needs enforced → this skill.
- A runtime unit/integration test for entity / VO / enum / service / repository / endpoint behavior → the matching `test-*` skill. Greps enforce static structure; runtime tests enforce dynamic behavior.
- A type-correctness rule → `mypy` / `pyright` enforce it; do not duplicate as a grep test.
- A style / formatting rule → `ruff` enforces it; do not duplicate.
- A "should usually" rule with material exceptions → not a firewall candidate; document in a layer skill instead. Firewalls are absolutes that accumulate exceptions and stop paying for themselves.
- An intent-based rule ("don't use `Any` *unless* at a true external boundary") → not a firewall candidate; greps either hit or don't, with no intent inspection.

## Template(s)

Only `tests/unit/test_architecture.py` is touched. `_grep(...)` and the `_ROOT` / `_SRC` / `_TESTS` / `_DOMAIN` / `_APP` constants already exist at the top of the file.

### Standard rule (no allow-list)

```python
def test_no_<rule_name>() -> None:
    hits = _grep("<pattern>", <paths>)
    assert hits == [], "<message>:\n" + "\n".join(hits)
```

Concrete:

```python
def test_domain_has_no_sqlalchemy() -> None:
    hits = _grep(r"import sqlalchemy\|from sqlalchemy", _DOMAIN)
    assert hits == [], "sqlalchemy import in domain:\n" + "\n".join(hits)
```

### Rule with in-test allow-list

```python
def test_no_print_calls_outside_allowed() -> None:
    _main_py = str(_ROOT / "src" / "myapp" / "restapi" / "main.py")
    _cli = str(_ROOT / "src" / "myapp" / "cli")
    all_hits = _grep("print(", _SRC)
    forbidden = [h for h in all_hits if not h.startswith(_main_py) and not h.startswith(_cli)]
    assert forbidden == [], "print() calls found outside allowed locations:\n" + "\n".join(forbidden)
```

The pattern stays simple ("no `print(`"); exceptions are explicit and visible to a future maintainer.

### Adding a new path constant (when a new scope is needed)

Append at the top of the file, next to the existing constants:

```python
_RESTAPI = str(_ROOT / "src" / "myapp" / "restapi")
_INFRA   = str(_ROOT / "src" / "myapp" / "infrastructure")
```

## Rules

1. **One `def test_*` per rule.** No fixtures, no parametrization, no async. The test name **is** the rule, and the names form the file's spec.
2. **Naming convention.** Layer-scoped → `test_<layer>_has_no_<thing>` (e.g. `test_domain_has_no_pydantic`). Repo-wide → `test_no_<thing>` (e.g. `test_no_future_annotations_anywhere`). Don't pluralize; don't add qualifiers.
3. **The `assert hits == []` form is deliberate.** When the test fails, pytest prints `[]` alongside the actual list, and the message lists every offending location — a clean diff.
4. **Use the path constants; don't inline literal paths.** `_SRC`, `_TESTS`, `_DOMAIN`, `_APP` exist at the top of the file. Add a new constant alongside them for a new scope (e.g. `_RESTAPI`). Inlined paths drift if the tree moves.
5. **Pattern syntax.** Plain string for unique tokens (`"Optional["`, `"time.sleep"`); alternation with escaped `\|` for equivalent forms (`r"import sqlalchemy\|from sqlalchemy"`); `\b` to avoid substring false matches (`r"Mapped\b"`). Use raw strings (`r"..."`) whenever the pattern contains a backslash.
6. **Test the pattern locally before committing.** Run `grep -rn --include='*.py' --exclude=test_architecture.py 'your pattern' src/ tests/` and confirm zero unexpected hits. Never ship a test that's already red — fix the hits or narrow the pattern first.
7. **Allow-list lives inside the test, not in the pattern.** Filter the `_grep` result with `startswith(...)` checks against the named exception paths. Cap the allow-list at **three entries**. Beyond three, the rule has too many exceptions to be a firewall; demote it to a layer skill's prose or split it into a more specific rule.
8. **`_grep` excludes `test_architecture.py` itself.** The `--exclude=test_architecture.py` argument inside `_grep` prevents the file from finding its own pattern strings.

## Inlined typing / import rules

- `subprocess` and `pathlib.Path` only at the file level (already present).
- Never import from `myapp` — importing what you're trying to forbid defeats the firewall.
- Tests are sync `def test_*() -> None`.

## Hard stops

- Pattern produces unintended hits in the current tree → stop, fix them first or narrow the pattern.
- Rule depends on intent or runtime state → stop, this isn't a grep-firewall rule.
- Allow-list would need more than three entries → stop, the rule is too leaky; restructure or demote it.
- Spec adds a fixture, parametrization, or async to the test → stop, one `def test_*` per rule; "no X in domain" across multiple `X` values means one test per `X`.
- Spec adds `try/except` around `_grep` or conditional skips → stop, that breaks the unconditional property of the firewall.
- Spec imports anything from `myapp` → stop, importing the thing you forbid defeats the firewall.
- Spec inlines a literal path inside a test → stop, use the `_<NAME>` constants at module top; add a new constant if a new scope is needed.
