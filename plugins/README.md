# plugins/

One directory per plugin of the `wntic-adw` marketplace. The catalog is
`../.claude-plugin/marketplace.json`; the packaging reference is `../notes/21_plugin_packaging.md`.

## Adding a plugin

Give it its own manifest and list it with a **relative** source:

```
plugins/my-plugin/.claude-plugin/plugin.json
plugins/my-plugin/{skills,commands,agents,hooks}/
```

```json
{ "name": "my-plugin", "source": "./plugins/my-plugin" }
```

That is the ordinary case and it needs nothing else: the plugin's own root is
`plugins/my-plugin/`, so the platform discovers `skills/`, `commands/`, `agents/` and
`hooks/hooks.json` there by location, with no custom paths to declare.

## Why `adw` is laid out differently

A relative source installs as a **content copy with no `.git`** in the plugin cache (measured —
`notes/21` §5a). `adw` gates itself, and `integrity.self-hash` needs the enforcement layer to be
inside a git checkout, so `adw` must be fetched as a whole repository — which makes **this
repository** its installation root. Hence, for `adw` alone:

- its manifest is `../.claude-plugin/plugin.json`, not `plugins/adw/.claude-plugin/plugin.json`;
  a manifest inside `plugins/adw/` would never be read;
- that manifest declares where the assets are (`skills`, `commands` → `./plugins/adw/…`);
- `../agents` and `../hooks` are relative symlinks into `plugins/adw/`, because the platform loads
  an agent from the installation root's `agents/` and from **no** custom path at all, and
  `hooks/hooks.json` is its default home.

A plugin that does not run `gate.py` has nothing to prove and needs none of this.
