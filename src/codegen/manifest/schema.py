"""Pydantic schema for an epic manifest.

This is the executable form of `.claude/templates/MANIFEST_SCHEMA.md`. It is
the deterministic *form* check (validation rule #1): types, required fields,
`Literal` enumerations, and the intra-node consistency that lives entirely
inside a single artifact (rule #11, the local part).

Scope: the node kinds the pilot epics use — the CRUD slice (domain entities,
repository protocols, exceptions; application commands and queries; infrastructure
tables and repositories; REST schemas and endpoints; the cross-cutting `tests`
block) plus the auth slice that lets a manifest declare its own authentication
instead of the generator hardcoding it: domain enums, value objects, services,
capability protocols; infrastructure settings and capability adapters. Node kinds
still reserved (filters, unit_of_work, compensating_tx) are NOT modelled yet —
every container sets `extra="forbid"`, so a manifest that uses them fails loudly
until this schema is extended. That is intentional: fail fast, not silent.

NOT in scope here (belongs to the §5 graph validator, which runs after this):
  - cross-node reference resolution (handler deps → declared protocols, etc.)
  - `sources:` resolving to real UC files
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic import Field as PydanticField  # `Field` is taken by the manifest leaf model below


class _Model(BaseModel):
    """Base: forbid unknown keys so typos and unmodelled node kinds fail loudly."""

    model_config = ConfigDict(extra="forbid")


# A method signature is a verbatim Python signature (transcribed into the generated code,
# parsed only structurally for the name + type tokens) — NOT a logic DSL. This guard makes a
# malformed signature fail LOUDLY at parse time instead of crashing the generator's regex or
# emitting broken Python: it must read `(async )def <name>(self, …) -> <ReturnType>` with no
# trailing colon (the generator appends the `:`). It checks SHAPE, never the type grammar.
_SIGNATURE_RE = re.compile(r"^(async\s+)?def\s+[A-Za-z_]\w*\(self\b.*\)\s*->\s*\S.*$")


def _check_signature(value: str) -> str:
    text = value.strip()
    if not _SIGNATURE_RE.match(text) or text.endswith(":"):
        raise ValueError(
            f"malformed method signature {value!r}: expected "
            f"'(async )def <name>(self, ...) -> <ReturnType>' with no trailing colon"
        )
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Shared leaf models
# ─────────────────────────────────────────────────────────────────────────────


class Field(_Model):
    name: str
    type: str
    optional: bool = False
    default: str | None = None
    # No glue attributes. Audit timestamps (created_at/updated_at) are NOT domain
    # fields and NOT declared here — the generator adds them to every aggregate table
    # as a DB-managed persistence convention (server_default/onupdate), off the domain
    # entity. List filtering/ordering is likewise a body contract, not a field.


class Invariant(_Model):
    """An enforceable runtime invariant on an entity/VO. A CONTRACT declaration (prose
    `rule` + the `field` it concerns + `source`), NOT executable code — it feeds the
    scaffolded `__post_init__` contract-comment and the canonical test (§9). The body sees
    ALL of the entity's fields, so `rule` may express a CROSS-FIELD condition ("end_date >
    start_date", "if status==CLOSED then closed_at is set"). `field` names the column the
    violation reports (`ValidationError.context["field"]`); it is OPTIONAL — omit it for a
    whole-entity rule with no single offending field (e.g. "sum(items) == total"), else
    name the primary offending field. Design NOTES that aren't runtime checks don't belong
    here (use a YAML comment)."""

    rule: str
    field: str | None = None
    source: str


# ─────────────────────────────────────────────────────────────────────────────
# behaviour — canonical given/when/then scenarios (MANIFEST_SCHEMA.md §13)
# ─────────────────────────────────────────────────────────────────────────────


class Then(_Model):
    """Outcome clause — closed vocabulary. At least one verb must be set."""

    raises: str | None = None
    returns: str | None = None
    persists: str | None = None
    deletes: str | None = None
    logs: str | None = None
    calls: str | None = None  # "<Dependency>.<method>"
    # `with` MODIFIES `persists`: a flat {field: value} map of expected POST-STATE on the
    # saved entity (mirrors arrange/act — literals only, no computation/relation). It is
    # the VERIFY half for state transitions: `then: {persists: Ticket, with: {status:
    # CLOSED}}` makes the generated test assert `stored.status == CLOSED`, so a no-op
    # "re-save unchanged" body goes RED. Not a new verb — it requires `persists`.
    with_: dict = PydanticField(default_factory=dict, alias="with")

    @model_validator(mode="after")
    def _at_least_one_verb(self) -> "Then":
        if not any((self.raises, self.returns, self.persists, self.deletes, self.logs, self.calls)):
            raise ValueError("then: at least one outcome verb is required")
        if self.with_ and not self.persists:
            raise ValueError("then.with requires then.persists (it asserts the persisted entity's post-state)")
        return self


class Seed(_Model):
    """One pre-existing record in the fake-repo starting state. `entity` names the
    aggregate; `fields` are literal field overrides (the rest default from the
    entity's own field defaults). Realizes the `given` precondition concretely so
    the canonical test seeds the fake the same way the prose describes."""

    entity: str
    fields: dict = {}


class Behaviour(_Model):
    given: str  # prose precondition, realized against a named fixture
    # arrange: seed of the starting state (records that exist before `when`). Empty
    # = empty starting state. act: literal input values for the call under test
    # (input field name → literal). Both feed the §9 canonical test AND the scaffold
    # contract-comment. then stays a CLOSED vocabulary (no not_calls/fails/@now —
    # those earn their place in the manual test file, not the schema).
    arrange: list[Seed] = []
    when: str  # method under test (`execute` for handlers; the method name for services)
    act: dict = {}
    then: Then
    source: str


# ─────────────────────────────────────────────────────────────────────────────
# Domain
# ─────────────────────────────────────────────────────────────────────────────


class EnumMember(_Model):
    name: str  # SCREAMING_SNAKE_CASE
    value: str


class EnumMethod(_Model):
    """A pure-logic method on the enum (ordering/rank/membership). Body is SCAFFOLDED
    (the implementer fills it from `rule`) — so an enum that declares methods is a
    body-bearing file (write-once), like an entity with invariants."""

    signature: str
    rule: str

    _v_signature = field_validator("signature")(_check_signature)


class Enum(_Model):
    name: str
    subdomain: str
    base: Literal["StrEnum", "Enum"] = "StrEnum"
    members: list[EnumMember]
    methods: list[EnumMethod] = []
    sources: list[str]


class ValueObject(_Model):
    """A frozen, value-equality domain type. Plain fields → declarative (regenerated);
    `invariants` → a SCAFFOLDED `__post_init__` (write-once), exactly like an entity."""

    name: str
    subdomain: str
    frozen: bool = True
    fields: list[Field]
    invariants: list[Invariant] = []
    sources: list[str]


class ServiceMethod(_Model):
    signature: str
    raises: list[str] = []
    # behaviour is the CANONICAL spec of what the method does — without it the scaffold
    # is unimplementable (the signature + raises say nothing about WHICH input raises
    # WHICH error). Lives per-method because a service may expose several. Feeds the
    # contract-comment + the §9 tests, exactly like a handler's behaviour.
    behaviour: list[Behaviour] = []
    # Per-method prose GUIDE (the method's distilled rule/algorithm). Complements the
    # service-wide `Service.notes`; rendered into THIS method's contract-comment.
    notes: str | None = None

    _v_signature = field_validator("signature")(_check_signature)


class ProtocolMethod(_Model):
    """One method of a repository/capability protocol. The signature is the contract; the
    optional `notes` is a per-method prose GUIDE (semantic, impl-agnostic) the adapter
    implementer reads. Authored as a bare signature string OR a {signature, notes} mapping
    — the protocol coerces strings to this shape (see `_coerce_protocol_methods`)."""

    signature: str
    notes: str | None = None

    _v_signature = field_validator("signature")(_check_signature)


def _coerce_protocol_methods(value):
    """Allow `methods:` entries to be a bare signature string (the terse common case) or a
    full {signature, notes} mapping — only the methods that need a note grow an object."""
    if isinstance(value, list):
        return [{"signature": m} if isinstance(m, str) else m for m in value]
    return value


class Service(_Model):
    """A domain service (orchestrator over injected protocols). The method bodies are
    SCAFFOLDED — the implementer fills them; the generator emits the class + the
    injected-dependency constructor + the method signatures + contract."""

    name: str
    subdomain: str
    kind: Literal["orchestrator", "pure"] = "orchestrator"
    dependencies: list[str] = []
    methods: list[ServiceMethod]
    # Distilled implementation intent in prose — the rule/algorithm the body enforces, in
    # the architect's words. Read by the implementer (the GUIDE channel; `behaviour` is the
    # VERIFY channel, `sources` is provenance). Distilled from the UC, NOT a pointer to it.
    notes: str | None = None
    sources: list[str]

    @model_validator(mode="after")
    def _behaviour_matches_contract(self) -> "Service":
        """Rule #11 (local part), per method: every `then` clause type-checks against the
        method's own `raises:` and the service's injected `dependencies:`."""
        deps = set(self.dependencies)
        for m in self.methods:
            raises = set(m.raises)
            for scenario in m.behaviour:
                then = scenario.then
                if then.raises and then.raises not in raises:
                    raise ValueError(
                        f"service {self.name} method {m.signature!r}: then.raises={then.raises!r} "
                        f"not in method raises {sorted(raises)}"
                    )
                if then.calls:
                    dep = then.calls.split(".", 1)[0]
                    if dep not in deps:
                        raise ValueError(
                            f"service {self.name} method {m.signature!r}: then.calls dependency {dep!r} "
                            f"not in dependencies {sorted(deps)}"
                        )
        return self


class CapabilityProtocol(_Model):
    """A narrow `ICan<Verb>` action interface (token verify, blob store, render).
    Declarative — a `typing.Protocol` like a repository protocol, but it lives in its
    own subdomain and its infra adapter is a separate scaffolded `capability`.

    `notes` here is the protocol-wide SEMANTIC contract (impl-agnostic — the domain must
    not know the SDK). Per-method semantics go on each `ProtocolMethod.notes`; SDK-specific
    guidance ("use PyJWT, HS256, …") lives on the infrastructure `Capability.notes`."""

    name: str
    subdomain: str
    methods: list[ProtocolMethod]  # bare signature string or {signature, notes}
    sources: list[str]
    notes: str | None = None

    _coerce_methods = field_validator("methods", mode="before")(_coerce_protocol_methods)


class Entity(_Model):
    name: str
    subdomain: str
    identity_field: str = "id"
    fields: list[Field]
    invariants: list[Invariant] = []
    sources: list[str]


class RepositoryProtocol(_Model):
    name: str
    subdomain: str
    aggregate: str
    methods: list[ProtocolMethod]  # bare signature string or {signature, notes}
    # NOTE: no `list_order` — list ordering (like filtering) is a body contract the
    # implementer derives from the query behaviour + the method signature (or a per-method
    # `notes`), not an anticipatory schema field. The generated fake is mechanical.
    raises: list[str] = []
    sources: list[str]

    _coerce_methods = field_validator("methods", mode="before")(_coerce_protocol_methods)


class DomainException(_Model):
    name: str
    code: str
    http_status: int
    sources: list[str]


class Domain(_Model):
    enums: list[Enum] = []
    value_objects: list[ValueObject] = []
    entities: list[Entity] = []
    services: list[Service] = []
    repository_protocols: list[RepositoryProtocol] = []
    capability_protocols: list[CapabilityProtocol] = []
    exceptions: list[DomainException] = []


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────


# The body axis is NOT a manifest field. Whether a node is generated (declarative /
# glue) or scaffolded (a method body the implementer LLM fills) is DERIVED from the
# node category, never declared (spec §3, §5): every application handler is a
# scaffold; enums / exceptions / protocols / plain VOs are generated; an entity is
# generated except its `__post_init__`, which is scaffolded. No `body`/`operation`/
# `sets` fields — those drove the dead deterministic-body macro.


class Handler(_Model):
    dependencies: list[str] = []


class _BehaviourConsistencyMixin(BaseModel):
    """Rule #11 (local part): every `then` clause type-checks against its node."""

    @model_validator(mode="after")
    def _behaviour_matches_contract(self):
        raises = set(getattr(self, "raises", []) or [])
        deps = set(self.handler.dependencies) if getattr(self, "handler", None) else set()
        log_event = getattr(self, "log_event", None)
        for scenario in getattr(self, "behaviour", []) or []:
            then = scenario.then
            if then.raises and then.raises not in raises:
                raise ValueError(
                    f"behaviour[{scenario.given!r}]: then.raises={then.raises!r} not in node raises {sorted(raises)}"
                )
            if then.logs and log_event is not None and then.logs != log_event:
                raise ValueError(
                    f"behaviour[{scenario.given!r}]: then.logs={then.logs!r} != node log_event={log_event!r}"
                )
            if then.calls:
                dep = then.calls.split(".", 1)[0]
                if dep not in deps:
                    raise ValueError(
                        f"behaviour[{scenario.given!r}]: then.calls dependency {dep!r} "
                        f"not in handler.dependencies {sorted(deps)}"
                    )
        return self


class Command(_BehaviourConsistencyMixin, _Model):
    name: str
    input: list[Field] = []
    output: str  # "UUID" | "None"
    handler: Handler
    # Optional: a command that emits a structured success event declares the event name
    # (snake_case — not derivable from English morphology). Omitted → the handler logs no
    # business event (a public/side-effect-free command need not). Feeds the §11 then.logs
    # check only when present.
    log_event: str | None = None
    raises: list[str] = []
    behaviour: list[Behaviour] = []
    sources: list[str]
    # Distilled prose intent the implementer reads — the rule/algorithm the body enforces
    # (the GUIDE channel). Rendered into the contract-comment. Behaviour VERIFIES, notes
    # GUIDES, sources is provenance — distilled from the UC, never a pointer to it.
    notes: str | None = None


class ResultDto(_Model):
    """A helper read-model DTO a query's result is composed of — a nested projection (e.g. a
    search hit `{chunk, score}`) the main `*Result` DTO references. Application-layer read
    projection, NOT a domain type; lives beside the `*Result` DTO. This is the only way to
    nest read models — `result_fields` are otherwise flat. Its `fields` may reference domain
    types, stdlib, or other `result_dtos`/`output` of the same query (resolved as siblings)."""

    name: str
    fields: list[Field]


class Query(_BehaviourConsistencyMixin, _Model):
    name: str
    input: list[Field] = []
    output: str  # entity name or *Result DTO name
    result_fields: list[Field] = []
    # Secondary read-model DTOs this query's result nests (e.g. SearchHit{chunk, score}); the
    # main *Result DTO's `result_fields` may type a field as `tuple[SearchHit, ...]`.
    result_dtos: list[ResultDto] = []
    handler: Handler
    raises: list[str] = []
    behaviour: list[Behaviour] = []
    sources: list[str]
    notes: str | None = None


class Application(_Model):
    commands: list[Command] = []
    queries: list[Query] = []


# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure
# ─────────────────────────────────────────────────────────────────────────────


# NOTE: there is no `Table`/`Alembic` model. A relational table's schema (column TYPES,
# indexes, constraints) is JUDGMENT the implementer fills in a write-once Table SCAFFOLD
# (§3/§4) — not a transcription the generator emits from a Python→SQL type map (the old
# `_SQL_CORE`, which broke on any unforeseen type). Migrations are owned by Alembic
# natively (the chain lives in `versions/`, not the manifest); the manifest is a SNAPSHOT
# of the desired schema, never a journal of revisions. Which entity is persisted, and in
# which store, is carried by `Repository.backs` + `Repository.store`.


class Datastore(_Model):
    """A configured persistence backend behind which storage JUDGMENT lives — the schema,
    indexes, constraints, and queries are bodies the implementer writes (§3), not a
    transcription the generator emits. A repository targets exactly one datastore via
    `store`.

    `kind` is a FREE token, deliberately NOT a `Literal`: a closed enum of backends would
    be the `_SQL_CORE` disease again (it breaks on the first unforeseen store). The
    generator maps `kind` to a connection-wiring + schema-setup PROFILE (postgres / qdrant /
    redis / …); an UNKNOWN kind degrades to a bare scaffold rather than crashing. `settings`
    references the `infrastructure.settings` class carrying connection config; the driver
    `requires_packages` land in pyproject by graph union (§10)."""

    name: str
    kind: str
    settings: str | None = None
    requires_packages: list[str] = []
    sources: list[str]


class Repository(_Model):
    implements: str
    backs: str
    # The datastore this repository persists to (references a `datastores[*].name`).
    # Optional for now: a manifest with no datastores declared keeps the legacy single-
    # Postgres behaviour (the generator synthesises an implicit `main` postgres store).
    # Polyglot persistence = several datastores + each repository naming its own.
    store: str | None = None
    constraint_map: dict[str, str] = {}
    # SQL/persistence-specific implementation GUIDE (the infra layer — e.g. "filter on a
    # partial index", "join …", "paginate with keyset"). The impl-agnostic semantics live
    # on the RepositoryProtocol (domain); this is where tech detail belongs.
    notes: str | None = None
    sources: list[str]


class SettingsField(_Model):
    name: str
    type: str
    default: str | None = None
    secret: bool = False  # → SecretStr (never logged, no default permitted)


class Settings(_Model):
    """A `pydantic-settings` BaseSettings class — the one place env vars are read.
    Declarative: fully transcribed from the manifest (env_prefix + typed fields).

    NO `subpackage`: a settings' infra home is DERIVED from its CONSUMER's tech — the
    capability `adapter` (openai/jwt) or the datastore `kind` (qdrant) that references it.
    Infrastructure groups by the external integration, not by a domain subdomain (that was
    the `ai`/`corpus` smell); the tech is already in the graph, so storing it here too
    would be a second source of truth (anticipation litmus)."""

    name: str
    env_prefix: str
    fields: list[SettingsField]
    sources: list[str]


class Capability(_Model):
    """An infra adapter implementing a domain `ICan<Verb>` capability protocol by
    wrapping an SDK (PyJWT, boto3, httpx). Body is SCAFFOLDED behind the port (§10)."""

    implements: str  # capability_protocol name
    adapter: str  # tech token (e.g. "jwt", "openai") → class prefix + infra subpackage
    # Optional agent-noun for the adapter's role (`TextEmbedder`, `TokenManager`). The class
    # is DERIVED as `<AdapterPascal><role>` (→ OpenaiTextEmbedder); the file follows. Carried
    # because verb→agent-noun is NOT mechanically derivable from the `ICan<Verb>` protocol
    # (irregular English -er/-or, like the `log_event` precedent) and a human reviews the
    # name. Absent → fall back to the verb form `<AdapterPascal><Verb>` (OpenaiEmbedText).
    role: str | None = None
    settings: str | None = None  # references infrastructure.settings[*].name
    # Third-party SDK packages this adapter wraps (PyJWT, boto3, openai, …). Unioned into
    # pyproject by the graph (§10); versions are pinned here at phase-2 review. Bare on a
    # pure-CPU adapter that needs no SDK.
    requires_packages: list[str] = []
    # SDK-specific implementation GUIDE (the infra layer — e.g. "PyJWT, HS256, secret from
    # settings.secret, ttl from settings.ttl_seconds; map jwt.ExpiredSignatureError →
    # UnauthorizedError"). The domain protocol stays SDK-ignorant; tech detail lives here.
    notes: str | None = None
    sources: list[str]


class Infrastructure(_Model):
    settings: list[Settings] = []
    datastores: list[Datastore] = []
    repositories: list[Repository] = []
    capabilities: list[Capability] = []


# ─────────────────────────────────────────────────────────────────────────────
# REST API
# ─────────────────────────────────────────────────────────────────────────────


class RestSchema(_Model):
    name: str
    resource: str
    kind: Literal["request", "response"]
    fields: list[Field]
    sources: list[str]


class Endpoint(_Model):
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"]
    path: str
    resource: str
    auth: str  # anonymous | authenticated | role:<ROLE>
    request: str | None = None
    response: str | None = None
    # The request BODY shape (HTTP content types are a closed, standard set). `json` (default)
    # → a Pydantic `request` schema; `multipart` → the generator derives an UploadFile + Form
    # signature from the handler command's inputs (a `bytes` input → the file), no JSON schema.
    request_kind: Literal["json", "multipart"] = "json"
    # status_code is an OPTIONAL override: when unset the generator derives it from the
    # method (POST→201, DELETE→204, else 200). Declare it only for a non-standard code.
    status_code: int | None = None
    handler: str
    # NB: no `errors:` — the advertised error codes are DERIVED from the handler's `raises`
    # (mapped to HTTP) plus the auth dependency (401/403); declaring them here duplicated
    # the handler contract. The endpoint advertises exactly what its handler can raise.
    # Optional prose GUIDE for the thin route — used ONLY for non-1:1 response assembly that
    # isn't derivable (a field rename like result.token → access_token, a constant like
    # token_type="bearer", a custom header). Empty for the vast majority of routes.
    notes: str | None = None
    sources: list[str]


class RestApi(_Model):
    schemas: list[RestSchema] = []
    endpoints: list[Endpoint] = []


# ─────────────────────────────────────────────────────────────────────────────
# Tests (cross-cutting only)
# ─────────────────────────────────────────────────────────────────────────────


class ArchitectureRule(_Model):
    name: str
    pattern: str
    paths: list[str]
    allow_list: list[str] = []
    sources: list[str] = []


class Tests(_Model):
    architecture_rules: list[ArchitectureRule] = []


# ─────────────────────────────────────────────────────────────────────────────
# Meta + root
# ─────────────────────────────────────────────────────────────────────────────


class Meta(_Model):
    # `status:` is intentionally absent — §4 removes process state from the
    # manifest. The annotated template still carries it (deferred cleanup).
    epic: str
    name: str
    sources: list[str]
    supersedes: list[str] = []
    replaces: list[str] = []
    notes: str | None = None


class Manifest(_Model):
    meta: Meta
    domain: Domain = Domain()
    application: Application = Application()
    infrastructure: Infrastructure = Infrastructure()
    restapi: RestApi = RestApi()
    tests: Tests = Tests()
