# plugins/

Additional plugins of the `wntic-adw` marketplace. One directory per plugin, each with its own
`.claude-plugin/plugin.json`, listed in `../.claude-plugin/marketplace.json` with a **relative**
source:

```json
{ "name": "my-plugin", "source": "./plugins/my-plugin" }
```

A relative source installs as a content copy with no `.git` in the plugin cache
(`notes/21_plugin_packaging.md` §5a). That is fine here and forbidden for `adw` alone: `adw` gates
itself, and `integrity.self-hash` needs the enforcement layer to be inside a git checkout. A plugin
that does not run `gate.py` has nothing to prove and may live in a subdirectory.
