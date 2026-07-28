# plugins/

One directory per plugin of the `wntic-adw` marketplace. The catalog is
`../.claude-plugin/marketplace.json`; the packaging reference is `../notes/21_plugin_packaging.md`.

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

## `adw` is one of them

`plugins/adw/` has exactly that shape, and it did not always: `integrity.self-hash` used to verify
the enforcement layer against *git* HEAD, an installed plugin is a content copy with no `.git`, and
satisfying that once forced the whole repository to be the plugin. The gate now falls back to a
shipped digest (`plugins/adw/.claude-plugin/anchors.json`, written by `adw.py anchors --write`), so
`adw` installs like anything else. A plugin that does not run `gate.py` never had the question.

Two things a new plugin should NOT copy from `adw`, because they belong to the workflow rather than
to plugins in general: the anchor digest, and the `.claude/` symlinks at the repository root (they
exist so this repo can load the workflow while developing it).
