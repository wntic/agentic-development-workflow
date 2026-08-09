# adw — spec-driven agentic development workflow

A Claude Code marketplace holding two plugins. `plugins/adw/` is a spec-driven workflow for building
strict hexagonal Python backends with coding agents — the rest of this file is about it.
`plugins/run-report/` is a separate observability tool: it renders a run's session transcripts into a
readable report of which agents ran, where the time went, what got written and what got in the way.
See [`plugins/README.md`](plugins/README.md) for how the two sit side by side.

## Status: being rebuilt

Three previous attempts are archived in git history under tags — a code generator, a YAML-manifest
pipeline, and a gate-and-hook enforcement layer. [`HISTORY.md`](HISTORY.md) says what each one was,
what it measured about itself, and how to recover any file from it.

The third attempt ended with 17 200 lines of enforcement, 0 lines of application, and 0 features
shipped. [`research/sdd-landscape-2026-07.md`](research/sdd-landscape-2026-07.md) is the survey of
what everyone else does — 14 sources, including the two Anthropic harness-design posts and a
comparison of 18 spec-driven tools — and it explains why that ratio was structural rather than
unlucky.

**What ships today:** the knowledge layer plus the change cycle — step 1 of the build order.

```
plugins/adw/
  skills/           the house-style catalog (~8 100 lines, three rounds of audit):
                    architecture · domain-model · domain-ports · application ·
                    infra-persistence · infra-integration · restapi ·
                    testing-unit · testing-integration · python-style ·
                    conventions · meta-skill-author · meta-uc-author
  agents/           the four roles: test-author · test-review · implementer · evaluator
  commands/         spec · build · accept · commit
  templates/        the artifacts the commands fill: a living spec, a delta spec,
                    a criteria checklist, a verdict — and a Makefile carrying `check`
```

No change has been run through the cycle yet: that is step 2, and it happens in a real project
before the workflow is iterated on a second time.

## The design

[`WORKFLOW.md`](WORKFLOW.md) is the canon. In one breath:

A living spec per capability that **compounds**; each change arrives as a delta in OpenSpec's
`ADDED` / `MODIFIED` / `REMOVED` + `WHEN … THEN` form and is **deleted** on acceptance, its criteria
merged into the living spec as invariants carrying the name of the test that proves them. Criteria
are observable behaviour, each pinned by an `@pytest.mark.ac("AC-n")` test, at least one of them
exercised through the really running app. Four roles, so that the red phase and the green phase each
get a verdict from an agent that did not author it: **test-author → test-review → implementer →
evaluator**. "Green" is `make check` — `ruff` + `mypy` + `pytest`, and **zero scripts of our own**.
Test tampering is caught by reading `git diff <baseline>..HEAD -- tests/`, not by a machine. One
branch per change.

Two layers, and the split decides how much is thrown away at the next platform change: the **core**
(`specs/`, skill bodies, `make check`, git conventions) is 100% portable Markdown-git-make; the
**adapter** (agent frontmatter, `commands/`, manifests) is 4–7 small Claude Code files. Hooks,
integrity checks and payload-parsing scripts are in neither — they don't port, so they aren't
written.

Seven red lines keep it from growing back into the previous attempt — `WORKFLOW.md` §9, and §8 lists
what is deliberately *not* built, with the reason for each.

## Install

```
/plugin marketplace add wntic/agentic-development-workflow
/plugin install adw
/plugin install run-report      # optional, and independent of the workflow
```

Do not enable the checked-out and the installed load at the same time.
