"""Guard: the enforcement layer holds ITSELF to the gate's pinned selection (T04g).

THE SCOPE DECISION, said plainly: every `*.py` under `.claude/` is linted with `gate.py`'s own
`RUFF_SELECT` / `ruff_common()` / `ruff format --check` — the exact invocation `check_ruff` runs
over a consumer's `src/` and `tests/`. **No carve-out.** The full selection was measured against
the whole tooling tree and it passes; a workflow that imposes a standard on its consumers' code
while exempting its own tooling is the A4 shape (the check does not exercise its own subject).

Why this is a test and not `pyproject.toml`'s `[tool.ruff.lint] select`: pre-commit reads static
TOML, which cannot *cite* `RUFF_SELECT` — it could only copy it, and a copied selection is exactly
the C7 drift that produced this task. Two configs disagreeing is how `RUF103`/`RUF100` sat in
`gate.py` itself (the gate's own file) until T04f, and how `RUF059` — **ruff naming a discarded
git return code**, the `notes/19` defect class an entire audit dispatch was spent enumerating —
sat unread in `accept.py`. So the selection keeps one home and this test is its second reader.
`pyproject.toml`'s narrower `[tool.ruff]` (no `select`, i.e. ruff's default `E4,E7,E9,F`) stays as
the fast pre-commit pass; this test is the one that decides.

Discovery is a `rglob`, deliberately (T18's reasoning for the anchor globs): a tool or hook added
later is covered the moment it lands, not when someone remembers to extend a list. The one
consequence to know: a deliberately lint-dirty specimen must live **inline in a test** (as
`red_check`'s lint-dirty conftest fixture does), never as a `.py` file on disk under `.claude/`.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
CLAUDE_DIR = TOOLS_DIR.parent
REPO_ROOT = CLAUDE_DIR.parent


def _load_gate():
    spec = importlib.util.spec_from_file_location("gate_for_self_lint", TOOLS_DIR / "gate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


_GATE = _load_gate()


def _targets() -> list[str]:
    """Every `*.py` the enforcement layer ships, discovered — never enumerated.

    Non-vacuity matters more here than anywhere: `ruff check` with an EMPTY path list falls back
    to the current directory, so a broken glob would not fail loud, it would silently lint
    something else and pass. The undetermined-input rule (notes/19) applied to this guard itself.
    """
    files = sorted(CLAUDE_DIR.rglob("*.py"))
    assert files, f"no .py files discovered under {CLAUDE_DIR} — the glob broke, the layer is unlinted"
    assert TOOLS_DIR / "gate.py" in files, "gate.py itself is missing from the discovered set"
    return [str(p) for p in files]


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ruff", *args], capture_output=True, text=True)


def test_the_enforcement_layer_passes_the_gates_own_ruff_selection() -> None:
    common = _GATE.ruff_common(REPO_ROOT)
    result = _ruff("check", *common, "--no-cache", "--select", _GATE.RUFF_SELECT, *_targets())
    assert result.returncode == 0, (
        f"the workflow's own tooling fails the selection it imposes on the app it builds "
        f"({_GATE.RUFF_SELECT}). Fix the finding — do not narrow the selection (it is the app's "
        f"contract) and do not add a `noqa` for a rule that is not in it (that is a RUF100 of its "
        f"own):\n{result.stdout}\n{result.stderr}"
    )


def test_the_enforcement_layer_is_ruff_format_canonical() -> None:
    common = _GATE.ruff_common(REPO_ROOT)
    result = _ruff("format", "--check", *common, *_targets())
    assert result.returncode == 0, (
        f"the workflow's own tooling is not `ruff format`-canonical under the gate's pinned "
        f"line-length/target — the second half of what `check_ruff` demands of a consumer:\n"
        f"{result.stdout}\n{result.stderr}"
    )
