"""Tests for the forward generator — exercised end-to-end on the Helpdesk manifest.

Helpdesk (examples/helpdesk_manifest.yaml) replaces the Tag slice as the generator's
primary fixture. It proves the generator is not hardcoded to one aggregate and, above
all, that AUTH IS MANIFEST-DRIVEN: the Role enum, Email/CurrentUser value objects, the
JWT token capability, and the derived restapi/dependencies.py all come from manifest
nodes — nothing about auth is hardcoded in the generator anymore.
"""

import asyncio
import importlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from codegen.generator import Generator
from codegen.manifest.validator import load_and_validate

_FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "helpdesk_manifest.yaml"
_PKG = "hdkgen"  # unique root package name for the generated output under tmp_path


def _ruff(paths):
    ruff = shutil.which("ruff")
    if ruff is None:
        return None
    return subprocess.run(
        [
            ruff,
            "check",
            "--isolated",
            "--line-length",
            "120",
            "--config",
            f'lint.isort.known-first-party=["{_PKG}", "tests"]',
            "--select",
            "E,F,I,B,UP,SIM,RUF",
            "--ignore",
            "B008",
            *map(str, paths),
        ],
        capture_output=True,
        text=True,
    )


def _is_scaffold(path: Path) -> bool:
    """A body-bearing scaffold (write-once, filled by the implementer) carries the
    NotImplementedError marker; everything else is declarative/glue (always regenerated)."""
    return "raise NotImplementedError" in path.read_text()


def _gen(tmp_path: Path) -> tuple[Path, Path]:
    """Generate the whole hexagon + tests; return (package_root, tmp_root)."""
    manifest, report = load_and_validate(_FIXTURE)
    assert report.ok, report.findings
    pkg = tmp_path / _PKG
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    gen = Generator(manifest, pkg)
    gen.generate_all(tests_root=tmp_path / "tests")
    return pkg, tmp_path


def _read(pkg: Path, rel: str) -> str:
    return (pkg / rel).read_text()


def _fresh_import(tmp_path: Path, module: str):
    sys.path.insert(0, str(tmp_path))
    for m in [m for m in list(sys.modules) if m == _PKG or m.startswith(f"{_PKG}.")]:
        del sys.modules[m]
    return importlib.import_module(module)


# ── manifest validity + the headline: auth is manifest-driven ────────────────────


def test_manifest_validates() -> None:
    _, report = load_and_validate(_FIXTURE)
    assert report.ok, [f.message for f in report.findings]


