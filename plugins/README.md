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

`plugins/adw/` has exactly that shape and nothing more. It once needed an extra mechanism — a
shipped digest, so a self-verifying enforcement layer could still check itself after being copied
into a tree with no `.git` — and that mechanism is gone along with the layer that wanted it
(`../HISTORY.md`). A plugin that ships no self-verifying script never has the question.

The one thing a new plugin should NOT copy from `adw` is the `.claude/` symlinks at the repository
root: they exist only so this repo can load the workflow while developing it.
