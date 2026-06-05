"""Store profiles — the small OPEN registry (redesign variant B).

A datastore's `kind` is a free token (schema.py). This registry maps a kind to the few
things the generator needs to wire a repository to it WITHOUT knowing the backend's SQL/SDK
internals (those live in the scaffolded bodies the implementer fills):

  * which resource the repository is injected with (a Postgres `session_factory`, a Qdrant
    `client`, …) — its param name, instance attribute, type annotation, and import;
  * the contract-comment STYLE for the repository's methods (relational `sql` vs. a
    `collection`/`generic` store);
  * whether the store reuses the existing Postgres bootstrap (`db_engine`/`session_factory`)
    or needs a scaffolded `create_<store>_client` connection factory.

A kind with NO registered profile DEGRADES GRACEFULLY to a generic, untyped client
(`client: object`) plus a loud contract comment — the same fail-loud-not-crash principle the
table scaffold follows. Adding a backend = one entry here, never a generator rewrite.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreProfile:
    kind: str
    resource_param: str  # repository ctor parameter + DI kwarg name
    resource_attr: str  # repository instance attribute: self._<attr>
    resource_type: str  # type annotation (ctor + container Provider[...])
    resource_import: str  # import line for resource_type ("" when none, e.g. a builtin)
    contract: str  # 'sql' | 'collection' | 'generic' — repo-method contract wording
    uses_bootstrap: bool  # True = the existing db_engine/session_factory bootstrap (postgres);
    # False = a scaffolded create_<store>_client connection factory the container injects.


_POSTGRES = StoreProfile(
    kind="postgres",
    resource_param="session_factory",
    resource_attr="sf",
    resource_type="async_sessionmaker[AsyncSession]",
    resource_import="from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker",
    contract="sql",
    uses_bootstrap=True,
)

_REGISTRY: dict[str, StoreProfile] = {
    "postgres": _POSTGRES,
    "qdrant": StoreProfile(
        kind="qdrant",
        resource_param="client",
        resource_attr="client",
        resource_type="QdrantClient",
        resource_import="from qdrant_client import QdrantClient",
        contract="collection",
        uses_bootstrap=False,
    ),
    "redis": StoreProfile(
        kind="redis",
        resource_param="client",
        resource_attr="client",
        resource_type="Redis",
        resource_import="from redis.asyncio import Redis",
        contract="generic",
        uses_bootstrap=False,
    ),
}


def kind_of(datastores, store: str | None) -> str:
    """The kind of the datastore a repository targets. Defaults to 'postgres' when the repo
    names no `store` or the manifest declares no matching datastore (legacy single-store).
    The one source of this resolution — shared by the generator and the drift checker."""
    if store is None:
        return "postgres"
    ds = next((d for d in datastores if d.name == store), None)
    return ds.kind if ds else "postgres"


def profile_for(kind: str) -> StoreProfile:
    """Resolve a store kind to its profile; an unknown kind degrades to a generic untyped
    client (never crashes — the redesign's fail-loud invariant)."""
    known = _REGISTRY.get(kind)
    if known is not None:
        return known
    return StoreProfile(
        kind=kind,
        resource_param="client",
        resource_attr="client",
        resource_type="object",
        resource_import="",
        contract="generic",
        uses_bootstrap=False,
    )