def test_auth_is_manifest_driven_not_hardcoded(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    # Role is the manifest enum (MEMBER/AGENT/ADMIN), NOT the old hardcoded stub
    # (COLLABORATOR/ADMIN/SUPER_ADMIN). This is the de-hardcoding proof.
    role = _read(pkg, "domain/auth/role.py")
    assert 'MEMBER = "MEMBER"' in role and 'AGENT = "AGENT"' in role and 'ADMIN = "ADMIN"' in role
    assert "COLLABORATOR" not in role
    # dependencies.py is DERIVED: it resolves the manifest's token capability provider
    # and calls its verify method; CurrentUser/Role come from the manifest.
    deps = _read(pkg, "restapi/dependencies.py")
    assert "request.app.state.container.manage_tokens()" in deps
    assert "verifier.verify(creds.credentials)" in deps
    assert "from hdkgen.domain.auth import CurrentUser, Role" in deps
    # the generator no longer hardcodes a jwt_verifier() that doesn't exist
    assert "jwt_verifier()" not in deps


# ── domain: enums, value objects, entities, protocols, services ──────────────────


def test_domain_files_written(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    for rel in (
        "domain/exceptions.py",
        "domain/auth/role.py",
        "domain/auth/email.py",
        "domain/auth/current_user.py",
        "domain/auth/user.py",
        "domain/auth/i_user_repository.py",
        "domain/auth/i_can_manage_tokens.py",
        "domain/auth/__init__.py",
        "domain/support/ticket.py",
        "domain/support/ticket_status.py",
        "domain/support/i_ticket_repository.py",
        "domain/support/ticket_assignment_service.py",
    ):
        assert (pkg / rel).is_file(), rel


def test_role_enum_scaffolds_its_method(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/auth/role.py")
    assert "class Role(StrEnum):" in src
    # a pure-logic method is a scaffolded body the implementer fills
    assert 'def satisfies(self, required: "Role") -> bool:' in src
    assert "# Rule: rank order ADMIN >= AGENT >= MEMBER" in src
    assert 'raise NotImplementedError("Role.satisfies")' in src


def test_method_free_enum_is_declarative(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/support/ticket_status.py")
    assert "class TicketStatus(StrEnum):" in src
    assert 'OPEN = "OPEN"' in src and 'CLOSED = "CLOSED"' in src
    assert "NotImplementedError" not in src  # no methods → fully declarative


def test_email_value_object_scaffolds_post_init(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/auth/email.py")
    assert "@dataclass(frozen=True)" in src
    assert "class Email:" in src and "value: str" in src
    assert "from ..exceptions import ValidationError" in src  # imported for the body
    assert "def __post_init__(self) -> None:" in src
    assert "RFC 5322" in src  # the invariant in the contract-comment
    assert 'raise NotImplementedError("Email.__post_init__")' in src


def test_plain_value_object_has_no_post_init(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/auth/current_user.py")
    assert "@dataclass(frozen=True)" in src
    assert "id: UUID" in src and "role: Role" in src
    assert "from .role import Role" in src  # domain field type resolved (same subdomain)
    assert "__post_init__" not in src  # no invariants → declarative, no scaffold


def test_entity_resolves_domain_field_imports(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    user = _read(pkg, "domain/auth/user.py")
    assert "from .email import Email" in user and "from .role import Role" in user
    ticket = _read(pkg, "domain/support/ticket.py")
    assert "from .ticket_status import TicketStatus" in ticket
    assert "status: TicketStatus = TicketStatus.OPEN" in ticket


def test_plain_entity_identity_equality(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    mod = _fresh_import(tmp, f"{_PKG}.domain.support.ticket")
    Ticket = mod.Ticket
    tid = uuid4()
    a = Ticket(id=tid, title="a", description="d", reporter_id=uuid4())
    b = Ticket(id=tid, title="DIFFERENT", description="x", reporter_id=uuid4())
    assert a == b and hash(a) == hash(b)  # identity equality


def test_capability_protocol_shape(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/auth/i_can_manage_tokens.py")
    assert "class ICanManageTokens(Protocol):" in src
    assert "def issue(self, principal: CurrentUser) -> str: ..." in src
    assert "def verify(self, token: str) -> CurrentUser: ..." in src
    assert "from .current_user import CurrentUser" in src


def test_service_scaffold_shape(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "domain/support/ticket_assignment_service.py")
    assert "class TicketAssignmentService:" in src
    assert "def __init__(self, repo: IUserRepository) -> None:" in src
    assert "from ..auth import IUserRepository" in src  # cross-subdomain dependency
    assert "async def assert_assignable(self, assignee_id: UUID) -> None:" in src
    # the method's behaviour is the canonical spec the implementer fills against — without
    # it the scaffold is unimplementable (signature + raises don't say which input → which error)
    assert "# Behaviour scenarios (canonical, §9):" in src
    assert "given: no user with that id" in src and "then: raises NotFoundError" in src
    assert "given: a user that exists but is not an AGENT" in src and "then: raises ValidationError" in src
    assert 'raise NotImplementedError("TicketAssignmentService.assert_assignable")' in src


def test_exceptions_are_graph_derived(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    exc = _fresh_import(tmp, f"{_PKG}.domain.exceptions")
    # reached by handler/service raises + the auth dependency
    for name in ("NotFoundError", "ConflictError", "ValidationError", "UnauthorizedError", "ForbiddenError"):
        assert hasattr(exc, name), name
    assert exc.UnauthorizedError.http_status == 401
    assert exc.ForbiddenError.http_status == 403
    assert not hasattr(exc, "InUseError")  # never referenced → not emitted


# ── application: DTOs + handler scaffolds (single + multi-dependency) ────────────


def test_command_dto_prepends_caller_id_and_is_frozen(tmp_path: Path) -> None:
    import dataclasses

    _pkg, tmp = _gen(tmp_path)
    app = _fresh_import(tmp, f"{_PKG}.application.support")
    fields = [f.name for f in dataclasses.fields(app.CreateTicketCommand)]
    assert fields[0] == "caller_id"
    cmd = app.CreateTicketCommand(caller_id=uuid4(), title="t", description="d")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmd.title = "other"


def test_caller_id_is_derived_from_endpoint_auth(tmp_path: Path) -> None:
    # §A: a command carries caller_id IFF reached by a non-anonymous endpoint — not a
    # blanket house rule. Flip CreateTicket's endpoint to anonymous → the actor disappears.
    import yaml

    from codegen.manifest.schema import Manifest

    data = yaml.safe_load(_FIXTURE.read_text())

    def _create_ticket_dto(payload: dict, root: Path) -> str:
        root.mkdir()
        (root / "__init__.py").write_text("")
        gen = Generator(Manifest.model_validate(payload), root)
        gen.generate_domain()
        gen.generate_application()
        return (root / "application/support/create_ticket_command.py").read_text()

    authed = _create_ticket_dto(data, tmp_path / "authed")
    assert "caller_id: UUID" in authed  # POST /tickets is `authenticated`

    for ep in data["restapi"]["endpoints"]:
        if ep["handler"] == "CreateTicket":
            ep["auth"] = "anonymous"  # a public mutation — no acting principal
    public = _create_ticket_dto(data, tmp_path / "public")
    assert "caller_id" not in public
    assert "class CreateTicketCommand" in public  # still a valid (caller-less) DTO


def test_log_event_is_optional(tmp_path: Path) -> None:
    # omitting log_event → the handler logs no business event (public/side-effect-free).
    import yaml

    from codegen.manifest.schema import Manifest

    data = yaml.safe_load(_FIXTURE.read_text())
    create = next(c for c in data["application"]["commands"] if c["name"] == "CreateTicket")
    del create["log_event"]
    root = tmp_path / _PKG
    root.mkdir()
    (root / "__init__.py").write_text("")
    gen = Generator(Manifest.model_validate(data), root)  # no ValidationError → log_event optional
    gen.generate_domain()
    gen.generate_application()
    src = (root / "application/support/create_ticket_handler.py").read_text()
    assert "log_event" not in src  # no success-logging line in the contract


def test_update_dto_optional_fields_default_none(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "application/support/update_ticket_command.py")
    assert "title: str | None = None" in src
    assert "description: str | None = None" in src


def test_query_result_dto_written(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    login_result = _read(pkg, "application/auth/login_result.py")
    assert "class LoginResult:" in login_result and "token: str" in login_result
    ticket_list = _read(pkg, "application/support/ticket_list_result.py")
    assert "items: tuple[Ticket, ...]" in ticket_list and "total: int" in ticket_list


def test_single_dependency_handler_scaffold(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "application/support/create_ticket_handler.py")
    assert "def __init__(self, repo: ITicketRepository) -> None:" in src
    assert "async def execute(self, cmd: CreateTicketCommand) -> uuid.UUID:" in src
    assert 'log_event: "ticket_created"' in src
    assert 'raise NotImplementedError("CreateTicketHandler.execute")' in src


def test_multi_dependency_handler_injects_every_dep(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    # Login query: repository + capability
    login = _read(pkg, "application/auth/login_handler.py")
    assert "def __init__(self, repo: IUserRepository, manage_tokens: ICanManageTokens) -> None:" in login
    assert "self._repo = repo" in login and "self._manage_tokens = manage_tokens" in login
    assert "from hdkgen.domain.auth import ICanManageTokens, IUserRepository" in login
    # AssignTicket command: repository + domain service
    assign = _read(pkg, "application/support/assign_ticket_handler.py")
    assert (
        "def __init__(self, repo: ITicketRepository, ticket_assignment_service: TicketAssignmentService) -> None:"
        in assign
    )
    assert "from hdkgen.domain.support import ITicketRepository, TicketAssignmentService" in assign


def test_notes_prose_flows_into_the_contract(tmp_path: Path) -> None:
    # `notes` is the GUIDE channel: distilled prose intent rendered into the contract-
    # comment so the implementer doesn't infer the rule from the class name. CloseTicket's
    # status transition (status is not an input) is exactly the case that needs it.
    pkg, _ = _gen(tmp_path)
    close = _read(pkg, "application/support/close_ticket_handler.py")
    assert "# Close = load the ticket, set status to TicketStatus.CLOSED, then persist." in close
    assert "re-saving the ticket" in close  # multi-line prose preserved line-by-line
    # a query's notes flow too
    login = _read(pkg, "application/auth/login_handler.py")
    assert "# Password auth is out of scope for the pilot" in login
    # a domain service: service-WIDE note at class level + per-METHOD note in the method
    svc = _read(pkg, "domain/support/ticket_assignment_service.py")
    assert "# Stateless cross-aggregate policy" in svc  # Service.notes — once, class-level
    assert "# Load the user by assignee_id" in svc  # ServiceMethod.notes — per method


def test_notes_split_across_layers_and_granularity(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    # repository: SQL-specific note (infra adapter) at class level + the protocol's per-method
    # semantic note inside the `list` method.
    repo = _read(pkg, "infrastructure/postgres/repositories/ticket_repository.py")
    assert "# list: SQLAlchemy Core select(tickets_table)" in repo  # Repository.notes (infra)
    assert "# Filter by status when given (None → all statuses)." in repo  # ProtocolMethod.notes (domain)
    # capability: protocol semantic note + adapter SDK note at class level; verify per-method note
    cap = _read(pkg, "infrastructure/jwt/jwt_token_manager.py")
    assert "# A stateless bearer-token mint/verify pair" in cap  # CapabilityProtocol.notes (domain)
    assert "# PyJWT, HS256." in cap  # Capability.notes (infra, SDK-specific)
    assert "# Decode + validate the token" in cap  # ProtocolMethod.notes (per method)
    # endpoint: the rare non-1:1 response-assembly note
    auth_router = _read(pkg, "restapi/routers/auth.py")
    assert '# Map the result: access_token = result.token; token_type = "bearer".' in auth_router


def test_query_handler_is_read_only(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "application/support/list_tickets_handler.py")
    assert "async def execute(self, query: ListTicketsQuery) -> TicketListResult:" in src
    assert "# Read-only: never mutates, never logs a business event." in src
    assert "_CALLER" not in src and "log_event" not in src


# ── infrastructure: tables, settings, capability adapter, repositories ───────────


def test_table_is_scaffolded_with_field_contract(tmp_path: Path) -> None:
    # Tables are no longer transcribed from a Python→SQL type map (the old _SQL_CORE that
    # broke on any unforeseen type). Each postgres-store repository gets a write-once Table
    # SCAFFOLD: the SQLAlchemy Core skeleton + a contract-comment listing the entity's fields
    # and domain types; the implementer fills the column types/indexes/constraints (§3/§4).
    pkg, _ = _gen(tmp_path)
    ticket = _read(pkg, "infrastructure/postgres/tables/tickets.py")
    assert "from sqlalchemy import Table" in ticket
    assert 'tickets_table: Table = Table(\n    "tickets",\n    metadata,' in ticket
    assert "from ..metadata import metadata" in ticket
    # the contract names the backing fields + their domain types (the fill spec)
    assert "# Fields (domain types)" in ticket
    assert "status: TicketStatus" in ticket
    assert "assignee_id: UUID | None (nullable)" in ticket  # optional field flagged
    # audit timestamps stay a DB-managed convention the implementer adds (not a domain field)
    assert "created_at" not in _read(pkg, "domain/support/ticket.py")
    assert "server_default=now()" in ticket
    # no hardcoded SQL type mapping leaks into the scaffold (that is the implementer's body)
    assert "UUID(as_uuid=True)" not in ticket


def test_non_relational_store_gets_no_sql_table(tmp_path: Path) -> None:
    # A repository on a non-postgres datastore (vector_rag's Chunk → qdrant) gets NO
    # SQLAlchemy table; its collection setup is the store profile's concern, not a `Table`.
    from codegen.manifest.validator import load_and_validate

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, report = load_and_validate(vrag)
    assert report.ok, report.findings
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    # No tests_root: the canonical-test fake repo only knows CRUD verb conventions, not
    # this manifest's add_many/search (a separate fake-lattice limitation, deferred); the
    # storage path under test is the table scaffolds.
    Generator(manifest, pkg).generate_all()
    assert (pkg / "infrastructure/postgres/tables/documents.py").exists()  # Document → postgres
    assert not (pkg / "infrastructure/postgres/tables/chunks.py").exists()  # Chunk → qdrant


def test_reference_integrity_clean_on_both_fixtures(tmp_path: Path) -> None:
    # Regression guard: the three generator bugs vector_rag surfaced (settings collision, a
    # no-auth UnauthorizedError import, a cross-resource schema ref) must stay fixed — every
    # first-party import in the generated tree resolves, no undefined names.
    from codegen.generator.references import check_references

    _, hdk_tmp = _gen(tmp_path)
    hdk_refs = check_references(hdk_tmp, _PKG)
    assert hdk_refs.errors == [], [f.message for f in hdk_refs.errors]

    vrag_root = tmp_path / "vrag_root"
    vrag_root.mkdir()
    _gen_vrag(vrag_root)
    vrag_refs = check_references(vrag_root, "vrag")
    assert vrag_refs.errors == [], [f.message for f in vrag_refs.errors]


def test_reference_check_flags_unresolved_import_and_allows_submodule(tmp_path: Path) -> None:
    # The resolver flags an import of a symbol the target module does not export, but allows a
    # submodule import (`from pkg.sub import mod` where pkg/sub/mod.py exists) — the false
    # positive the inline probe had on `from <pkg>.domain import exceptions`.
    from codegen.generator.references import check_references

    pkg = tmp_path / "demo"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "sub" / "__init__.py").write_text("")
    (pkg / "sub" / "thing.py").write_text("VALUE = 1\n")
    (pkg / "user.py").write_text(
        "from demo.sub import thing\nfrom demo.sub.thing import VALUE\nfrom demo.sub.thing import GHOST\n"
    )
    report = check_references(tmp_path, "demo")
    msgs = [f.message for f in report.errors if f.code == "unresolved_import"]
    assert any("GHOST" in m for m in msgs)
    assert not any("thing" in m and "GHOST" not in m for m in msgs)  # submodule import not flagged
    assert not any("VALUE" in m for m in msgs)  # real symbol not flagged


def _gen_vrag(tmp_path: Path):
    from codegen.manifest.validator import load_and_validate

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, _ = load_and_validate(vrag)
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()
    return pkg


def test_error_handler_omits_auth_when_no_authenticated_endpoint(tmp_path: Path) -> None:
    # vector_rag is all-anonymous → UnauthorizedError never joins the catalog, so the error
    # handler must NOT import or branch on it (that import was broken). helpdesk (authed) keeps it.
    vrag_handler = (_gen_vrag(tmp_path) / "restapi/error_handler.py").read_text()
    assert "UnauthorizedError" not in vrag_handler
    assert "WWW-Authenticate" not in vrag_handler
    assert "from vrag.domain.exceptions import DomainError\n" in vrag_handler

    hdk_root = tmp_path / "hdk_root"
    hdk_root.mkdir()
    hdk, _ = _gen(hdk_root)
    authed_handler = (hdk / "restapi/error_handler.py").read_text()
    assert "import DomainError, UnauthorizedError" in authed_handler  # auth app keeps the 401 branch
    assert "WWW-Authenticate" in authed_handler


def test_schema_cross_resource_reference_is_imported(tmp_path: Path) -> None:
    # A schema field referencing a schema in ANOTHER resource file must import it from the
    # sibling module (was an undefined-name bug). Self-contained synthetic manifest so the
    # test does not depend on a fixture's evolving shape.
    from codegen.manifest.schema import Manifest

    m = Manifest.model_validate(
        {
            "meta": {"epic": "x", "name": "x", "sources": []},
            "restapi": {
                "schemas": [
                    {
                        "name": "Hit",
                        "resource": "search",
                        "kind": "response",
                        "fields": [{"name": "id", "type": "UUID"}],
                        "sources": [],
                    },
                    {
                        "name": "Wrap",
                        "resource": "rag",
                        "kind": "response",
                        "fields": [{"name": "items", "type": "Sequence[Hit]"}],
                        "sources": [],
                    },
                ]
            },
        }
    )
    pkg = tmp_path / "demo"
    pkg.mkdir()
    Generator(m, pkg).generate_restapi_schemas()
    rag = (pkg / "restapi/schemas/rag.py").read_text()
    assert "from .search import Hit" in rag  # cross-resource reference imported
    assert "items: Sequence[Hit]" in rag
    search = (pkg / "restapi/schemas/search.py").read_text()
    assert "from .search import" not in search  # same-resource ref stays local, no self-import


def test_pure_service_without_deps_has_no_empty_init(tmp_path: Path) -> None:
    # A stateless `pure` domain service with no dependencies (vector_rag's ChunkingService)
    # must not emit `def __init__(self) -> None:` with an empty body — that was an
    # IndentationError. It gets no constructor at all; the method body is still scaffolded.
    import py_compile

    from codegen.manifest.validator import load_and_validate

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, _ = load_and_validate(vrag)
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()
    svc_path = pkg / "domain/corpus/chunking_service.py"
    svc = svc_path.read_text()
    assert "def __init__" not in svc  # no constructor for a depless service
    assert "def split(self, text: str) -> list[str]:" in svc
    assert 'raise NotImplementedError("ChunkingService.split")' in svc
    py_compile.compile(str(svc_path), doraise=True)  # would have raised IndentationError before


def test_settings_with_method_is_a_scaffold(tmp_path: Path) -> None:
    # A settings class may declare methods (a derived value like a DSN). The fields stay
    # declarative; each method is a SCAFFOLD — stacked decorators + signature + contract +
    # NotImplementedError — exactly like an enum with methods or an entity invariant. The
    # house style for a derived value is the two-stack `@computed_field @property`.
    import py_compile

    from codegen.manifest.schema import Manifest

    payload = {
        "meta": {"epic": "x", "name": "x", "sources": []},
        "infrastructure": {
            "settings": [
                {
                    "name": "DbSettings",
                    "env_prefix": "DB_",
                    "fields": [
                        {"name": "host", "type": "str", "default": '"localhost"'},
                        {"name": "password", "type": "SecretStr", "secret": True},
                    ],
                    "methods": [
                        {
                            "signature": "def dsn(self) -> str",
                            "decorators": ["computed_field", "property"],
                            "notes": "Compose the postgresql+asyncpg URL from the fields.",
                        }
                    ],
                    "sources": [],
                }
            ]
        },
    }
    manifest = Manifest.model_validate(payload)
    gen = Generator(manifest, tmp_path / "app")
    src = gen._render_settings(manifest.infrastructure.settings[0])

    # decorators render stacked, computed_field outermost (above property)
    assert src.index("@computed_field") < src.index("@property")
    assert "def dsn(self) -> str:" in src
    assert 'raise NotImplementedError("DbSettings.dsn")' in src
    assert "# Compose the postgresql+asyncpg URL from the fields." in src  # notes → contract
    # imports: pydantic carries SecretStr (secret field) + computed_field (the decorator)
    assert "from pydantic import SecretStr, computed_field" in src
    assert "from pydantic_settings import BaseSettings, SettingsConfigDict" in src
    # fields stay declarative
    assert 'host: str = "localhost"' in src and "password: SecretStr" in src

    out = tmp_path / "db_settings.py"
    out.write_text(src)
    py_compile.compile(str(out), doraise=True)


def test_query_result_dtos_nest_a_helper_read_model(tmp_path: Path) -> None:
    # #3: a query declares a helper read-model DTO (SearchHit{chunk, score}) that its main
    # *Result references — the nested read-model the flat result_fields couldn't carry.
    pkg = _gen_vrag(tmp_path)
    hit = _read(pkg, "application/corpus/search_hit.py")
    assert "class SearchHit:" in hit
    assert "chunk: Chunk" in hit and "score: float" in hit
    assert "from vrag.domain.corpus import Chunk" in hit  # field type → domain import
    result = _read(pkg, "application/corpus/search_result.py")
    assert "items: tuple[SearchHit, ...]" in result
    assert "from .search_hit import SearchHit" in result  # sibling read-DTO → local import


def test_same_resource_schema_topological_order(tmp_path: Path) -> None:
    # A schema referencing another in the SAME module is defined AFTER it (no __future__
    # annotations → forward refs would be undefined). ChunkHitResponse{chunk: ChunkResponse}.
    pkg = _gen_vrag(tmp_path)
    search = _read(pkg, "restapi/schemas/search.py")
    assert search.index("class ChunkResponse") < search.index("class ChunkHitResponse")
    assert search.index("class ChunkHitResponse") < search.index("class SearchResponse")


def test_multipart_endpoint_signature_and_dependency(tmp_path: Path) -> None:
    # #4: request_kind=multipart derives an UploadFile + Form signature from the command's
    # inputs (bytes → file), no JSON body; python-multipart lands in pyproject.
    pkg = _gen_vrag(tmp_path)
    router = _read(pkg, "restapi/routers/documents.py")
    assert "from fastapi import APIRouter, File, Form, Request, UploadFile" in router
    assert "file: UploadFile = File(...)" in router  # the bytes input → the uploaded file
    assert "title: str = Form(...)" in router  # other inputs → multipart form fields
    # (the sibling JSON endpoint IngestText keeps its `body: IngestTextRequest` — multipart is
    # per-endpoint, not per-router; the multipart route itself takes no JSON body.)
    toml = (tmp_path / "pyproject.toml").read_text()
    assert "python-multipart" in toml  # FastAPI Form/File parsing needs it (graph-derived dep)


def test_pyproject_unions_base_stack_with_node_packages(tmp_path: Path) -> None:
    # pyproject = the fixed framework substrate plus the SDK packages declared on infra nodes
    # (§10), at the project root (the package's parent). Helpdesk's jwt capability pulls PyJWT.
    _, tmp = _gen(tmp_path)
    toml = (tmp / "pyproject.toml").read_text()
    assert f'name = "{_PKG}"' in toml
    assert '"fastapi>=0.115"' in toml  # base substrate
    assert '"sqlalchemy[asyncio]>=2.0"' in toml
    assert '"pyjwt>=2.8"' in toml  # capability-declared SDK, unioned from the graph
    assert "[dependency-groups]" in toml and '"mypy>=1.10"' in toml


def test_pyproject_collects_polyglot_packages(tmp_path: Path) -> None:
    # vector_rag pulls its datastore driver (qdrant-client) AND its capability SDKs
    # (openai, pypdf, python-docx), deduped, on top of the base stack.
    from codegen.manifest.validator import load_and_validate

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, _ = load_and_validate(vrag)
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()
    toml = (tmp_path / "pyproject.toml").read_text()
    assert '"qdrant-client>=1.9"' in toml  # datastore driver
    assert '"openai>=1.30"' in toml  # capability SDK (declared twice, deduped)
    assert toml.count('"openai>=1.30"') == 1
    assert '"pypdf>=4.2"' in toml and '"python-docx>=1.1"' in toml


def test_non_relational_app_emits_no_postgres_substrate(tmp_path: Path) -> None:
    # A pure non-relational app (a qdrant repo, no postgres store) must NOT get the SQLAlchemy
    # bootstrap: no infrastructure/postgres/ package, no metadata.py, no engine/session_factory in
    # the container, and no sqlalchemy/asyncpg/alembic in pyproject. The relational substrate is
    # gated on a relational store actually backing a repository.
    from codegen.manifest.schema import Manifest

    payload = {
        "meta": {"epic": "x", "name": "x", "sources": []},
        "domain": {
            "entities": [
                {"name": "Doc", "subdomain": "corpus", "fields": [{"name": "id", "type": "UUID"}], "sources": []}
            ],
            "repository_protocols": [
                {
                    "name": "IDocRepository",
                    "subdomain": "corpus",
                    "aggregate": "Doc",
                    "methods": ["async def add(self, doc: Doc) -> None"],
                    "sources": [],
                }
            ],
        },
        "infrastructure": {
            "settings": [
                {
                    "name": "QSettings",
                    "env_prefix": "Q_",
                    "fields": [{"name": "url", "type": "str", "default": '"x"'}],
                    "sources": [],
                }
            ],
            "datastores": [
                {
                    "name": "vectors",
                    "kind": "qdrant",
                    "settings": "QSettings",
                    "requires_packages": ["qdrant-client>=1.9"],
                    "sources": [],
                }
            ],
            "repositories": [{"implements": "IDocRepository", "backs": "Doc", "store": "vectors", "sources": []}],
        },
    }
    manifest = Manifest.model_validate(payload)
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()

    assert not (pkg / "infrastructure" / "postgres").exists()  # no postgres subpackage at all
    toml = (tmp_path / "pyproject.toml").read_text()
    assert "sqlalchemy" not in toml and "asyncpg" not in toml and "alembic" not in toml
    assert '"qdrant-client>=1.9"' in toml  # the datastore driver is still unioned in
    container = (pkg / "containers.py").read_text()
    assert "session_factory" not in container and "create_engine" not in container


def test_schema_drift_flags_unfilled_and_clears_when_filled(tmp_path: Path) -> None:
    # The deterministic §4 trigger: a freshly scaffolded table has no columns, so every
    # entity field is "missing" → drift (wakes the implementer). Filling the columns clears
    # it; removing one re-opens drift for that field. Extra columns (audit) are allowed.
    from codegen.generator.drift import check_schema_drift

    manifest, _ = load_and_validate(_FIXTURE)
    pkg, _ = _gen(tmp_path)

    fresh = check_schema_drift(manifest, pkg)
    assert any(f.code == "schema_drift" and "tickets" in f.message for f in fresh.warnings)

    # simulate the implementer filling the tickets table with every entity field + audit
    fields = [f.name for f in next(e for e in manifest.domain.entities if e.name == "Ticket").fields]
    cols = "\n".join(f'    Column("{name}", Text)' for name in [*fields, "created_at", "updated_at"])
    table_file = pkg / "infrastructure/postgres/tables/tickets.py"
    table_file.write_text(f"from sqlalchemy import Column, Table\n\ntickets_table = Table(\n{cols}\n)\n")
    filled = check_schema_drift(manifest, pkg)
    assert all(not (f.code == "schema_drift" and "tickets" in f.message) for f in filled.warnings)

    # drop a column → drift re-opens naming the missing field (the brownfield-delta case)
    table_file.write_text('from sqlalchemy import Column, Table\n\ntickets_table = Table(\n    Column("id", Text)\n)\n')
    drifted = check_schema_drift(manifest, pkg)
    assert any(f.code == "schema_drift" and "title" in f.message for f in drifted.warnings)


def test_schema_drift_skips_non_relational_store(tmp_path: Path) -> None:
    # a qdrant-backed entity has no SQLAlchemy table → it is never a schema-drift candidate.
    from codegen.generator.drift import check_schema_drift

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, _ = load_and_validate(vrag)
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()
    report = check_schema_drift(manifest, pkg)
    assert any("Document" in f.message for f in report.warnings)  # postgres → checked (unfilled)
    assert all("Chunk" not in f.message for f in report.warnings)  # qdrant → skipped


def test_repository_is_store_aware(tmp_path: Path) -> None:
    # The repo scaffold + DI wiring follow the store profile (variant B): the postgres repo
    # injects a session_factory; the qdrant repo injects a QdrantClient. The generator never
    # hardcodes a single backend.
    from codegen.manifest.validator import load_and_validate

    vrag = Path(__file__).resolve().parents[1] / "examples" / "vector_rag_manifest.yaml"
    manifest, _ = load_and_validate(vrag)
    pkg = tmp_path / "vrag"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    Generator(manifest, pkg).generate_all()

    chunk_repo = _read(pkg, "infrastructure/qdrant/repositories/chunk_repository.py")
    assert "from qdrant_client import QdrantClient" in chunk_repo
    assert "def __init__(self, client: QdrantClient)" in chunk_repo
    assert "async_sessionmaker" not in chunk_repo  # no postgres leak
    assert "qdrant adapter" in chunk_repo  # contract style, not "SQLAlchemy Core"

    doc_repo = _read(pkg, "infrastructure/postgres/repositories/document_repository.py")
    assert "def __init__(self, session_factory: async_sessionmaker[AsyncSession])" in doc_repo

    # the qdrant connection factory is scaffolded; the container injects its client Singleton
    conn = _read(pkg, "infrastructure/qdrant/connection.py")
    assert "def create_vectors_client(settings: QdrantSettings) -> QdrantClient:" in conn
    container = _read(pkg, "containers.py")
    assert "vectors_client: providers.Provider[QdrantClient] = providers.Singleton(" in container
    assert "create_vectors_client, settings=qdrant_settings" in container
    assert "client=vectors_client" in container  # chunk repo wired to the qdrant client


def test_settings_generated(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    # one settings class per module, named after the class (jwt_settings.py, not settings.py)
    src = _read(pkg, "infrastructure/jwt/jwt_settings.py")
    assert "class JwtSettings(BaseSettings):" in src
    assert 'env_prefix="HELPDESK_JWT_"' in src
    assert "secret: SecretStr" in src  # secret → SecretStr, no default
    assert 'algorithm: str = "HS256"' in src
    assert "ttl_seconds: int = 3600" in src


def test_capability_adapter_scaffold(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "infrastructure/jwt/jwt_token_manager.py")
    assert "class JwtTokenManager:" in src  # <Adapter><Verb>, structural (no inheritance)
    assert "def __init__(self, settings: JwtSettings) -> None:" in src
    assert "from .jwt_settings import JwtSettings" in src
    assert "from hdkgen.domain.auth import CurrentUser" in src
    assert "def issue(self, principal: CurrentUser) -> str:" in src
    assert 'raise NotImplementedError("JwtTokenManager.issue")' in src
    assert "import jwt" not in src  # the SDK import is the implementer's


def test_repository_scaffold_imports_domain_types_not_protocol(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "infrastructure/postgres/repositories/user_repository.py")
    assert "class UserRepository:" in src
    # imports the aggregate + the Email referenced in get_by_email — but NOT the protocol
    assert "from hdkgen.domain.auth import Email, User" in src
    assert "IUserRepository" not in src  # structural subtyping; no protocol import
    assert "async def get_by_email(self, email: Email) -> User:" in src


# ── composition root: DI container ───────────────────────────────────────────────


def test_container_wires_every_provider_kind(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "containers.py")
    # settings → Singleton; capability → Singleton wired to its settings
    assert "jwt_settings: providers.Provider[JwtSettings] = providers.Singleton(JwtSettings)" in src
    assert "manage_tokens: providers.Provider[ICanManageTokens] = providers.Singleton(" in src
    assert "JwtTokenManager, settings=jwt_settings" in src
    # service → Factory wired to its (cross-subdomain) repository
    assert "ticket_assignment_service: providers.Provider[TicketAssignmentService] = providers.Factory(" in src
    assert "TicketAssignmentService, repo=user_repository" in src
    # multi-dependency handlers wire each dependency by name
    assert "LoginHandler, repo=user_repository, manage_tokens=manage_tokens" in src
    assert "AssignTicketHandler, repo=ticket_repository, ticket_assignment_service=ticket_assignment_service" in src


def test_container_imports_and_builds(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    mod = _fresh_import(tmp, f"{_PKG}.containers")
    for attr in ("jwt_settings", "manage_tokens", "ticket_assignment_service", "login_handler", "get_ticket_handler"):
        assert hasattr(mod.Container, attr), attr


# ── REST API: bootstrap, derived dependencies, schemas, routers ──────────────────


def test_bootstrap_writes_no_hardcoded_auth_files(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    # the generic boilerplate is written
    for rel in ("restapi/error_handler.py", "restapi/schemas/errors.py", "restapi/dependencies.py"):
        assert (pkg / rel).is_file(), rel
    # role/current_user are NOT written by the bootstrap into a hardcoded location —
    # they are ordinary domain nodes generated under their subdomain.
    assert (pkg / "domain/auth/role.py").is_file()
    assert (pkg / "domain/auth/current_user.py").is_file()


def test_dependencies_render_require_role(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    deps = _read(pkg, "restapi/dependencies.py")
    assert "def require_role(required: Role) -> Callable[..., CurrentUser]:" in deps
    assert "if not user.role.satisfies(required):" in deps


def test_schema_patch_semantics(tmp_path: Path) -> None:
    pkg, _tmp = _gen(tmp_path)
    spec = importlib.util.spec_from_file_location("_t_schemas", pkg / "restapi/schemas/tickets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.TicketUpdateRequest().title is None  # PATCH: every field optional
    from pydantic import ValidationError as PydErr

    with pytest.raises(PydErr):
        mod.TicketCreateRequest()  # required inputs


def test_anonymous_login_route_has_no_auth_dependency(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "restapi/routers/auth.py")
    assert "async def login(" in src
    assert "Depends" not in src  # anonymous → no auth dependency at all
    assert "CurrentUser" not in src
    assert "status_code=201" in src
    assert "responses=error_responses(401, 403)" in src  # from the handler's raises


def test_router_action_subpaths_and_role_gates(tmp_path: Path) -> None:
    pkg, _ = _gen(tmp_path)
    src = _read(pkg, "restapi/routers/tickets.py")
    # action sub-paths below the resource prefix are emitted verbatim
    assert '"/{ticket_id}/assign",' in src
    assert '"/{ticket_id}/close",' in src
    # role gates use the manifest Role enum members
    assert "Depends(require_role(Role.AGENT))" in src
    assert "Depends(require_role(Role.ADMIN))" in src
    # an authenticated mutation binds `user` (caller_id flows); a read binds `_`
    assert "user: CurrentUser = Depends(get_current_user)," in src  # create (authenticated command)
    assert "_: CurrentUser = Depends(get_current_user)," in src  # list/get (reads)
    # a domain-enum query param is imported + typed
    assert "from hdkgen.domain.support import TicketStatus" in src
    assert "status: Annotated[TicketStatus | None, Query()] = None" in src


def test_routers_and_main_import_cleanly(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    _fresh_import(tmp, f"{_PKG}.restapi.routers.tickets")
    _fresh_import(tmp, f"{_PKG}.restapi.routers.auth")
    main = _fresh_import(tmp, f"{_PKG}.restapi.main")
    assert hasattr(main, "create_app")


# ── test artifacts: fakes, canonical flat/manual split, reference-body proofs ────


def test_fakes_written_with_lookup_convention(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    assert (tmp / "tests/unit/fakes/fake_user_repository.py").is_file()
    assert (tmp / "tests/unit/fakes/fake_ticket_repository.py").is_file()
    src = (tmp / "tests/unit/fakes/fake_user_repository.py").read_text()
    assert "async def get_by_email(self, email: Email) -> User:" in src  # get_by_<field> convention
    assert "if item.email == email:" in src


def test_flat_and_manual_test_split(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    app = tmp / "tests/unit/application"
    # single-repository, flat scenarios → generated flat tests
    for verb in ("delete", "get", "update", "close", "create"):
        assert (app / f"test_{verb}_ticket_handler.py").is_file(), verb
    # multi-dependency handlers → write-once manual stubs (no generated flat file)
    assert not (app / "test_login_handler.py").exists()
    assert (app / "test_login_handler_manual.py").is_file()
    assert not (app / "test_assign_ticket_handler.py").exists()
    assert (app / "test_assign_ticket_handler_manual.py").is_file()
    # ListTickets is non-flat (returns a *Result aggregate) → manual stub
    assert (app / "test_list_tickets_handler_manual.py").is_file()


def test_fake_repository_behaves(tmp_path: Path) -> None:
    _pkg, tmp = _gen(tmp_path)
    sys.path.insert(0, str(tmp))
    try:
        for m in [m for m in list(sys.modules) if m == _PKG or m.startswith(f"{_PKG}.")]:
            del sys.modules[m]
        support = importlib.import_module(f"{_PKG}.domain.support")
        exc = importlib.import_module(f"{_PKG}.domain.exceptions")
        spec = importlib.util.spec_from_file_location(
            "_fake_ticket_repo", tmp / "tests/unit/fakes/fake_ticket_repository.py"
        )
        fake_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fake_mod)
        repo = fake_mod.FakeTicketRepository()
        ticket = support.Ticket(id=uuid4(), title="t", description="d", reporter_id=uuid4())
        asyncio.run(repo.add(ticket))
        assert asyncio.run(repo.get_by_id(ticket.id)).id == ticket.id
        asyncio.run(repo.delete(ticket.id))
        with pytest.raises(exc.NotFoundError):
            asyncio.run(repo.get_by_id(ticket.id))
    finally:
        sys.path.remove(str(tmp))


def test_generated_flat_test_goes_green_with_a_reference_body(tmp_path: Path) -> None:
    # §9/§12 proof: the generated canonical test is RED against the scaffold by design.
    # Hand-fill ONE reference handler body and the generated arrange/act→assert binding
    # must go GREEN. Generation happens under tmp_path; it never commits a filled body.
    pkg, tmp = _gen(tmp_path)
    handler = pkg / "application/support/delete_ticket_handler.py"
    handler.write_text(
        "from uuid import UUID\n\n"
        f"from {_PKG}.domain.support import ITicketRepository\n\n"
        "from .delete_ticket_command import DeleteTicketCommand\n\n"
        '__all__ = ["DeleteTicketHandler"]\n\n\n'
        "class DeleteTicketHandler:\n"
        "    def __init__(self, repo: ITicketRepository) -> None:\n"
        "        self._repo = repo\n\n"
        "    async def execute(self, cmd: DeleteTicketCommand) -> None:\n"
        "        await self._repo.get_by_id(cmd.ticket_id)\n"
        "        await self._repo.delete(cmd.ticket_id)\n"
    )
    for marker in ("tests", "tests/unit", "tests/unit/fakes", "tests/unit/application"):
        (tmp / marker / "__init__.py").write_text("")
    (tmp / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).parent))\n"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(tmp / "tests/unit/application/test_delete_ticket_handler.py"),
            "-p",
            "asyncio",
            "--asyncio-mode=auto",
            "-q",
        ],
        cwd=tmp,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout


def test_persists_with_makes_a_no_op_implementation_fail(tmp_path: Path) -> None:
    # The VERIFY half (§A): `then: {persists: Ticket, with: {status: CLOSED}}` makes the
    # generated test assert the post-state. A correct close goes GREEN; a no-op
    # "re-save unchanged" body goes RED — exactly the footgun a bare `persists` missed.
    pkg, tmp = _gen(tmp_path)
    close_test = tmp / "tests/unit/application/test_close_ticket_handler.py"
    assert "assert stored.status == TicketStatus.CLOSED" in close_test.read_text()

    for marker in ("tests", "tests/unit", "tests/unit/fakes", "tests/unit/application"):
        (tmp / marker / "__init__.py").write_text("")
    (tmp / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).parent))\n"
    )
    handler = pkg / "application/support/close_ticket_handler.py"
    head = (
        "from uuid import UUID  # noqa: F401\n\n"
        f"from {_PKG}.domain.support import ITicketRepository, TicketStatus  # noqa: F401\n\n"
        "from .close_ticket_command import CloseTicketCommand\n\n"
        '__all__ = ["CloseTicketHandler"]\n\n\n'
        "class CloseTicketHandler:\n"
        "    def __init__(self, repo: ITicketRepository) -> None:\n"
        "        self._repo = repo\n\n"
        "    async def execute(self, cmd: CloseTicketCommand) -> None:\n"
        "        ticket = await self._repo.get_by_id(cmd.ticket_id)\n"
    )

    def _run():
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(close_test), "-p", "asyncio", "--asyncio-mode=auto", "-q"],
            cwd=tmp,
            capture_output=True,
            text=True,
        )

    # correct: the transition happens → GREEN
    handler.write_text(head + "        ticket.status = TicketStatus.CLOSED\n        await self._repo.update(ticket)\n")
    ok = _run()
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "2 passed" in ok.stdout

    # no-op: re-save unchanged → the post-state assert fails (RED)
    handler.write_text(head + "        await self._repo.update(ticket)\n")
    bad = _run()
    assert bad.returncode != 0
    assert "status" in bad.stdout  # the failing assertion is the post-state check


def test_value_object_invariant_enforced_when_filled(tmp_path: Path) -> None:
    # The Email __post_init__ scaffold is RED by design; fill it and the invariant holds.
    pkg, tmp = _gen(tmp_path)
    email_py = pkg / "domain/auth/email.py"
    email_py.write_text(
        email_py.read_text().replace(
            'raise NotImplementedError("Email.__post_init__")',
            'if "@" not in self.value:\n            raise ValidationError("invalid email", {"field": "value"})',
        )
    )
    mod = _fresh_import(tmp, f"{_PKG}.domain.auth.email")
    exc = importlib.import_module(f"{_PKG}.domain.exceptions")
    mod.Email(value="a@b.com")  # valid → no raise
    with pytest.raises(exc.ValidationError) as ei:
        mod.Email(value="nope")
    assert ei.value.context["field"] == "value"


# ── file ownership + lint ────────────────────────────────────────────────────────


def test_scaffold_write_once_but_declarative_regenerated(tmp_path: Path) -> None:
    manifest, report = load_and_validate(_FIXTURE)
    assert report.ok
    pkg = tmp_path / _PKG
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    gen = Generator(manifest, pkg)
    gen.generate_domain()
    gen.generate_application()

    scaffold = pkg / "application/support/create_ticket_handler.py"
    declarative = pkg / "application/support/create_ticket_command.py"
    sentinel = "    # IMPLEMENTER-OWNED\n"
    scaffold.write_text(scaffold.read_text() + sentinel)
    declarative.write_text("# stale\n")

    gen.generate_domain()
    gen.generate_application()

    assert sentinel in scaffold.read_text()  # scaffold survived
    assert "stale" not in declarative.read_text()  # declarative regenerated
    assert "class CreateTicketCommand" in declarative.read_text()


def test_declarative_and_glue_files_pass_ruff(tmp_path: Path) -> None:
    pkg, tmp = _gen(tmp_path)
    candidates = [p for p in pkg.rglob("*.py") if p.name != "__init__.py"]
    candidates += list((tmp / "tests").rglob("*.py"))
    declarative = [p for p in candidates if not _is_scaffold(p)]
    result = _ruff(declarative)
    if result is None:
        return  # ruff not on PATH in this runner
    assert result.returncode == 0, result.stdout + result.stderr


def test_all_generated_python_compiles(tmp_path: Path) -> None:
    import py_compile

    pkg, tmp = _gen(tmp_path)
    for p in list(pkg.rglob("*.py")) + list((tmp / "tests").rglob("*.py")):
        py_compile.compile(str(p), doraise=True)
