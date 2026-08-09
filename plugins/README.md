# plugins/

One directory per plugin of the `wntic-adw` marketplace. The catalog is
`../.claude-plugin/marketplace.json`, and it is the only one in this tree: a plugin never carries
a catalog of its own. The measured packaging reference — what the platform actually does with
plugin layouts, verified by install rehearsals — is one command away:
`git show v3-archive:notes/21_plugin_packaging.md`.

## Adding a plugin

```
plugins/my-plugin/.claude-plugin/plugin.json
plugins/my-plugin/{skills,commands,agents,hooks,...}/
```

```json
{ "name": "my-plugin", "source": "./plugins/my-plugin" }
```

That is all of it. The plugin's own root is `plugins/my-plugin/`, so the platform discovers every
component there by location and the manifest declares no paths.

A plugin that arrives from a repository of its own sheds that repository's shell on the way in:
its `marketplace.json`, its `LICENSE`, its `.gitignore` belong to the tree it joined. Licensing is
the root `../LICENSE`; ignores are the root `../.gitignore`. What a plugin keeps is its
`plugin.json`, its components, its `README.md` and — if it versions itself — its `CHANGELOG.md`.

## The two of them

`plugins/adw/` is the workflow, and the red lines of `../CLAUDE.md` govern it. It has exactly the
shape above and nothing more. It once needed an extra mechanism — a shipped digest, so a
self-verifying enforcement layer could still check itself after being copied into a tree with no
`.git` — and that mechanism is gone along with the layer that wanted it. A plugin that ships no
self-verifying script never has the question.

`plugins/run-report/` is an observability tool with its own lifecycle, deliberately **outside** the
workflow and its red lines: its script is legal and does not count against the enforcement budget,
whose check is scoped to `plugins/adw`. It is the one plugin here that versions itself, so it is the
one that keeps a `CHANGELOG.md`.

The one thing a new plugin should NOT copy from `adw` is the `.claude/` symlinks at the repository
root: they exist only so this repo can load the workflow while developing it.
