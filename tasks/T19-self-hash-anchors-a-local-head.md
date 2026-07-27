# T19 — `check_self_hash` compares against a HEAD the agent can rewrite

## Goal
T18 anchored the whole enforcement layer: 12 files (`tools/*.py`, `hooks/*.py`, `hooks/*.json`,
`bin/*.py`, `.claude-plugin/*.json`, `settings.json`) must match git HEAD or the gate goes RED. That
closed the vacuous-protection hole. It also made the remaining one **strictly larger**, and T18 said
so plainly (its finding 2):

> Self-hash compares against the plugin's **local `HEAD`**. An agent that can write the plugin
> directory — which `bash_guard` allows, by design (T06e: targets outside the anchored project root
> never fire) — can also `git -C <plugin> commit -a`, after which work tree == HEAD and the check
> passes.

So the trust anchor is "the tree matches a commit **the same actor could have made**". Under S8 the
gate is supposed to be what a bypassed hook cannot defeat; here the gate's own integrity input is
writable by the thing it judges.

**Read the honest framing before planning work:** this may not be *fixable* in the sense the other
tasks were. It has always been true — in the workflow's own repo an agent with git access can commit
over `gate.py` too — and closing it properly means comparing against something the local actor cannot
author: a published commit (network), a signed manifest (key management), or a checksum pinned outside
the plugin. Each of those buys real assurance and costs real machinery. **A written, precise statement
of the limit is a legitimate outcome of this task**; an unbounded architecture is not.

## Depends on
T18 (the anchor set — this is its stated residue), T15 (the distribution shape, which is where a
published-commit comparison would hook in), T04.

## Read first
- `.claude/tools/gate.py` — `check_self_hash`, `self_integrity_anchors`, `plugin_root()`,
  `SELF_INTEGRITY_GLOBS` / `SELF_INTEGRITY_SKIP`, and the fail-closed floor. Note it already fails
  closed on a non-git plugin and on an unanswerable git call.
- `notes/20_consumer_trial_venue.md` F-02 — the answered question and the two limits recorded under it.
- `notes/21_plugin_packaging.md` §5 — the release procedure, i.e. where a published reference exists
  at all (`git subtree split` → whole-repo marketplace source; `claude plugin tag` cuts
  `{name}--v{version}`).
- `PRINCIPLES.md` S8 and A3's second clause ("the verification verifies the integrity of its own
  inputs") — this task is exactly that clause applied to the verifier itself.
- `notes/19_accept_gate_audit.md` — the fail-open class, for the direction rule: an unanswerable
  comparison must FAIL, never PASS.

## Deliverables
Pick one and justify it; do **not** build more than one.

- **(a) State the limit and stop.** Add it to `notes/20` F-02 and to `gate.py`'s `check_self_hash`
  docstring in the same voice the other limits are recorded in, and say what it would take to close.
  Cheapest, honest, and leaves the reader able to reason about their own threat model. Recommended
  unless (b) turns out cheap.
- **(b) Compare against the release tag when one exists.** `claude plugin tag` cuts
  `{name}--v{version}`; if such a tag resolves in the plugin repo *and* is an ancestor of HEAD, verify
  the anchors against **the tag**, not HEAD. An agent can still commit, but it cannot make its commit
  the tagged release without also moving a tag (visible, and one more deliberate act). Offline, no
  keys, no network — likely a small diff. Degrade **loudly** to today's HEAD comparison when no tag
  exists (a dev checkout), never silently.
- **(c) An external checksum.** A manifest of anchor digests kept outside the plugin (consumer's repo,
  or the marketplace entry). Real assurance, real machinery, and a new file nobody owns. Only if (a)
  and (b) are both judged insufficient — and then **escalate first**, because it adds a concept.

Whichever lands: keep every T18 property — the glob-derived anchor set, the fail-closed floor, both
git calls failing closed, and a non-git plugin FAILing with the remedy named.

## Verification
- `uv run pytest .claude/tools` green.
- Under (a): no behaviour change, so the deliverable is the text — but re-run the suite to prove that.
- Under (b): the tampered-then-committed sequence that passes today must **FAIL** — that is the whole
  point. Demonstrate it: split the plugin, tag it, tamper an anchor, `git commit -a` in the plugin,
  run the gate from the consumer → RED. Today that sequence is GREEN.
- Under (b): a dev checkout with no release tag still gates GREEN, with the degradation stated in the
  check's message.
- The workflow's own repo gates GREEN on a clean tree, and T18's consumer procedure
  (`notes/20` F-02 / the T18 report) still behaves as recorded.

## Out of scope / Escalate if
- Do NOT add a network call. A gate that needs the internet to say "green" is a worse property than
  the one being fixed.
- Do NOT widen `bash_guard` to protect the plugin directory. It is anchored to the project root on
  purpose (T06e), and re-widening it revives the false-positive family T06i measured twelve members of.
- Do NOT touch the anchor set itself — T18 settled it.
- **Escalate if** (b)'s tag comparison would make a legitimate dev or `--plugin-dir` workflow RED. The
  workflow's own repo *is* such a checkout, and a fix that reddens it every day will simply be turned
  off — which is worse than the documented limit.
