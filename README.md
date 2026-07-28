# adw — spec-driven agentic development workflow

A Claude Code marketplace holding one plugin, `plugins/adw/`: a spec-driven workflow for building
strict hexagonal Python backends with coding agents.

## Status: being rebuilt

Three previous attempts are archived in git history under tags — a code generator, a YAML-manifest
pipeline, and a gate-and-hook enforcement layer. [`HISTORY.md`](HISTORY.md) says what each one was,
what it measured about itself, and how to recover any file from it.

The third attempt ended with 17 200 lines of enforcement, 0 lines of application, and 0 features
shipped. [`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md) is the survey of
what everyone else does — 14 sources, including the two Anthropic harness-design posts and a
comparison of 18 spec-driven tools — and it explains why that ratio was structural rather than
unlucky.

**What ships today:** the knowledge layer only.

```
plugins/adw/
  skills/           the house-style catalog (~8 100 lines, three rounds of audit):
                    architecture · domain-model · domain-ports · application ·
                    infra-persistence · infra-integration · restapi ·
                    testing-unit · testing-integration · python-style ·
                    conventions · meta-skill-author · meta-uc-author
  commands/         commit
```

## The direction

Living spec per capability, one delta per change in OpenSpec's `ADDED` / `MODIFIED` / `REMOVED`
format, every acceptance criterion pinned by an `@pytest.mark.ac("AC-n")` test, one check script of
at most 300 lines, a fresh-context evaluator subagent for the verdict, a branch per change, and
human review of the merge diff instead of a machine that guards against being bypassed.

The reasoning is in the research document §7; the five rules that keep it from growing back into
the previous attempt are in [`CLAUDE.md`](CLAUDE.md).

## Install

```
/plugin marketplace add wntic/agentic-development-workflow
/plugin install adw
```

Do not enable the checked-out and the installed load at the same time.
