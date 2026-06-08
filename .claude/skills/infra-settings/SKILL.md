---
name: infra-settings
description: Apply when a spec adds a new external integration (database, blob store, third-party API, observability backend) or new configuration for an existing one. Produces one `pydantic-settings` `BaseSettings` class per integration, scoped to its infrastructure subpackage, with a stable env prefix, `SecretStr` for secrets, and `@computed_field` for derived values. The DI wiring (always `providers.Singleton`) is the responsibility of `infra-di-provider`. Defers package mechanics to `general-python-package`.
---

# Infrastructure Settings

Produces one settings class per external integration. The class is the **only** place this codebase reads environment variables — adapters always receive a settings object via DI.

## When to use vs. neighbours

- Adding/extending env-backed configuration for an integration → this skill.
- Wiring the settings into `containers.py` as a Singleton → `infra-di-provider`.
- A frozen-dataclass domain-shaped view of these settings (a tunable knob the domain consults) → the tunable-VO variant in `domain-value-object` (it consumes fields from the settings class).

## File location and naming

- Path: `src/<root>/infrastructure/<subpackage>/settings.py` — always named `settings.py`.
- Class: `<Concept>Settings`. Not `Config`, not `Options`.
- Env prefix: `MYAPP_<DOMAIN>_` (uppercase, short noun 3–8 chars, terminal underscore). Never reuse a prefix across two classes.

## Template

```python
from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["DbSettings"]

class DbSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MYAPP_DB_",
        env_file=".env",
        extra="ignore",
    )

    host: str
    port: int = 5432
    user: str
    password: SecretStr
    name: str

    pool_size: int = 10
    max_overflow: int = 5
    pool_pre_ping: bool = True
    echo: bool = False

    @computed_field
    @property
    def dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
```

## Rules

### Required `model_config`

All three keys are mandatory:

- `env_prefix="MYAPP_<DOMAIN>_"`
- `env_file=".env"` — local dev reads `.env`; production injects via real environment (the file simply isn't there).
- `extra="ignore"` — unknown env vars in the namespace are tolerated. Without this, a stray var crashes startup.

### Field shape

1. **Required fields have no default.** Missing values fail loudly at container instantiation, before any request is served.
2. **Optional fields use inline defaults.** Defaults must be safe values for production-like setups.
3. **Booleans use Python types**, not strings. Pydantic parses env-string forms (`"true"`, `"1"`, `"yes"`) correctly.
4. **Numerics use real types** — `port: int`, never `str`.
5. **Optional is `T | None = None`**, never `T = ""`.

### Secrets

6. **`SecretStr` for any value that must not appear in logs, repr, or tracebacks** — passwords, API keys, signing secrets, JWT keys.
7. **Never default a secret.** If a secret env var is missing, the process must crash at startup.
8. **`.get_secret_value()` is called only at point of use** (inside a `@computed_field` like `dsn`, or when constructing an SDK client). Never log, format, or print a `SecretStr`.

### Composition

9. **Derived values live in `@computed_field @property`.** DSNs, composite URLs, normalized strings. Adapters consume the computed value, not the parts.
10. **Two integrations don't share fields by importing one's settings class from another.** Each settings class is self-contained; copy the field if both genuinely need it.

### Validators

11. **`@field_validator` for two purposes only:**
    - **Normalization** — accept env-friendly form, store canonical form (e.g. unescaping `\\n` in multi-line keys).
    - **Rejection** — refuse values that would cause silent misbehavior (e.g. allowlist JWT algorithms).
12. **Validation messages should be clear** — they surface at container startup where stack traces get read.

### Scope and ownership

13. **One settings class per infrastructure subpackage.** Bundling unrelated config under one prefix is forbidden.
14. **Settings live next to the adapter they configure.** No top-level central settings module.
15. **Re-export from the subpackage `__init__.py`** — the settings class is part of the subpackage's public surface.

### Reading env

16. **Settings are instantiated only in `containers.py`.** Never call `DbSettings()` from a handler, an entrypoint, a test fixture, or another settings class.
17. **Adapters depend on the settings type**, not on `os.environ` or `os.getenv`. No `os.getenv` outside settings classes themselves.

### Testing

18. **Tests construct settings explicitly with values**, not by mutating env: `DbSettings(host="localhost", user="t", password=SecretStr("t"), name="t")`.
19. **Don't `monkeypatch.setenv`** to drive settings unless testing the env-parsing layer itself.

## Inlined typing / import rules

- `from pydantic import SecretStr, computed_field` — add `field_validator` to this line **only when the class defines one** (rule 11); an unused import is an F401.
- `from pydantic_settings import BaseSettings, SettingsConfigDict`.
- Full annotations on every field and validator.
- No `from __future__ import annotations`.

## Package wiring

Follow `general-python-package` to re-export the settings class from the subpackage `__init__.py`. The DI Singleton wiring is in `infra-di-provider`.

## Hard stops

- Spec asks for env reads outside a settings class → stop, route through a settings field.
- Spec wants two unrelated integrations under the same prefix → stop, split into two classes.
- Spec asks the adapter to take individual fields instead of the settings object → discouraged; pass the whole settings object. Use individual fields only via `.provided.<field>` in the DI wiring when a tunable VO needs a single value.
