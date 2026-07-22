"""Tests for criteria_lint.py (workflow v3, spec §3.3)."""

from pathlib import Path

import criteria_lint as cl

SPEC_EXAMPLE = """\
# Criteria — meetings/003-upload-recording
- [ ] AC-1: POST /meetings with a valid audio file returns 201 and the meeting id
- [ ] AC-2: exceeding the plan's monthly quota returns 402 with code quota_exceeded
- [x] AC-3: on a DB write failure the uploaded blob is deleted (compensation), response 5xx
- [m] AC-4: a file >25 MiB is rejected with 413 before the body is read in full
"""


def _lint(text: str) -> list[cl.Finding]:
    return cl.lint_lines(text.splitlines(), path="criteria.md")


def _reasons(text: str) -> str:
    return "\n".join(f.reason for f in _lint(text))


# --- observable criteria pass ------------------------------------------------


def test_spec_example_passes() -> None:
    assert _lint(SPEC_EXAMPLE) == []


def test_observable_artifact_variants_pass() -> None:
    for text in [
        "- [ ] AC-1: GET /billing/plan for an authorized user returns their plan and limits",
        "- [ ] AC-1: after a repeat call the status stays DONE",
        "- [ ] AC-1: the response carries a `meeting_id` field",
        "- [ ] AC-1: the error carries code quota_exceeded",
        "- [ ] AC-1: on a DB failure the response is 5xx",
    ]:
        assert _lint(text) == [], text


# --- states parse ([ ] / [x] / [m]), grammar is strict -----------------------


def test_all_three_states_parse() -> None:
    criteria = cl.iter_criteria(SPEC_EXAMPLE.splitlines())
    assert [(c.ac_id, c.state) for c in criteria] == [
        ("AC-1", " "),
        ("AC-2", " "),
        ("AC-3", "x"),
        ("AC-4", "m"),
    ]


def test_unknown_state_is_malformed() -> None:
    reasons = _reasons("- [y] AC-1: POST /a returns 200")
    assert "malformed criteria line" in reasons


def test_indented_or_sloppy_checkbox_is_malformed() -> None:
    assert "malformed criteria line" in _reasons("  - [ ] AC-1: POST /a returns 200")
    assert "malformed criteria line" in _reasons("- [X] AC-1: POST /a returns 200")


# --- vague markers are rejected ----------------------------------------------


def test_vague_english_rejected() -> None:
    reasons = _reasons("- [ ] AC-1: the endpoint works correctly and returns data as expected")
    assert '"works"' in reasons
    assert '"correctly"' in reasons
    assert '"as expected"' in reasons


def test_vague_marker_rejected_even_with_observable_token() -> None:
    reasons = _reasons("- [ ] AC-1: POST /meetings returns 201 and works correctly")
    assert '"works"' in reasons
    assert '"correctly"' in reasons


def test_negated_and_embedded_forms_are_not_flagged() -> None:
    # "incorrect password" describes an input, not a verdict — `\bcorrect\b` must NOT fire
    # inside "incorrect", so a criterion about rejecting a bad password stays clean.
    assert _lint("- [ ] AC-1: an incorrect password is rejected with 401") == []


# --- criteria without an observable artifact are rejected --------------------


def test_no_observable_artifact_rejected() -> None:
    reasons = _reasons("- [ ] AC-1: the user sees a clear error message")
    assert "names no observable artifact" in reasons


# --- empty inventory is rejected ----------------------------------------------


def test_empty_file_rejected() -> None:
    assert "no acceptance criteria found" in _reasons("")


def test_header_only_file_rejected() -> None:
    assert "no acceptance criteria found" in _reasons("# Criteria — meetings/004\n\nprose, no checklist\n")


# --- duplicates and comments ---------------------------------------------------


def test_duplicate_ac_id_rejected() -> None:
    text = "- [ ] AC-1: POST /a returns 200\n- [ ] AC-1: DELETE /a returns 204"
    assert "duplicate id AC-1" in _reasons(text)


def test_html_comments_are_ignored() -> None:
    template = Path(__file__).resolve().parents[1] / "templates" / "criteria.md"
    lines = cl._strip_html_comments(template.read_text(encoding="utf-8").splitlines())
    # the commented example line inside the template must not parse as a criterion
    assert all("AC-n" not in c.text for c in cl.iter_criteria(lines))


# --- CLI ------------------------------------------------------------------------


def test_cli_green_file_exits_zero(tmp_path, capsys) -> None:
    f = tmp_path / "criteria.md"
    f.write_text(SPEC_EXAMPLE, encoding="utf-8")
    assert cl.main([str(f)]) == 0
    out = capsys.readouterr().out
    assert "OK:" in out
    assert "4 criteria" in out


def test_cli_vague_file_exits_nonzero_with_line_numbers(tmp_path, capsys) -> None:
    f = tmp_path / "criteria.md"
    f.write_text("# Criteria — x/001\n- [ ] AC-1: it all works correctly\n", encoding="utf-8")
    assert cl.main([str(f)]) == 1
    out = capsys.readouterr().out
    assert f"{f}:2:" in out


def test_cli_missing_file_exits_two(tmp_path, capsys) -> None:
    assert cl.main([str(tmp_path / "absent.md")]) == 2


def test_cli_no_args_exits_two() -> None:
    assert cl.main([]) == 2
