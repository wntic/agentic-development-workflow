#!/usr/bin/env python3
"""anchors.py — write (or check) the anchor digest the gate falls back to when there is no git.

`integrity.self-hash` (E-02) verifies the enforcement layer against git HEAD of the repository
the workflow lives in. An INSTALLED plugin is a content copy of `plugins/adw/` with no `.git`
above it, so there is nothing to verify against — and the workflow refuses to be laid out around
that fact (making the install a whole-repo clone once forced the plugin's assets into a root
shared with the marketplace). `.claude-plugin/anchors.json` is the second anchor: the sha256 of
every anchored file, written at release, checked when git is absent.

Its strength, stated so nobody over-reads it: it catches an edited tool or hook — the agent that
patched the checker instead of the code, the hand-fix to an installed copy. It does NOT stop
someone who also updates the digest, exactly as the git anchor does not stop someone who also
commits (`notes/20` F-02). The digest simply needs no `.git`.

WHAT is anchored is not decided here: `gate.py`'s `anchor_digest()` is the single source, so the
writer and the verifier cannot disagree (C7).

    adw.py anchors            # check: is the committed digest current? (exit 1 if not)
    adw.py anchors --write    # rewrite it — the release step
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate  # the tools directory is put on sys.path just above

DESCRIBE = "anchors.py: writes/checks .claude-plugin/anchors.json, the gate's anchor digest for git-less installs."


def render(root: Path) -> str:
    payload = {"schema": gate.ANCHOR_DIGEST_SCHEMA, "anchors": gate.anchor_digest(root)}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="rewrite the digest instead of checking it")
    parser.add_argument("--describe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.describe:
        print(DESCRIBE)
        return 0

    root = gate.plugin_root()
    target = root / gate.ANCHOR_DIGEST_REL
    current = render(root)
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(current, encoding="utf-8")
        print(f"{target}: {len(json.loads(current)['anchors'])} anchor(s) written")
        return 0

    if not target.is_file():
        print(f"{target} is missing — run `adw.py anchors --write` (E-02 has no anchor without it)", file=sys.stderr)
        return 1
    if target.read_text(encoding="utf-8") != current:
        print(
            f"{target} is STALE — the enforcement layer changed since it was written. "
            "Run `adw.py anchors --write` and commit the result.",
            file=sys.stderr,
        )
        return 1
    print(f"{target}: current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
