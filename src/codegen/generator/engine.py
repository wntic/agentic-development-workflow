"""Forward generator — scaffold-first (spec §3 / §4).

Walks the manifest graph and emits two kinds of file, split BY FILE (§4):

  * Declarative + glue — a transcription of the manifest/graph, written by Jinja2
    with NO LLM and ALWAYS overwritten on regeneration (idempotent). Covers the
    domain (entity shells, repository protocols, the exception
    catalog), application DTOs, infrastructure tables + Alembic migrations, the DI
    container, REST schemas + bootstrap, route registration in main.py, every
    `__init__.py` re-export, and the test fakes.

  * Body-bearing scaffolds — a `class + __init__ + method signature(s) + contract-
    type imports from the graph + a contract-comment (the implementer's spec) +
    raise NotImplementedError`. Emitted ONCE and NEVER overwritten (the implementer
    LLM owns the file; contract drift surfaces as red mypy, §4). Covers application
    command/query handlers, the SQLAlchemy repositories, and the REST endpoint
    functions.

There is no generate-vs-scaffold field in the manifest — the choice is derived
from the node category (spec §3, §5). Output paths are derived (naming.py); the
scaffold's contract-type imports are derived from the graph (imports.py, §3).
"""

import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from jinja2 import Environment, FileSystemLoader

from ..manifest.schema import (
    Capability,
    CapabilityProtocol,
    Command,
    Entity,
    Enum,
    Manifest,
    Query,
    RepositoryProtocol,
    Service,
    Settings,
    ValueObject,
)
from . import naming
from .imports import (
    _STDLIB,
    dataclass_domain_import_block,
    dto_import_block,
    protocol_import_block,
    type_tokens,
)
from .store_profiles import StoreProfile, kind_of, profile_for

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# The fixed house-style runtime substrate every generated app needs (the FastAPI hexagon's
# framework stack). NOT anticipation — it is the architecture itself. Third-party SDK
# packages are NOT here; they ride on the infra node that needs them (datastore/capability
# `requires_packages`) and are unioned in from the graph (§10). The SQLAlchemy/asyncpg/
# alembic trio sits in the base because the persistence bootstrap (db_engine/containers) is
# still emitted unconditionally; move it per-postgres-store once that becomes conditional.
_BASE_DEPENDENCIES = (
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "dependency-injector>=4.41",
    "structlog>=24.1",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
)
_DEV_DEPENDENCIES = (
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "mypy>=1.10",
    "testcontainers>=4.5",
    "httpx>=0.27",
)

# §8 scaffold: package-agnostic reference-app files copied verbatim into the
# target (NOT generated from the manifest). See codegen/scaffold/README.md.
_SCAFFOLD = Path(__file__).resolve().parent.parent / "scaffold"


# App-bootstrap boilerplate that is NOT manifest-derived ({{PKG}} → import root).
# The auth artifacts (Role enum, CurrentUser VO, the token-verifying capability) are
# NO LONGER hardcoded here — they are ordinary manifest nodes the generator emits from
# domain.enums / domain.value_objects / infrastructure.capabilities. `restapi/
# dependencies.py` (get_current_user / require_role) is DERIVED from those nodes by
# `_render_dependencies` when the manifest exposes authenticated endpoints.
_ERROR_HANDLER_PY = """from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from {{PKG}}.domain.exceptions import DomainError, UnauthorizedError

from .schemas.errors import ErrorResponse

__all__ = ["register_error_handlers"]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers: dict[str, str] = {}
        if isinstance(exc, UnauthorizedError):
            headers["WWW-Authenticate"] = 'Bearer realm="{{PKG}}"'
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                code=exc.code,
                message=str(exc),
                context=exc.context,
            ).model_dump(),
            headers=headers or None,
        )
"""

# No-auth variant: a manifest with only anonymous endpoints never declares UnauthorizedError
# (it joins the catalog only for an authenticated route), so the handler must NOT import it or
# branch on it — else the import breaks (the vector_rag bug). Chosen by `_has_authenticated_endpoint`.
_ERROR_HANDLER_NOAUTH_PY = """from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from {{PKG}}.domain.exceptions import DomainError

from .schemas.errors import ErrorResponse

__all__ = ["register_error_handlers"]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=ErrorResponse(
                code=exc.code,
                message=str(exc),
                context=exc.context,
            ).model_dump(),
        )
"""

_ERRORS_SCHEMA_PY = """from pydantic import BaseModel, Field

from {{PKG}}.domain import exceptions as _domain_exceptions
from {{PKG}}.domain.exceptions import DomainError

__all__ = ["MIDDLEWARE_ERRORS", "ErrorResponse", "error_responses"]


class ErrorResponse(BaseModel):
    code: str
    message: str
    context: dict[str, object] = Field(default_factory=dict)


MIDDLEWARE_ERRORS: dict[str, int] = {
    "PAYLOAD_TOO_LARGE": 413,
}

_DESCR: dict[int, str] = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    422: "Unprocessable entity",
}


def _all_known_statuses() -> set[int]:
    domain_statuses: set[int] = set()
    for name in _domain_exceptions.__all__:
        cls = getattr(_domain_exceptions, name)
        if isinstance(cls, type) and issubclass(cls, DomainError):
            domain_statuses.add(cls.http_status)
    return domain_statuses | set(MIDDLEWARE_ERRORS.values())


def error_responses(*codes: int) -> dict[int, dict[str, object]]:
    known = _all_known_statuses()
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise ValueError(f"HTTP statuses not produced by any DomainError or middleware: {unknown}")
    return {c: {"model": ErrorResponse, "description": _DESCR.get(c, str(c))} for c in codes}
"""


def _base_type(annotation: str) -> str:
    return annotation.split("|")[0].strip()


def _method_name(signature: str) -> str:
    """The method name out of a `(async )def <name>(...)` signature string."""
    return re.match(r"(?:async\s+)?def\s+(\w+)", signature).group(1)


def _import_from(module: str, names) -> str:
    """A `from module import …` line, wrapped to the parenthesized multi-line form
    (one name per line, trailing comma) when the single line would exceed 99 cols."""
    ordered = sorted(names)
    single = f"from {module} import {', '.join(ordered)}"
    if len(single) <= 99:
        return single
    body = "".join(f"    {n},\n" for n in ordered)
    return f"from {module} import (\n{body})"


def _init_body(modules: list[str]) -> str:
    """Wildcard re-exports + `__all__` concat (general-python-package contract).

    F403/F405 on the star imports are silenced by the target project's
    `[tool.ruff.lint.per-file-ignores] "__init__.py"` config (bootstrap, §8).
    """
    imports = "\n".join(f"from .{mod} import *" for mod in modules)
    if len(modules) == 1:
        all_block = f"__all__ = {modules[0]}.__all__"
    else:
        joined = "\n    + ".join(f"{mod}.__all__" for mod in modules)
        all_block = f"__all__ = (\n    {joined}\n)"
    return f"{imports}\n\n{all_block}\n"


class Generator:
    def __init__(self, manifest: Manifest, out_root: str | Path, package: str | None = None) -> None:
        self.m = manifest
        self.root = Path(out_root)
        # import root for absolute application-layer imports (the generated package);
        # defaults to the output package directory name.
        self.package = package or self.root.name
        self.env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        self.entity_subdomains = {e.name: e.subdomain for e in manifest.domain.entities}
        # The symbol table: every NAMED domain type (entity, enum, value object) → the
        # subdomain package that owns it. Drives every import edge (imports.py).
        self.domain_subdomains = {
            **{e.name: e.subdomain for e in manifest.domain.entities},
            **{en.name: en.subdomain for en in manifest.domain.enums},
            **{vo.name: vo.subdomain for vo in manifest.domain.value_objects},
        }
        # Port name → subdomain, for resolving handler/service dependency imports
        # (repository protocols, capability protocols, services).
        self.port_subdomains = {
            **{p.name: p.subdomain for p in manifest.domain.repository_protocols},
            **{c.name: c.subdomain for c in manifest.domain.capability_protocols},
            **{s.name: s.subdomain for s in manifest.domain.services},
        }
        # A command carries the acting principal (caller_id) iff it is reachable through a
        # non-anonymous endpoint (derived, not a house rule): a public/no-auth app gets no
        # caller_id. This is the set of handler names a non-anonymous endpoint dispatches.
        self._authed_handlers = {e.handler for e in manifest.restapi.endpoints if e.auth != "anonymous"}

    def _command_has_caller(self, command: Command) -> bool:
        return command.name in self._authed_handlers

    def generate_all(self, *, tests_root: str | Path | None = None) -> list[Path]:
        """Run every layer in dependency order — the whole hexagon from one manifest."""
        written = self.generate_domain()
        written += self.generate_application()
        written += self.generate_infrastructure()
        written += self.generate_container()
        written += self.generate_restapi_schemas()
        written += self.generate_restapi_bootstrap()
        written += self.generate_restapi_routers()
        written.append(self.generate_pyproject())
        if tests_root is not None:
            written += self.generate_fakes(tests_root)
            written += self.generate_application_tests(tests_root)
            written += self.generate_domain_tests(tests_root)
        return written

    def generate_pyproject(self) -> Path:
        """pyproject.toml = the fixed framework substrate plus the third-party SDK packages
        declared on infra nodes (datastore/capability `requires_packages`), unioned by the
        graph (§10) — never 'an agent recalls a package'. Written at the project root (the
        package's parent), alongside the package and tests."""
        extra: set[str] = set()
        for ds in self.m.infrastructure.datastores:
            extra.update(ds.requires_packages)
        for cap in self.m.infrastructure.capabilities:
            extra.update(cap.requires_packages)
        # A multipart endpoint needs python-multipart (FastAPI parses Form/File through it) —
        # a graph-derived framework dep, like the base substrate but conditional on the feature.
        if any(e.request_kind == "multipart" for e in self.m.restapi.endpoints):
            extra.add("python-multipart>=0.0.9")
        dependencies = list(_BASE_DEPENDENCIES) + sorted(extra)
        content = self.env.get_template("pyproject.toml.j2").render(
            name=self.package, dependencies=dependencies, dev_dependencies=list(_DEV_DEPENDENCIES)
        )
        return self._write_file(self.root.parent / "pyproject.toml", content)

    def generate_domain(self) -> list[Path]:
        written = [self._write(naming.exceptions_path(), self._render_exceptions())]
        # Enums: a declarative StrEnum/Enum, UNLESS it declares pure-logic methods —
        # those bodies are scaffolded, making the file body-bearing (write-once, §3/§4).
        for en in self.m.domain.enums:
            path = naming.domain_path(en.name, en.subdomain)
            content = self._render_enum(en)
            written.append(self._write_scaffold(path, content) if en.methods else self._write(path, content))
        # Value objects: declarative frozen dataclass, scaffolded `__post_init__` when it
        # declares invariants (write-once), exactly like an entity.
        for vo in self.m.domain.value_objects:
            path = naming.domain_path(vo.name, vo.subdomain)
            content = self._render_value_object(vo)
            written.append(self._write_scaffold(path, content) if vo.invariants else self._write(path, content))
        for e in self.m.domain.entities:
            path = naming.entity_path(e.name, e.subdomain)
            content = self._render_entity(e)
            # An entity WITH invariants carries a scaffolded `__post_init__` (a body the
            # implementer fills) → the file is body-bearing: emit once, never overwrite
            # (§3/§4). A pure-declarative entity (no invariants) is always regenerated.
            written.append(self._write_scaffold(path, content) if e.invariants else self._write(path, content))
        for p in self.m.domain.repository_protocols:
            written.append(self._write(naming.protocol_path(p.name, p.subdomain), self._render_protocol(p)))
        # Capability protocols: declarative `typing.Protocol` (the adapter is scaffolded
        # separately in infrastructure).
        for cp in self.m.domain.capability_protocols:
            written.append(self._write(naming.domain_path(cp.name, cp.subdomain), self._render_capability_protocol(cp)))
        # Services: orchestrators with injected ports — the method bodies are scaffolds.
        for svc in self.m.domain.services:
            written.append(self._write_scaffold(naming.domain_path(svc.name, svc.subdomain), self._render_service(svc)))
        written.extend(self._write_domain_inits())
        return [p for p in written if p is not None]

    def _render_entity(self, e: Entity) -> str:
        required = [f for f in e.fields if f.default is None]
        defaulted = [f for f in e.fields if f.default is not None]
        decls = [f"{f.name}: {f.type}" for f in required]
        decls += [f"{f.name}: {f.type} = {f.default}" for f in defaulted]
        # Invariants → a scaffolded __post_init__: the contract-comment names each rule +
        # the field its ValidationError reports; the implementer fills the checks (§9).
        invariant_lines = [self._invariant_contract_line(inv) for inv in e.invariants]
        return self.env.get_template("domain_entity.py.j2").render(
            class_name=e.name,
            identity_field=e.identity_field,
            field_decls=decls,
            invariants=invariant_lines,
            import_block=dataclass_domain_import_block(
                [f.type for f in e.fields],
                subdomain=e.subdomain,
                domain_subdomains=self.domain_subdomains,
                has_post_init=bool(e.invariants),
            ),
        )

    def _render_enum(self, en: Enum) -> str:
        # Pure-logic methods carry a scaffolded body (NotImplementedError) the implementer
        # fills from `rule`; a method-free enum is fully declarative.
        methods = [
            {
                "signature": m.signature,
                "contract": [f"# Rule: {m.rule}"],
                "todo_message": f'"{en.name}.{_method_name(m.signature)}"',
            }
            for m in en.methods
        ]
        return self.env.get_template("domain_enum.py.j2").render(
            base=en.base,
            class_name=en.name,
            members=[{"name": mem.name, "value": mem.value} for mem in en.members],
            methods=methods,
        )

    def _render_value_object(self, vo: ValueObject) -> str:
        decls = self._ordered_decls(vo.fields)
        invariant_lines = [self._invariant_contract_line(inv) for inv in vo.invariants]
        return self.env.get_template("domain_value_object.py.j2").render(
            class_name=vo.name,
            field_decls=decls,
            invariants=invariant_lines,
            import_block=dataclass_domain_import_block(
                [f.type for f in vo.fields],
                subdomain=vo.subdomain,
                domain_subdomains=self.domain_subdomains,
                has_post_init=bool(vo.invariants),
            ),
        )

    def _render_protocol(self, p: RepositoryProtocol) -> str:
        signatures = [m.signature for m in p.methods]
        return self.env.get_template("domain_repository_protocol.py.j2").render(
            class_name=p.name,
            methods=signatures,
            import_block=protocol_import_block(
                signatures, subdomain=p.subdomain, domain_subdomains=self.domain_subdomains
            ),
        )

    def _render_capability_protocol(self, cp: CapabilityProtocol) -> str:
        signatures = [m.signature for m in cp.methods]
        return self.env.get_template("domain_repository_protocol.py.j2").render(
            class_name=cp.name,
            methods=signatures,
            import_block=protocol_import_block(
                signatures, subdomain=cp.subdomain, domain_subdomains=self.domain_subdomains
            ),
        )

    def _render_service(self, svc: Service) -> str:
        deps = self._dep_params(svc.dependencies, repos_first=False)
        methods = [
            {
                "signature": m.signature,
                "contract": self._service_method_contract(svc, m),
                "todo_message": f'"{svc.name}.{_method_name(m.signature)}"',
            }
            for m in svc.methods
        ]
        return self.env.get_template("scaffold_service.py.j2").render(
            class_name=svc.name,
            class_notes=self._notes_lines(svc.notes),  # service-wide GUIDE, rendered once
            deps=[{"param": p, "type": t} for p, t in deps],
            methods=methods,
            import_block=self._service_imports(svc),
        )

    def _service_method_contract(self, svc: Service, m) -> list[str]:
        lines = [f"# Contract for {svc.name}.{_method_name(m.signature)} (domain service). Implement the body below."]
        lines += self._notes_lines(m.notes)  # per-method GUIDE (service-wide note is at class level)
        if svc.dependencies:
            lines.append(f"# Dependencies: {', '.join(svc.dependencies)}.")
        if m.raises:
            lines.append(f"# Raises: {', '.join(m.raises)}.")
        lines += self._contract_behaviour_lines(m.behaviour)
        if any(svc.sources):
            lines.append(f"# Source: {', '.join(svc.sources)}.")
        return lines

    def _service_imports(self, svc: Service) -> str:
        # Domain types referenced in the method signatures (relative) + each injected
        # port from its owning subdomain (relative).
        sigs = [m.signature for m in svc.methods]
        groups: list[str] = []
        protocol_block = protocol_import_block(sigs, subdomain=svc.subdomain, domain_subdomains=self.domain_subdomains)
        # protocol_import_block seeds `typing.Protocol` — strip it (a service is not a Protocol)
        protocol_block = "\n".join(line for line in protocol_block.splitlines() if "import Protocol" not in line)
        dep_imports: dict[str, set[str]] = {}
        for dep in svc.dependencies:
            owner = self.port_subdomains[dep]
            module = f".{naming.snake_case(dep)}" if owner == svc.subdomain else f"..{owner}"
            dep_imports.setdefault(module, set()).add(dep)
        dep_lines = "\n".join(f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(dep_imports.items()))
        for block in (protocol_block.strip(), dep_lines):
            if block:
                groups.append(block)
        return "\n\n".join(groups)

    def _render_exceptions(self) -> str:
        exceptions = self._resolve_exceptions()
        all_names = sorted(["DomainError"] + [e["name"] for e in exceptions])
        return self.env.get_template("domain_exceptions.py.j2").render(all_names=all_names, exceptions=exceptions)

    def _resolve_exceptions(self) -> list[dict[str, object]]:
        """The error catalog: `DomainError` (the root, emitted unconditionally by the
        template) plus every exception the manifest DECLARES. There is no hardcoded standard
        catalog — a manifest declares every exception it uses (name + code + http_status), so
        the manifest is the single source of truth (the same anti-overfit move as the free-
        token store `kind`). Every declared exception subclasses `DomainError`; a refinement
        subclass (`InUseError(ConflictError)`) is not expressible yet — add a `parent` field
        to the schema when the first manifest needs one (anticipation litmus, §5).

        A structurally-required-but-undeclared exception (the `ValidationError` a scaffolded
        `__post_init__` raises, the `UnauthorizedError` an auth route's dependency imports)
        is NOT injected here: forgetting to declare it surfaces downstream as a broken import
        / red mypy in the verification loop (§4), the same way contract drift does.
        """
        return [
            {"name": x.name, "code": x.code, "http_status": x.http_status, "parent": "DomainError"}
            for x in self.m.domain.exceptions
        ]

    def _has_authenticated_endpoint(self) -> bool:
        return any(e.auth != "anonymous" for e in self.m.restapi.endpoints)

    def _write_domain_inits(self) -> list[Path]:
        modules_by_sub: dict[str, list[str]] = defaultdict(list)
        domain = self.m.domain
        for artifact in (*domain.enums, *domain.value_objects, *domain.entities, *domain.services):
            modules_by_sub[artifact.subdomain].append(naming.snake_case(artifact.name))
        for p in (*domain.repository_protocols, *domain.capability_protocols):
            modules_by_sub[p.subdomain].append(naming.snake_case(p.name))

        written = []
        for sub, modules in sorted(modules_by_sub.items()):
            init_path = PurePosixPath("domain", sub, "__init__.py")
            written.append(self._write(init_path, _init_body(sorted(modules))))
        written.append(self._write(PurePosixPath("domain", "__init__.py"), _init_body(sorted(modules_by_sub))))
        return written

    # ── application layer ───────────────────────────────────────────────────────
    # DTOs are declarative (always overwritten); handlers are BODIES (scaffold once,
    # never overwritten — the implementer LLM owns them). Spec §3 / §4.

    def generate_application(self) -> list[Path]:
        written = []
        for c in self.m.application.commands:
            sub = self._app_subdomain(c)
            written.append(self._write(naming.command_dto_path(c.name, sub), self._render_command_dto(c)))
            written.append(self._write_scaffold(naming.handler_path(c.name, sub), self._render_handler_scaffold(c)))
        for q in self.m.application.queries:
            sub = self._app_subdomain(q)
            written.append(self._write(naming.query_dto_path(q.name, sub), self._render_query_dto(q)))
            # The query's read-model cluster: helper result_dtos (e.g. SearchHit) + the main
            # *Result. They may reference each other / the output as siblings (local imports).
            sibling_names = {rd.name for rd in q.result_dtos} | ({q.output} if q.result_fields else set())
            for rd in q.result_dtos:
                content = self._render_dto(
                    rd.name,
                    self._ordered_decls(rd.fields),
                    [f.type for f in rd.fields],
                    sibling_dtos=sibling_names - {rd.name},
                )
                written.append(self._write(naming.result_dto_path(rd.name, sub), content))
            if q.result_fields:
                written.append(self._write(naming.result_dto_path(q.output, sub), self._render_result_dto(q)))
            written.append(self._write_scaffold(naming.handler_path(q.name, sub), self._render_handler_scaffold(q)))
        written.extend(self._write_application_inits())
        return [p for p in written if p is not None]

    def _render_command_dto(self, c: Command) -> str:
        # the actor (caller_id) is prepended only when the command is reachable via an
        # authenticated endpoint (derived — §A); a public command carries no caller_id.
        decls = self._ordered_decls(c.input)
        types = [f.type for f in c.input]
        if self._command_has_caller(c):
            decls = ["caller_id: UUID", *decls]
            types = ["UUID", *types]
        return self._render_dto(f"{c.name}Command", decls, types)

    def _render_query_dto(self, q: Query) -> str:
        decls = self._ordered_decls(q.input)
        return self._render_dto(f"{q.name}Query", decls, [f.type for f in q.input])

    def _render_result_dto(self, q: Query) -> str:
        decls = self._ordered_decls(q.result_fields)
        siblings = {rd.name for rd in q.result_dtos}
        return self._render_dto(q.output, decls, [f.type for f in q.result_fields], sibling_dtos=siblings)

    def _render_dto(self, class_name, decls, field_types, *, sibling_dtos=frozenset()) -> str:
        import_block = dto_import_block(field_types, package=self.package, domain_subdomains=self.domain_subdomains)
        # sibling read-model DTOs (helper result_dtos / the *Result) live in the same
        # application subpackage → a local import, not a domain/stdlib one.
        referenced = {t for ft in field_types for t in type_tokens(ft)}
        local = [f"from .{naming.snake_case(n)} import {n}" for n in sorted(sibling_dtos) if n in referenced]
        if local:
            import_block = f"{import_block}\n\n{chr(10).join(local)}" if import_block else "\n".join(local)
        return self.env.get_template("frozen_dataclass_dto.py.j2").render(
            class_name=class_name, field_decls=decls, import_block=import_block
        )

    # ── handler scaffolds (bodies — §3 / §4) ────────────────────────────────────
    # The handler body is a body: scaffold it (signature + contract-type imports +
    # contract-comment + raise NotImplementedError). The LLM fills the body behind
    # the contract; the contract-comment IS its spec (behaviour / raises / deps /
    # log_event / source UC).

    def _render_handler_scaffold(self, node: Command | Query) -> str:
        is_command = isinstance(node, Command)
        deps = self._dep_params(node.handler.dependencies)
        if is_command:
            arg_name, arg_type = "cmd", f"{node.name}Command"
            return_type = "uuid.UUID" if node.output == "UUID" else "None"
        else:
            arg_name, arg_type = "query", f"{node.name}Query"
            return_type = node.output
        local = [(f"{naming.snake_case(node.name)}_{'command' if is_command else 'query'}", arg_type)]
        result_entity = None
        output_type = None  # a query output that is neither a *Result DTO nor a domain entity
        if not is_command and node.result_fields:
            # the *Result DTO this query returns is a sibling application module
            local.append((naming.snake_case(node.output), node.output))
        elif not is_command and node.output not in ("None", "UUID"):
            if node.output in self.entity_subdomains:
                result_entity = node.output  # a single-entity read returns the domain entity directly
            else:
                # a free type expression (e.g. a streaming `AsyncIterator[str]`) — its tokens
                # are resolved generically (stdlib + domain), not assumed to be an entity.
                output_type = node.output

        contract = self._handler_contract(node, is_command=is_command)
        import_block = self._handler_scaffold_imports(
            deps,
            local=local,
            needs_uuid_return=is_command and node.output == "UUID",
            result_entity=result_entity,
            output_type=output_type,
        )
        return self.env.get_template("scaffold_handler.py.j2").render(
            class_name=f"{node.name}Handler",
            deps=[{"param": p, "type": t} for p, t in deps],
            method="execute",
            arg_name=arg_name,
            arg_type=arg_type,
            return_type=return_type,
            contract=contract,
            todo_message=f'"{node.name}Handler.execute"',
            import_block=import_block,
        )

    def _handler_contract(self, node: Command | Query, *, is_command: bool) -> list[str]:
        """The contract-comment the implementer LLM reads to fill the body (§4)."""
        kind = "command" if is_command else "query"
        lines = [f"# Contract for {node.name}Handler.execute ({kind}). Implement the body below."]
        lines += self._notes_lines(node.notes)  # the GUIDE: distilled prose intent (read first)
        lines += self._contract_meta_lines(node, is_command=is_command)
        lines += self._contract_behaviour_lines(node.behaviour)
        return lines

    @staticmethod
    def _invariant_contract_line(inv) -> str:
        """One invariant line for an entity/VO `__post_init__` contract. `field` is optional
        (a whole-entity / cross-field rule may report no single field)."""
        meta = f"field: {inv.field}, source: {inv.source}" if inv.field else f"source: {inv.source}"
        return f"#   - {inv.rule}  [{meta}]"

    @staticmethod
    def _notes_lines(notes: str | None) -> list[str]:
        """The `notes` prose, rendered into the contract-comment — the implementer's
        distilled GUIDE (the rule/algorithm the body must implement). Multi-line prose is
        preserved line-by-line; empty when no notes."""
        if not notes:
            return []
        out: list[str] = []
        for line in notes.strip().splitlines():
            out.append(f"# {line.rstrip()}" if line.strip() else "#")
        return out

    def _contract_meta_lines(self, node: Command | Query, *, is_command: bool) -> list[str]:
        lines: list[str] = []
        deps = node.handler.dependencies
        if deps:
            lines.append(f"# Dependencies: {', '.join(deps)}.")
        if node.raises:
            lines.append(f"# Raises: {', '.join(node.raises)}.")
        if is_command and getattr(node, "log_event", None):
            lines.append(f'# On success log_event: "{node.log_event}" (success-only, structured).')
        if not is_command:
            lines.append("# Read-only: never mutates, never logs a business event.")
        if any(node.sources):
            lines.append(f"# Source: {', '.join(node.sources)}.")
        return lines

    @staticmethod
    def _contract_behaviour_lines(behaviour) -> list[str]:
        if not behaviour:
            return []
        lines = ["# Behaviour scenarios (canonical, §9):"]
        for sc in behaviour:
            lines.append(f"#   - given: {sc.given}")
            if sc.arrange:
                seeds = "; ".join(f"{s.entity}({s.fields})" for s in sc.arrange)
                lines.append(f"#       arrange: {seeds}")
            if sc.act:
                lines.append(f"#       act: {sc.act}")
            lines.append(f"#       then: {Generator._then_outcome(sc.then)}")
        return lines

    @staticmethod
    def _then_outcome(then) -> str:
        """The closed `then` vocabulary (§9) rendered for the contract-comment —
        unlike _then_str (used by the §9 test seam), this includes `raises`."""
        for verb in ("raises", "returns", "persists", "deletes", "logs", "calls"):
            value = getattr(then, verb)
            if value:
                if verb == "persists" and then.with_:
                    pairs = ", ".join(f"{k}={v}" for k, v in then.with_.items())
                    return f"persists {value} (with {pairs})"
                return f"{verb} {value}"
        return "outcome"

    def _handler_scaffold_imports(self, deps, *, local, needs_uuid_return, result_entity, output_type=None) -> str:
        # Cross-layer (application → domain) imports are absolute. Group every injected
        # port type — plus the result entity, if any — by its owning subdomain.
        groups: list[str] = []
        if needs_uuid_return:
            groups.append("import uuid")
        by_subdomain: dict[str, set[str]] = defaultdict(set)
        stdlib: dict[str, set[str]] = {}
        for _param, dep_type in deps:
            by_subdomain[self.port_subdomains[dep_type]].add(dep_type)
        if result_entity:
            by_subdomain[self.entity_subdomains[result_entity]].add(result_entity)
        if output_type:  # a free output type expression: resolve its tokens (stdlib + domain)
            for token in type_tokens(output_type):
                if token in _STDLIB:
                    module, symbol = _STDLIB[token]
                    stdlib.setdefault(module, set()).add(symbol)
                elif token in self.domain_subdomains:
                    by_subdomain[self.domain_subdomains[token]].add(token)
        stdlib_block = "\n".join(f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(stdlib.items()))
        if stdlib_block:
            groups.append(stdlib_block)
        domain_lines = [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(names))}"
            for sub, names in sorted(by_subdomain.items())
        ]
        groups.append("\n".join(domain_lines))
        local_lines = [f"from .{module} import {name}" for module, name in sorted(local)]
        groups.append("\n".join(local_lines))
        return "\n\n".join(g for g in groups if g)

    def _node_repo(self, node: Command | Query) -> RepositoryProtocol:
        """The single repository a node is built around — used only by the FLAT canonical
        test (which injects exactly one fake repo). A multi-repository handler is never
        flat (`_is_flat` routes it to a manual stub), so this is only ever reached for a
        single-repo node; the guard is defensive."""
        protocols = {p.name: p for p in self.m.domain.repository_protocols}
        deps = [d for d in node.handler.dependencies if d in protocols]
        if len(deps) != 1:
            raise NotImplementedError(
                f"{node.name}: _node_repo is single-repo only (flat-test path); "
                f"a multi-repo node must route to a manual stub"
            )
        return protocols[deps[0]]

    def _dep_params(self, deps: list[str], *, repos_first: bool = True) -> list[tuple[str, str]]:
        """Ordered (param_name, type) for an injected dependency list — the single source
        of constructor-parameter names, shared by the handler scaffold, the service
        scaffold, and the DI wiring so the kwargs line up.

        A node may depend on MULTIPLE repositories (a write that spans two aggregates/
        stores — there is no single-repo restriction any more). With one repository the
        param stays `repo` (unchanged); with several it is disambiguated by aggregate
        (`document_repo`, `chunk_repo`). Capabilities (`ICan<Verb>` → `<verb>`) and services
        (`<X>Service` → snake_case) are named by `_dep_param`. `repos_first` puts repos
        ahead of the rest (the handler convention); services keep declared order. Cross-
        store atomicity is the implementer's concern in the body — the generator only
        injects the ports."""
        repo_aggregate = {p.name: p.aggregate for p in self.m.domain.repository_protocols}
        repo_names = [d for d in deps if d in repo_aggregate]
        multi_repo = len(repo_names) > 1

        def param(dep: str) -> str:
            if dep in repo_aggregate:
                return f"{naming.snake_case(repo_aggregate[dep])}_repo" if multi_repo else "repo"
            return self._dep_param(dep)

        ordered = repo_names + [d for d in deps if d not in repo_aggregate] if repos_first else list(deps)
        return [(param(d), d) for d in ordered]

    def _dep_param(self, dep: str) -> str:
        """Constructor parameter name for a NON-repository injected dependency: a capability
        `ICan<Verb>` → `<verb>`; a `<X>Service` → its snake_case. Repository params are
        named contextually by `_dep_params` (`repo` alone, `<aggregate>_repo` when several)."""
        if dep.startswith("ICan"):
            return naming.snake_case(dep[len("ICan") :])
        return naming.snake_case(dep)

    def _dep_provider_attr(self, dep: str) -> str:
        """Container attribute that provides a dependency."""
        for p in self.m.domain.repository_protocols:
            if p.name == dep:
                return f"{naming.snake_case(p.aggregate)}_repository"
        if dep.startswith("ICan"):
            return naming.snake_case(dep[len("ICan") :])
        return naming.snake_case(dep)

    def _entity(self, name: str) -> Entity:
        return next(e for e in self.m.domain.entities if e.name == name)

    @staticmethod
    def _ordered_decls(fields) -> list[str]:
        def decl(f) -> str:
            if f.default is not None:
                return f"{f.name}: {f.type} = {f.default}"
            if f.optional:
                return f"{f.name}: {f.type} = None"
            return f"{f.name}: {f.type}"

        required = [f for f in fields if f.default is None and not f.optional]
        optional = [f for f in fields if not (f.default is None and not f.optional)]
        return [decl(f) for f in required] + [decl(f) for f in optional]

    def _app_subdomain(self, node: Command | Query) -> str:
        """Application file subdomain = the subdomain of the aggregate it touches,
        read off the node's primary repository dependency."""
        protocols = {p.name: p.subdomain for p in self.m.domain.repository_protocols}
        for dep in node.handler.dependencies:
            if dep in protocols:
                return protocols[dep]
        return self.m.domain.entities[0].subdomain

    def _write_application_inits(self) -> list[Path]:
        modules_by_sub: dict[str, list[str]] = defaultdict(list)
        for c in self.m.application.commands:
            sub = self._app_subdomain(c)
            snake = naming.snake_case(c.name)
            modules_by_sub[sub] += [f"{snake}_command", f"{snake}_handler"]
        for q in self.m.application.queries:
            sub = self._app_subdomain(q)
            snake = naming.snake_case(q.name)
            modules_by_sub[sub] += [f"{snake}_query", f"{snake}_handler"]
            if q.result_fields:
                modules_by_sub[sub].append(naming.snake_case(q.output))
            modules_by_sub[sub] += [naming.snake_case(rd.name) for rd in q.result_dtos]

        written = []
        for sub, modules in sorted(modules_by_sub.items()):
            init_path = PurePosixPath("application", sub, "__init__.py")
            written.append(self._write(init_path, _init_body(sorted(modules))))
        app_init = PurePosixPath("application", "__init__.py")
        written.append(self._write(app_init, _init_body(sorted(modules_by_sub))))
        return written

    # ── infrastructure: tables + Alembic migrations ─────────────────────────────

    def _relational_subpkg(self) -> str:
        """Infra subpackage for the shared SQLAlchemy bootstrap (engine/metadata/DbSettings)
        + the relational tables/repositories: the kind of a bootstrap-backed repository
        (`postgres`), so everything for that store sits together — `infrastructure/postgres/`,
        not a special `db/`. Defaults to 'postgres' when no relational repo is present."""
        for r in self.m.infrastructure.repositories:
            if self._repo_profile(r).uses_bootstrap:
                return self._store_kind(r)
        return "postgres"

    def generate_infrastructure(self) -> list[Path]:
        repos = self.m.infrastructure.repositories
        relational = self._relational_subpkg()
        written = [self._copy_scaffold("metadata.py", PurePosixPath("infrastructure", relational, "metadata.py"))]

        # A repository (and its table) lives under its STORE'S kind, like every other infra
        # node groups by tech (§ naming): a postgres repo → infrastructure/postgres/, a qdrant
        # repo → infrastructure/qdrant/. No store is split across folders.
        #
        # Table schema is a BODY (judgment: column TYPES, indexes, constraints — jsonb,
        # pgvector), not a transcription: a write-once Table SCAFFOLD the implementer fills
        # (§3/§4), only for relational stores. Migrations are NOT generated — Alembic owns the
        # revision chain natively (`alembic revision`), so emitting them would duplicate it
        # (§0.2). A non-relational store (qdrant, …) gets no SQLAlchemy table.
        tables_by_sub: dict[str, list[str]] = defaultdict(list)
        repos_by_sub: dict[str, list[str]] = defaultdict(list)
        for r in repos:
            sub = self._store_kind(r)
            scaffold = self._write_scaffold(naming.repository_path(r.backs, sub), self._render_repository_scaffold(r))
            if scaffold is not None:
                written.append(scaffold)
            repos_by_sub[sub].append(f"{naming.snake_case(r.backs)}_repository")
            if self._repo_profile(r).uses_bootstrap:  # only relational stores get a SQLAlchemy table
                table = self._write_scaffold(naming.table_path(r.backs, sub), self._render_table_scaffold(r))
                if table is not None:
                    written.append(table)
                tables_by_sub[sub].append(naming.table_name(r.backs))
        for sub, mods in tables_by_sub.items():
            init_path = PurePosixPath("infrastructure", sub, "tables", "__init__.py")
            written.append(self._write(init_path, _init_body(sorted(mods))))
        for sub, mods in repos_by_sub.items():
            init_path = PurePosixPath("infrastructure", sub, "repositories", "__init__.py")
            written.append(self._write(init_path, _init_body(sorted(mods))))

        # settings (declarative) + capability adapters (scaffolded bodies), grouped by
        # infra subpackage; each subpackage gets a wildcard re-export __init__ (glue).
        modules_by_pkg: dict[str, list[str]] = defaultdict(list)
        for s in self.m.infrastructure.settings:
            sub = self._settings_subpackage(s.name)
            written.append(self._write(naming.settings_path(s.name, sub), self._render_settings(s)))
            modules_by_pkg[sub].append(naming.settings_module(s.name))
        for cap in self.m.infrastructure.capabilities:
            subpkg = self._capability_subpackage(cap)
            path = naming.capability_adapter_path(self._capability_class(cap), subpkg)
            scaffold = self._write_scaffold(path, self._render_capability_scaffold(cap, subpkg))
            if scaffold is not None:
                written.append(scaffold)
            modules_by_pkg[subpkg].append(path.stem)
        # Connection factory per non-bootstrap datastore that backs a repository: a scaffold
        # `create_<store>_client(settings) -> <Client>` the implementer fills (SDK-specific
        # construction = judgment). Postgres reuses the db_engine bootstrap, so it is skipped.
        stores_with_repos = {r.store for r in repos if r.store is not None}
        for ds in self.m.infrastructure.datastores:
            if ds.name not in stores_with_repos or profile_for(ds.kind).uses_bootstrap:
                continue
            subpkg = self._datastore_subpkg(ds)
            path = PurePosixPath("infrastructure", subpkg, "connection.py")
            scaffold = self._write_scaffold(path, self._render_connection_scaffold(ds))
            if scaffold is not None:
                written.append(scaffold)
            modules_by_pkg[subpkg].append("connection")
        for subpkg, modules in sorted(modules_by_pkg.items()):
            init_path = PurePosixPath("infrastructure", subpkg, "__init__.py")
            written.append(self._write(init_path, _init_body(sorted(set(modules)))))

        # empty package markers so the import chain resolves: the infrastructure root, plus
        # every store subpackage that holds repositories/tables but got no wildcard re-export
        # __init__ from modules_by_pkg (e.g. `postgres/`, which holds only the bootstrap +
        # repositories/ + tables/ subpackages, none of them wildcard-re-exported).
        written.append(self._write(PurePosixPath("infrastructure", "__init__.py"), ""))
        store_subs = (set(repos_by_sub) | set(tables_by_sub) | {relational}) - set(modules_by_pkg)
        for sub in sorted(store_subs):
            written.append(self._write(PurePosixPath("infrastructure", sub, "__init__.py"), ""))
        return [p for p in written if p is not None]

    def _store_kind(self, repo) -> str:
        """The datastore KIND backing a repository — the profile selector. Defaults to
        'postgres' when the repo names no `store` or the manifest declares no datastores
        (legacy single-Postgres behaviour). Drives whether a relational Table scaffold is
        emitted (postgres) and, later, the connection/collection-setup profile."""
        return kind_of(self.m.infrastructure.datastores, repo.store)

    def _repo_profile(self, repo) -> StoreProfile:
        """The store profile (variant B) backing a repository — drives the injected client
        param/type/import, the contract style, and the connection wiring."""
        return profile_for(self._store_kind(repo))

    def _datastore_for(self, repo):
        if repo.store is None:
            return None
        return next((d for d in self.m.infrastructure.datastores if d.name == repo.store), None)

    def _datastore_subpkg(self, ds) -> str:
        """Infra subpackage that owns a datastore's connection + settings = its TECH (kind):
        infrastructure/qdrant/, infrastructure/redis/. Groups by the external integration."""
        return ds.kind

    def _render_connection_scaffold(self, ds) -> str:
        """A write-once connection-factory SCAFFOLD for a non-bootstrap datastore:
        `create_<store>_client(settings) -> <Client>` the implementer fills (constructing the
        SDK client from settings is judgment). The container injects its Singleton result into
        every repository on this store."""
        profile = profile_for(ds.kind)
        factory = f"create_{ds.name}_client"
        params = f"settings: {ds.settings}" if ds.settings else ""
        third = [profile.resource_import] if profile.resource_import else []
        local = [f"from .{naming.settings_module(ds.settings)} import {ds.settings}"] if ds.settings else []
        import_block = "\n\n".join(g for g in ("\n".join(third), "\n".join(local)) if g)
        contract = [
            f"# Connection factory for datastore {ds.name!r} ({ds.kind}). Build the client from",
            "# settings (SDK-specific — translate connection errors at the boundary as needed).",
        ]
        return self.env.get_template("scaffold_connection.py.j2").render(
            factory=factory,
            params=params,
            client_type=profile.resource_type,
            contract=contract,
            import_block=import_block,
        )

    def _render_table_scaffold(self, repo) -> str:
        """A write-once Table SCAFFOLD: the SQLAlchemy Core skeleton (`<name>_table = Table(
        "<name>", metadata, ...)`) plus a contract-comment listing the backing entity's
        fields + domain types. Column TYPES, indexes, and constraints are JUDGMENT the
        implementer fills (§3/§4) — the generator no longer maps Python→SQL types (the old
        `_SQL_CORE`, which broke on any unforeseen type like `list[float]`). Audit timestamps
        stay a DB-managed convention the implementer adds; the migration is authored
        separately via Alembic."""
        entity = self._entity(repo.backs)
        store = repo.store or "main"
        contract = [
            f"# Schema for {entity.name} in datastore {store!r} (postgres). Choose column types,",
            "# indexes, and constraints — this is a body (judgment), not a transcription.",
            f"# Fields (domain types) — identity field is {entity.identity_field!r} (primary key):",
            *[f"#   - {f.name}: {f.type}{' (nullable)' if f.optional else ''}" for f in entity.fields],
            "# Audit (DB-managed convention): add created_at/updated_at with",
            "# server_default=now() (updated_at also onupdate=now()).",
            "# Migration: authored separately via `alembic revision` (Alembic owns the chain).",
        ]
        return self.env.get_template("scaffold_table.py.j2").render(
            table_var=f"{naming.table_name(repo.backs)}_table",
            table_name=naming.table_name(repo.backs),
            contract=contract,
        )

    # ── infrastructure: repository adapters (bodies — §3 / §4) ───────────────────
    # The repository IS a body (SQLAlchemy Core queries are logic, not a graph
    # transcription): scaffold it. The scaffold gives the class + the standard
    # session_factory injection + each protocol method signature + a contract-comment
    # naming the table, the row-to-entity mapping, and the _map_integrity_error
    # translation the implementer must write, then raise NotImplementedError.

    def _render_repository_scaffold(self, repo_entry) -> str:
        proto = next(p for p in self.m.domain.repository_protocols if p.name == repo_entry.implements)
        entity = self._entity(repo_entry.backs)
        agg = repo_entry.backs
        profile = self._repo_profile(repo_entry)
        methods = []
        for pm in proto.methods:
            method_name = re.match(r"async def (\w+)", pm.signature).group(1)
            methods.append(
                {
                    "signature": pm.signature,
                    "contract": self._repo_method_contract(pm, agg, entity, proto, repo_entry, profile),
                    "todo_message": f'"{agg}Repository.{method_name}"',
                }
            )
        return self.env.get_template("scaffold_repository.py.j2").render(
            class_name=f"{agg}Repository",
            class_notes=self._notes_lines(repo_entry.notes),  # store-wide GUIDE (infra), rendered once
            methods=methods,
            resource_param=profile.resource_param,
            resource_attr=profile.resource_attr,
            resource_type=profile.resource_type,
            import_block=self._repo_scaffold_imports(proto, agg, repo_entry, profile),
        )

    def _repo_method_contract(
        self, pm, agg: str, entity: Entity, proto, repo_entry, profile: StoreProfile
    ) -> list[str]:
        sig = pm.signature
        name = re.match(r"async def (\w+)", sig).group(1)
        lines = self._notes_lines(pm.notes)  # per-method semantic GUIDE (from the protocol)
        if profile.contract == "sql":
            table = f"{naming.table_name(agg)}_table"
            fields = ", ".join(f.name for f in entity.fields)
            lines = [f"# Contract for {agg}Repository.{name} (SQLAlchemy Core, never ORM).", *lines]
            lines.append(f"# Table: {table} ({fields}).")
            lines.append(f"# Row → entity: map every column to {agg}(...) (the row-to-entity mapper).")
            if name in ("add", "create", "save", "update", "delete"):
                constraints = repo_entry.constraint_map
                mapped = "; ".join(f"{c} → {e}" for c, e in constraints.items()) or "none declared"
                lines.append(f"# Wrap writes: translate IntegrityError via _map_integrity_error ({mapped}).")
            if name in ("get_by_id", "update", "delete"):
                lines.append(f'# Missing row → raise NotFoundError("{agg} not found", {{"id": ...}}).')
            if name == "list":
                lines.append(
                    "# Filtering/ordering follow the query behaviour + this signature "
                    "(e.g. a flag param excludes matching rows when false). Not declared "
                    "in the manifest — derive from the contract."
                )
            return lines
        # non-relational store (collection / generic): no Table, no SQLAlchemy, no IntegrityError.
        store = repo_entry.store or profile.kind
        header = f"# Contract for {agg}Repository.{name} ({profile.kind} adapter, via self._{profile.resource_attr})."
        lines = [header, *lines]
        lines.append(f"# Persists {agg} to the {store!r} datastore ({profile.kind}); map items to/from {agg}(...).")
        lines.append("# Translate SDK/provider errors into domain exceptions at the boundary.")
        if name.startswith("get") or name in ("update", "delete"):
            lines.append(f'# Missing item → raise NotFoundError("{agg} not found", {{...}}).')
        return lines

    def _repo_scaffold_imports(self, proto, agg: str, repo_entry, profile: StoreProfile) -> str:
        # Contract-type imports from the graph: the stdlib types the protocol signatures
        # reference (UUID, …) plus every DOMAIN type they reference (the aggregate and any
        # enum/VO in a parameter or return, e.g. Email). The protocol itself is NOT imported
        # — the adapter satisfies it structurally (no inheritance). The body's incidental
        # imports (select, IntegrityError, the table module, …) are the implementer's.
        referenced = {t for pm in proto.methods for t in type_tokens(pm.signature)}
        stdlib: dict[str, set[str]] = {}
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        domain_by_sub[self.domain_subdomains[agg]].add(agg)
        for token in referenced:
            if token in _STDLIB:
                module, symbol = _STDLIB[token]
                stdlib.setdefault(module, set()).add(symbol)
            elif token in self.domain_subdomains:
                domain_by_sub[self.domain_subdomains[token]].add(token)
        stdlib_lines = [f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(stdlib.items())]
        # the injected client's import comes from the store profile (postgres → SQLAlchemy
        # async session; qdrant → QdrantClient; unknown kind → none, an untyped client).
        third = [profile.resource_import] if profile.resource_import else []
        first = [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(names))}"
            for sub, names in sorted(domain_by_sub.items())
        ]
        groups = ["\n".join(stdlib_lines), "\n".join(third), "\n".join(first)]
        return "\n\n".join(g for g in groups if g)

    # ── infrastructure: settings (declarative) + capability adapters (bodies) ────

    def _render_settings(self, s: Settings) -> str:
        fields, needs_secret = [], False
        for f in s.fields:
            if f.secret:
                needs_secret = True
                fields.append(f"{f.name}: SecretStr")  # secrets never default (must fail loud)
            elif f.default is not None:
                fields.append(f"{f.name}: {f.type} = {f.default}")
            else:
                fields.append(f"{f.name}: {f.type}")
        return self.env.get_template("infra_settings.py.j2").render(
            class_name=s.name, env_prefix=s.env_prefix, fields=fields, needs_secret=needs_secret
        )

    def _capability_subpackage(self, cap: Capability) -> str:
        # Infra groups by the external TECH, not a domain subdomain: the adapter token
        # (openai/jwt/unstructured) IS the integration. Was: settings.subpackage / the
        # protocol's domain subdomain (the `ai`/`corpus` smell).
        return cap.adapter

    def _settings_subpackage(self, settings_name: str) -> str:
        """A settings' infra home = the tech of whatever consumes it: a capability's
        `adapter` or a datastore's `kind` (derived, not a manifest field). One settings has
        one consuming tech in practice; an orphan falls back to its own snake name."""
        for cap in self.m.infrastructure.capabilities:
            if cap.settings == settings_name:
                return cap.adapter
        for ds in self.m.infrastructure.datastores:
            if ds.settings == settings_name:
                return ds.kind
        return naming.snake_case(settings_name)

    def _capability_protocol(self, name: str) -> CapabilityProtocol:
        return next(p for p in self.m.domain.capability_protocols if p.name == name)

    @staticmethod
    def _capability_class(cap: Capability) -> str:
        """`<AdapterPascal><Suffix>` — the adapter token PascalCased + an agent-noun. The
        suffix is `cap.role` when given (`TokenManager` → `JwtTokenManager`); otherwise it
        falls back to the protocol verb-noun (`ICanManageTokens` → `JwtManageTokens`). The
        role is carried because the agent-noun isn't mechanically derivable from the verb."""
        suffix = cap.role or (cap.implements[len("ICan") :] if cap.implements.startswith("ICan") else cap.implements)
        return f"{cap.adapter[:1].upper()}{cap.adapter[1:]}{suffix}"

    def _render_capability_scaffold(self, cap: Capability, subpkg: str) -> str:
        proto = self._capability_protocol(cap.implements)
        class_name = self._capability_class(cap)
        # class-level GUIDE, rendered once: the protocol's semantic contract (domain) then
        # the adapter's SDK-specific note (infra).
        class_notes = self._notes_lines(proto.notes) + self._notes_lines(cap.notes)
        methods = [
            {
                "signature": pm.signature,
                "contract": self._capability_method_contract(cap, proto, pm),
                "todo_message": f'"{class_name}.{_method_name(pm.signature)}"',
            }
            for pm in proto.methods
        ]
        return self.env.get_template("scaffold_capability.py.j2").render(
            class_name=class_name,
            class_notes=class_notes,
            settings_type=cap.settings,
            methods=methods,
            import_block=self._capability_imports(proto, cap),
        )

    def _capability_method_contract(self, cap: Capability, proto: CapabilityProtocol, pm) -> list[str]:
        lines = [
            f"# Contract for {self._capability_class(cap)}.{_method_name(pm.signature)} — adapter for {proto.name}.",
            f"# Wraps the {cap.adapter} SDK; translate SDK errors into domain exceptions at the boundary.",
        ]
        lines += self._notes_lines(pm.notes)  # per-method semantic GUIDE (from the protocol)
        if any(cap.sources):
            lines.append(f"# Source: {', '.join(cap.sources)}.")
        return lines

    def _capability_imports(self, proto: CapabilityProtocol, cap: Capability) -> str:
        referenced = {t for pm in proto.methods for t in type_tokens(pm.signature)}
        stdlib: dict[str, set[str]] = {}
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        for token in referenced:
            if token in _STDLIB:
                module, symbol = _STDLIB[token]
                stdlib.setdefault(module, set()).add(symbol)
            elif token in self.domain_subdomains:
                domain_by_sub[self.domain_subdomains[token]].add(token)
        stdlib_lines = [f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(stdlib.items())]
        domain_lines = [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(names))}"
            for sub, names in sorted(domain_by_sub.items())
        ]
        local = [f"from .{naming.settings_module(cap.settings)} import {cap.settings}"] if cap.settings else []
        groups = ["\n".join(stdlib_lines), "\n".join(domain_lines), "\n".join(local)]
        return "\n\n".join(g for g in groups if g)

    # ── composition root: DI container (infra-di-provider) ──────────────────────

    def generate_container(self) -> list[Path]:
        rel = self._relational_subpkg()  # the SQLAlchemy bootstrap lives with its store (postgres/)
        return [
            self._copy_scaffold("db_settings.py", PurePosixPath("infrastructure", rel, "settings.py")),
            self._copy_scaffold("db_engine.py", PurePosixPath("infrastructure", rel, "engine.py")),
            self._write(PurePosixPath("containers.py"), self._render_container()),
        ]

    def _render_container(self) -> str:
        # Definition order matters (a provider references those above it): settings →
        # repositories → capabilities → services → handlers.
        blocks = []
        for s in self.m.infrastructure.settings:
            blocks.append(self._provider_block(naming.snake_case(s.name), s.name, s.name, [], kind="Singleton"))
        # One client Singleton per non-bootstrap datastore that backs a repository, built from
        # its scaffolded connection factory (postgres reuses the template's engine/
        # session_factory, so it is skipped here).
        stores_with_repos = {r.store for r in self.m.infrastructure.repositories if r.store is not None}
        for ds in self.m.infrastructure.datastores:
            profile = profile_for(ds.kind)
            if ds.name not in stores_with_repos or profile.uses_bootstrap:
                continue
            kwargs = [("settings", naming.snake_case(ds.settings))] if ds.settings else []
            blocks.append(
                self._provider_block(
                    f"{ds.name}_client", profile.resource_type, f"create_{ds.name}_client", kwargs, kind="Singleton"
                )
            )
        for r in self.m.infrastructure.repositories:
            attr = f"{naming.snake_case(r.backs)}_repository"
            profile = self._repo_profile(r)
            if profile.uses_bootstrap:
                resource_kwarg = [("session_factory", "session_factory")]
            else:
                resource_kwarg = [(profile.resource_param, f"{r.store}_client")]
            blocks.append(self._provider_block(attr, r.implements, f"{r.backs}Repository", resource_kwarg))
        for cap in self.m.infrastructure.capabilities:
            kwargs = [("settings", naming.snake_case(cap.settings))] if cap.settings else []
            blocks.append(
                self._provider_block(
                    self._dep_provider_attr(cap.implements),
                    cap.implements,
                    self._capability_class(cap),
                    kwargs,
                    kind="Singleton",
                )
            )
        for svc in self.m.domain.services:
            kwargs = [(p, self._dep_provider_attr(t)) for p, t in self._dep_params(svc.dependencies, repos_first=False)]
            blocks.append(self._provider_block(naming.snake_case(svc.name), svc.name, svc.name, kwargs))
        for node in (*self.m.application.commands, *self.m.application.queries):
            attr = f"{naming.snake_case(node.name)}_handler"
            handler_cls = f"{node.name}Handler"
            kwargs = [(p, self._dep_provider_attr(t)) for p, t in self._dep_params(node.handler.dependencies)]
            blocks.append(self._provider_block(attr, handler_cls, handler_cls, kwargs))
        return self.env.get_template("containers.py.j2").render(
            import_block=self._container_imports(),
            wiring_package=f"{self.package}.restapi",
            provider_blocks=blocks,
        )

    @staticmethod
    def _provider_block(attr: str, type_ann: str, factory_cls: str, kwargs, *, kind: str = "Factory") -> str:
        if not kwargs:
            return f"    {attr}: providers.Provider[{type_ann}] = providers.{kind}({factory_cls})"
        kw = ", ".join(f"{k}={v}" for k, v in kwargs)
        return f"    {attr}: providers.Provider[{type_ann}] = providers.{kind}(\n        {factory_cls}, {kw}\n    )"

    def _container_imports(self) -> str:
        third = [
            "from dependency_injector import containers, providers",
            "from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker",
        ]
        first: list[str] = []

        # Domain port + service types that appear in `Provider[...]` annotations, grouped
        # by subdomain: repository protocols (backed by a repo), capability protocols
        # (backed by an adapter), and service classes.
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        for r in self.m.infrastructure.repositories:
            proto = next(p for p in self.m.domain.repository_protocols if p.name == r.implements)
            domain_by_sub[proto.subdomain].add(proto.name)
        for cap in self.m.infrastructure.capabilities:
            proto = self._capability_protocol(cap.implements)
            domain_by_sub[proto.subdomain].add(proto.name)
        for svc in self.m.domain.services:
            domain_by_sub[svc.subdomain].add(svc.name)
        for sub, names in domain_by_sub.items():
            first.append(_import_from(f"{self.package}.domain.{sub}", sorted(names)))

        # Application handler classes, by subdomain.
        handlers_by_sub: dict[str, list[str]] = defaultdict(list)
        for node in (*self.m.application.commands, *self.m.application.queries):
            handlers_by_sub[self._app_subdomain(node)].append(f"{node.name}Handler")
        for sub, names in handlers_by_sub.items():
            first.append(_import_from(f"{self.package}.application.{sub}", names))

        # Infrastructure: engine helpers + DbSettings (the SQLAlchemy bootstrap, in the
        # relational store's subpackage), repository classes (each under its store's kind),
        # settings classes, capability adapter classes.
        rel = self._relational_subpkg()
        engine_mod = f"{self.package}.infrastructure.{rel}.engine"
        first.append(_import_from(engine_mod, ["create_engine", "create_session_factory"]))
        first.append(_import_from(f"{self.package}.infrastructure.{rel}.settings", ["DbSettings"]))
        for r in self.m.infrastructure.repositories:
            sub = self._store_kind(r)
            mod = f"{self.package}.infrastructure.{sub}.repositories.{naming.snake_case(r.backs)}_repository"
            first.append(_import_from(mod, [f"{r.backs}Repository"]))
        for s in self.m.infrastructure.settings:
            mod = f"{self.package}.infrastructure.{self._settings_subpackage(s.name)}.{naming.settings_module(s.name)}"
            first.append(_import_from(mod, [s.name]))
        for cap in self.m.infrastructure.capabilities:
            subpkg = self._capability_subpackage(cap)
            stem = naming.capability_adapter_path(self._capability_class(cap), subpkg).stem
            first.append(_import_from(f"{self.package}.infrastructure.{subpkg}.{stem}", [self._capability_class(cap)]))

        # Non-bootstrap datastore clients: the client TYPE (third-party, for the Provider[...]
        # annotation) + the connection factory (first-party).
        stores_with_repos = {r.store for r in self.m.infrastructure.repositories if r.store is not None}
        for ds in self.m.infrastructure.datastores:
            profile = profile_for(ds.kind)
            if ds.name not in stores_with_repos or profile.uses_bootstrap:
                continue
            if profile.resource_import and profile.resource_import not in third:
                third.append(profile.resource_import)
            subpkg = self._datastore_subpkg(ds)
            conn_mod = f"{self.package}.infrastructure.{subpkg}.connection"
            first.append(_import_from(conn_mod, [f"create_{ds.name}_client"]))

        return "\n".join(third) + "\n\n" + "\n".join(sorted(first))

    # ── REST API app bootstrap (restapi-app-bootstrap) ───────────────────────────
    # The error handler + error schema are package-agnostic boilerplate. The auth
    # artifacts are NO LONGER hardcoded — Role/CurrentUser are ordinary manifest domain
    # nodes (generated in generate_domain), and restapi/dependencies.py is DERIVED from
    # the token-verifying capability + role enum when the app has authenticated routes.

    def generate_restapi_bootstrap(self) -> list[Path]:
        def sub(text: str) -> str:
            return text.replace("{{PKG}}", self.package)

        error_handler = _ERROR_HANDLER_PY if self._has_authenticated_endpoint() else _ERROR_HANDLER_NOAUTH_PY
        written = [
            self._write(PurePosixPath("restapi", "__init__.py"), ""),
            self._write(PurePosixPath("restapi", "error_handler.py"), sub(error_handler)),
            self._write(PurePosixPath("restapi", "schemas", "errors.py"), sub(_ERRORS_SCHEMA_PY)),
        ]
        if self._has_authenticated_endpoint():
            written.append(self._write(PurePosixPath("restapi", "dependencies.py"), self._render_dependencies()))
        resources = ["errors", *sorted({s.resource for s in self.m.restapi.schemas})]
        init = self._render_schemas_init(resources)
        written.append(self._write(PurePosixPath("restapi", "schemas", "__init__.py"), init))
        return written

    # ── derived auth dependencies (get_current_user / require_role) ──────────────

    @staticmethod
    def _return_type(signature: str) -> str:
        m = re.search(r"->\s*([A-Za-z_][\w.]*)", signature)
        return m.group(1) if m else ""

    def _auth_wiring(self) -> dict:
        """Resolve the auth wiring the dependencies + routers need, FROM THE MANIFEST:
        the token-verifying capability (a capability protocol with a method returning a
        value object — the principal), that principal VO, the verify method name, the
        container provider that supplies the verifier, and (when any route is role-gated)
        the Role enum a field on the principal carries."""
        vo_names = {v.name for v in self.m.domain.value_objects}
        enum_names = {e.name for e in self.m.domain.enums}
        has_role_gate = any(e.auth.startswith("role:") for e in self.m.restapi.endpoints)
        for cap in self.m.infrastructure.capabilities:
            proto = self._capability_protocol(cap.implements)
            for pm in proto.methods:
                principal = self._return_type(pm.signature)
                if principal not in vo_names:
                    continue
                vo = next(v for v in self.m.domain.value_objects if v.name == principal)
                role_enum = role_sub = None
                if has_role_gate:
                    for f in vo.fields:
                        if _base_type(f.type) in enum_names:
                            role_enum, role_sub = _base_type(f.type), self.domain_subdomains[_base_type(f.type)]
                            break
                return {
                    "principal": principal,
                    "principal_sub": self.domain_subdomains[principal],
                    "verify_method": _method_name(pm.signature),
                    "token_provider": self._dep_provider_attr(proto.name),
                    "role_enum": role_enum,
                    "role_sub": role_sub,
                }
        raise NotImplementedError(
            "authenticated endpoints require a token-verifying capability protocol whose "
            "method returns a principal value object (e.g. ICanManageTokens.verify -> CurrentUser)"
        )

    def _render_dependencies(self) -> str:
        w = self._auth_wiring()
        role_enum = w["role_enum"]
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        domain_by_sub[w["principal_sub"]].add(w["principal"])
        if role_enum:
            domain_by_sub[w["role_sub"]].add(role_enum)
        exc_names = ["UnauthorizedError"] + (["ForbiddenError"] if role_enum else [])
        domain_lines = [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(n))}"
            for sub, n in sorted(domain_by_sub.items())
        ]
        domain_lines.append(f"from {self.package}.domain.exceptions import {', '.join(sorted(exc_names))}")
        fastapi_block = (
            "from fastapi import Depends, Request\n"
            "from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer"
        )
        groups = []
        if role_enum:
            groups.append("from collections.abc import Callable")
        groups.append(fastapi_block)
        groups.append("\n".join(sorted(domain_lines)))
        import_block = "\n\n".join(groups)
        all_names = ", ".join(f'"{n}"' for n in (["get_current_user"] + (["require_role"] if role_enum else [])))
        return self.env.get_template("restapi_dependencies.py.j2").render(
            import_block=import_block,
            all_names=all_names,
            principal=w["principal"],
            token_provider=w["token_provider"],
            verify_method=w["verify_method"],
            role_enum=role_enum,
        )

    # ── REST API: routers (endpoint functions are BODIES — §3 / §4) ──────────────
    # Route registration in main.py and the router declaration are glue (generated,
    # always overwritten). Each endpoint FUNCTION BODY is a body: the scaffold emits
    # the full route shell (decorator with path/status/response_model/responses, the
    # auth dependency, the typed signature — that is the contract surface) and a
    # contract-comment + raise NotImplementedError for the body the LLM fills.

    def generate_restapi_routers(self) -> list[Path]:
        by_resource: dict[str, list] = defaultdict(list)
        for e in self.m.restapi.endpoints:
            by_resource[e.resource].append(e)
        written = []
        for resource, endpoints in by_resource.items():
            path = PurePosixPath("restapi", "routers", f"{resource}.py")
            scaffold = self._write_scaffold(path, self._render_router_scaffold(resource, endpoints))
            if scaffold is not None:
                written.append(scaffold)
        written.append(self._write(PurePosixPath("restapi", "routers", "__init__.py"), ""))
        main = self.env.get_template("main.py.j2").render(
            package=self.package, title=self.package, resources=sorted(by_resource)
        )
        written.append(self._write(PurePosixPath("restapi", "main.py"), main))
        return written

    def _render_router_scaffold(self, resource: str, endpoints: list) -> str:
        nodes = {n.name: n for n in (*self.m.application.commands, *self.m.application.queries)}
        subdomain = self._app_subdomain(nodes[endpoints[0].handler])
        wiring = self._auth_wiring() if self._has_authenticated_endpoint() else None
        used = {
            "app": set(),
            "schemas": set(),
            "query": False,
            "query_types": set(),  # domain types referenced by GET query params (need import)
            "response": False,
            "path_param": False,
            "get_current_user": False,
            "require_role": False,
            "multipart": False,  # any endpoint takes a file upload → needs File/Form/UploadFile
        }
        functions = [self._render_endpoint_scaffold(ep, resource, nodes, used, wiring) for ep in endpoints]
        import_block = self._router_imports(subdomain, used, wiring)
        return self.env.get_template("scaffold_router.py.j2").render(
            import_block=import_block, prefix=f"/{resource}", resource=resource, endpoints=functions
        )

    def _render_endpoint_scaffold(self, ep, resource, nodes, used, wiring) -> str:
        prefix = f"/{resource}"
        sub = ep.path[len(prefix) :] or ""
        path_params = re.findall(r"{(\w+)}", sub)
        method = ep.method.lower()
        node = nodes[ep.handler]
        is_role = ep.auth.startswith("role:")
        is_anon = ep.auth == "anonymous"
        is_command = isinstance(node, Command)
        # NB: the handler class is NOT imported — the route body (the implementer's) resolves
        # it from request.app.state.container.<name>_handler(), so importing it would be unused.
        codes = ", ".join(str(c) for c in self._error_codes(node, is_role, not is_anon))

        # Auth dependency line (none for anonymous; bind `user` when caller identity
        # flows into the call — role-gated, or an authenticated mutation — else `_`).
        auth_line = None
        if not is_anon:
            principal = wiring["principal"]
            if is_role:
                used["require_role"] = True
                member = ep.auth.split(":", 1)[1]
                auth_line = f"    user: {principal} = Depends(require_role({wiring['role_enum']}.{member})),"
            else:
                used["get_current_user"] = True
                bind = "user" if is_command else "_"
                auth_line = f"    {bind}: {principal} = Depends(get_current_user),"

        fn = naming.snake_case(ep.handler)
        decorator = self._endpoint_decorator(ep, method, sub, codes)
        signature = self._endpoint_signature(ep, method, path_params, node, auth_line, used)
        contract = self._endpoint_contract(ep, node, has_caller=is_command and not is_anon)
        lines = [*decorator, f"async def {fn}(", *signature, f") -> {self._endpoint_return(ep, method, used)}:"]
        lines += [f"    {c}" for c in contract]
        lines.append(f'    raise NotImplementedError("{fn}")')
        return "\n".join(lines)

    def _endpoint_decorator(self, ep, method: str, sub: str, codes: str) -> list[str]:
        path = f'"{sub}"' if sub else '""'  # the path below the router prefix, verbatim
        lines = [f"@router.{method}(", f"    {path},"]
        if ep.response:
            lines.append(f"    response_model={ep.response},")
        status = ep.status_code or self._default_status(method)  # override else method default
        if status != 200:
            lines.append(f"    status_code={status},")
        lines.append(f"    responses=error_responses({codes}),")
        lines.append(")")
        return lines

    def _endpoint_signature(self, ep, method: str, path_params: list[str], node, auth_line, used) -> list[str]:
        # Order: positional path/body params (no default) first, then `request`, then
        # default-bearing query params, then the auth dependency — so no parameter
        # without a default follows one with a default (a Python SyntaxError otherwise).
        lines: list[str] = []
        for p in path_params:
            used["path_param"] = True
            lines.append(f"    {p}: UUID,")
        multipart_lines: list[str] = []
        if ep.request_kind == "multipart":
            # Derive the upload signature from the command's inputs: a `bytes` input is the
            # uploaded file (UploadFile), the rest are multipart Form fields. No JSON schema.
            used["multipart"] = True
            for f in node.input:
                if _base_type(f.type) == "bytes":
                    multipart_lines.append("    file: UploadFile = File(...),")
                else:
                    multipart_lines.append(f"    {f.name}: {f.type} = Form(...),")
        elif ep.request:
            used["schemas"].add(ep.request)
            lines.append(f"    body: {ep.request},")
        lines.append("    request: Request,")
        lines += multipart_lines  # defaulted params follow the no-default `request: Request`
        if method == "get":
            for f in node.input:
                if f.name in path_params:  # a path param is not also a query param
                    continue
                used["query"] = True
                for token in type_tokens(f.type):
                    if token in self.domain_subdomains:
                        used["query_types"].add(token)
                default = f" = {f.default}" if f.default is not None else ""
                lines.append(f"    {f.name}: Annotated[{f.type}, Query()]{default},")
        if auth_line:
            lines.append(auth_line)
        if ep.response:
            used["schemas"].add(ep.response)
        used["schemas"].add("error_responses")
        return lines

    def _endpoint_return(self, ep, method: str, used) -> str:
        if ep.response:
            return ep.response
        used["response"] = True
        return "Response"

    def _endpoint_contract(self, ep, node, *, has_caller: bool) -> list[str]:
        lines = [f"# Contract for {node.name} endpoint ({ep.method} {ep.path}). Implement the route body."]
        lines += self._notes_lines(ep.notes)  # non-1:1 response assembly / headers (rare)
        lines.append(f"# Resolve {node.name}Handler from request.app.state.container and dispatch.")
        if isinstance(node, Command):
            built = "caller_id=user.id + body/path fields" if has_caller else "body/path fields"
            lines.append(f"# Build the command ({built}), await execute.")
            lines.append("# Read back through the matching Get query and serialize via the response schema.")
        else:
            lines.append("# Build the query from path/query params, await execute, serialize the result.")
        if node.raises:
            lines.append(f"# Advertised errors: {', '.join(node.raises)} (raised by the handler, not the route).")
        lines.append("# Thin route: no business logic, no try/except, no logging.")
        if any(ep.sources):
            lines.append(f"# Source: {', '.join(ep.sources)}.")
        return lines

    def _error_codes(self, node, is_role: bool, is_auth: bool) -> list[int]:
        # Derived: the codes the route advertises = what its handler can raise (node.raises
        # → HTTP) plus the auth dependency's (role → 401/403, authenticated → 401).
        codes: set[int] = set()
        if is_role:
            codes |= {401, 403}
        elif is_auth:
            codes.add(401)
        for name in node.raises:
            status = self._status_for_exception(name)
            if status is not None:
                codes.add(status)
        return sorted(codes)

    @staticmethod
    def _default_status(method: str) -> int:
        """REST convention: a create returns 201, a delete 204, everything else 200."""
        return {"post": 201, "delete": 204}.get(method, 200)

    def _status_for_exception(self, name: str) -> int | None:
        for x in self.m.domain.exceptions:
            if x.name == name:
                return x.http_status
        return None

    def _router_imports(self, subdomain: str, used, wiring) -> str:
        uses_auth = used["get_current_user"] or used["require_role"]
        stdlib = []
        if used["query"]:
            stdlib.append("from typing import Annotated")
        if used["path_param"]:
            stdlib.append("from uuid import UUID")
        fastapi = ["APIRouter", "Request"]
        if uses_auth:
            fastapi.append("Depends")
        if used["query"]:
            fastapi.append("Query")
        if used["multipart"]:
            fastapi += ["File", "Form", "UploadFile"]
        third = [f"from fastapi import {', '.join(sorted(fastapi))}"]
        if used["response"]:
            third.append("from fastapi.responses import Response")
        first: list[str] = []
        # domain types referenced in the routes: the principal VO (+ Role enum on a
        # role-gated route) and any enum/VO used as a GET query param, by owning subdomain.
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        if uses_auth:
            domain_by_sub[wiring["principal_sub"]].add(wiring["principal"])
            if used["require_role"]:
                domain_by_sub[wiring["role_sub"]].add(wiring["role_enum"])
        for token in used["query_types"]:
            domain_by_sub[self.domain_subdomains[token]].add(token)
        for sub, names in domain_by_sub.items():
            first.append(_import_from(f"{self.package}.domain.{sub}", sorted(names)))
        first = sorted(first)
        local = []
        dep_names = []
        if used["get_current_user"]:
            dep_names.append("get_current_user")
        if used["require_role"]:
            dep_names.append("require_role")
        if dep_names:
            local.append(_import_from("..dependencies", dep_names))
        local.append(_import_from("..schemas", used["schemas"]))
        groups = ["\n".join(stdlib), "\n".join(third), "\n".join(first), "\n".join(local)]
        return "\n\n".join(g for g in groups if g)

    # ── REST API: schemas (restapi-schema) ──────────────────────────────────────

    def generate_restapi_schemas(self) -> list[Path]:
        by_resource: dict[str, list] = defaultdict(list)
        for s in self.m.restapi.schemas:
            by_resource[s.resource].append(s)
        # name → resource, so a schema referencing another schema defined in a DIFFERENT
        # resource file gets a cross-resource import (the vector_rag AnswerResponse →
        # ChunkResponse bug — schema files are split by resource but types cross them).
        schema_resource = {s.name: s.resource for s in self.m.restapi.schemas}
        written = []
        for resource, schemas in by_resource.items():
            path = PurePosixPath("restapi", "schemas", f"{resource}.py")
            written.append(self._write(path, self._render_schema_module(schemas, resource, schema_resource)))
        if by_resource:
            init = self._render_schemas_init(sorted(by_resource))
            written.append(self._write(PurePosixPath("restapi", "schemas", "__init__.py"), init))
        return written

    def _render_schema_module(self, schemas, resource: str, schema_resource: dict[str, str]) -> str:
        ordered = self._order_schemas(schemas)
        classes = []
        referenced = set()
        for s in ordered:
            is_update = s.name.endswith("UpdateRequest")
            decls = []
            for f in s.fields:
                referenced |= type_tokens(f.type)
                if is_update:
                    ftype = f.type if "None" in f.type else f"{f.type} | None"
                    decls.append(f"{f.name}: {ftype} = None")
                else:
                    decls.append(f"{f.name}: {f.type}")
            classes.append({"name": s.name, "fields": decls})
        # cross-resource schema references → first-party imports from the sibling module.
        cross: dict[str, set[str]] = defaultdict(set)
        for name in referenced:
            other = schema_resource.get(name)
            if other is not None and other != resource:
                cross[other].add(name)
        return self.env.get_template("restapi_schema.py.j2").render(
            all_names=sorted(s.name for s in schemas),
            classes=classes,
            import_block=self._schema_imports(referenced, cross),
        )

    def _order_schemas(self, schemas) -> list:
        """Order schemas within a module so a class that references another SAME-module schema
        is defined AFTER it (Pydantic evaluates annotations at class-definition time, and the
        house style forbids `from __future__ import annotations`, so a forward reference would
        be an undefined name). Stable base order is (_schema_rank, name); a topological pass
        then pulls referenced same-module schemas ahead of their users. (The reference-checker
        catches a violation — this is the fix it pointed at.)"""
        local = {s.name for s in schemas}
        base = sorted(schemas, key=lambda s: (self._schema_rank(s.name), s.name))

        def local_deps(s) -> set[str]:
            return ({t for f in s.fields for t in type_tokens(f.type)} & local) - {s.name}

        ordered, emitted = [], set()
        remaining = list(base)
        while remaining:
            ready = [s for s in remaining if local_deps(s) <= emitted]
            if not ready:  # a cycle (shouldn't happen for DTOs) — emit the rest in base order
                ordered.extend(remaining)
                break
            nxt = ready[0]
            ordered.append(nxt)
            emitted.add(nxt.name)
            remaining.remove(nxt)
        return ordered

    @staticmethod
    def _schema_rank(name: str) -> int:
        if name.endswith("ListResponse"):
            return 1
        if name.endswith("Response"):
            return 0
        if name.endswith("CreateRequest"):
            return 2
        return 3  # UpdateRequest

    @staticmethod
    def _schema_imports(referenced: set[str], cross: dict[str, set[str]] | None = None) -> str:
        stdlib: dict[str, set[str]] = {}
        type_imports = {
            "UUID": ("uuid", "UUID"),
            "datetime": ("datetime", "datetime"),
            "Sequence": ("collections.abc", "Sequence"),
        }
        for token in referenced:
            if token in type_imports:
                module, symbol = type_imports[token]
                stdlib.setdefault(module, set()).add(symbol)
        stdlib_block = "\n".join(f"from {m} import {', '.join(sorted(n))}" for m, n in sorted(stdlib.items()))
        pydantic_block = "from pydantic import BaseModel"
        # first-party: schema types defined in a sibling resource module
        cross_block = "\n".join(
            f"from .{res} import {', '.join(sorted(names))}" for res, names in sorted((cross or {}).items())
        )
        return "\n\n".join(b for b in (stdlib_block, pydantic_block, cross_block) if b)

    @staticmethod
    def _render_schemas_init(resources: list[str]) -> str:
        imports = f"from . import {', '.join(resources)}\n"
        imports += "\n".join(f"from .{r} import *" for r in resources)
        all_concat = " + ".join(f"{r}.__all__" for r in resources)
        return f"{imports}\n\n__all__ = {all_concat}\n"

    # ── test fakes (test-fake-repository) ───────────────────────────────────────

    def generate_fakes(self, tests_root: str | Path) -> list[Path]:
        base = Path(tests_root) / "unit" / "fakes"
        written = []
        for proto in self.m.domain.repository_protocols:
            path = base / f"fake_{naming.snake_case(proto.aggregate)}_repository.py"
            content, scaffolded = self._render_fake(proto)
            # A fully-mechanical fake is always regenerated (a transcription); a fake with a
            # scaffolded method is write-once — once the implementer fills it, don't clobber.
            if scaffolded and path.exists():
                continue
            written.append(self._write_file(path, content))
        return written

    def _render_fake(self, proto: RepositoryProtocol) -> tuple[str, bool]:
        agg = proto.aggregate
        methods = [self._fake_method(pm.signature, agg) for pm in proto.methods]
        scaffolded = any(m["scaffolded"] for m in methods)
        names = {re.match(r"async def (\w+)", pm.signature).group(1) for pm in proto.methods}
        raises_not_found = any(n.startswith("get_by_") or n in {"update", "delete"} for n in names)
        exceptions = ["NotFoundError"] if raises_not_found else []
        import_block = self._fake_imports(proto, agg, exceptions)
        content = self.env.get_template("fake_repository.py.j2").render(
            class_name=f"Fake{agg}Repository",
            entity=agg,
            methods=methods,
            import_block=import_block,
        )
        return content, scaffolded

    def _fake_method(self, sig: str, agg: str) -> dict:
        m = re.match(r"async def (\w+)\(self(?:,\s*(.*?))?\)\s*->\s*(.+)", sig)
        name, params = m.group(1), (m.group(2) or "")
        pname = params.split(":")[0].strip() if params else ""
        if name == "get_by_id":
            body = [
                f"if {pname} not in self._store:",
                f'    raise NotFoundError("{agg} not found", {{"id": str({pname})}})',
                f"return self._store[{pname}]",
            ]
        elif name.startswith("get_by_"):
            # lookup by a non-id field: linear scan over the store, NotFound if absent.
            attr = name[len("get_by_") :]
            body = [
                "for item in self._store.values():",
                f"    if item.{attr} == {pname}:",
                "        return item",
                f'raise NotFoundError("{agg} not found", {{"{attr}": str({pname})}})',
            ]
        elif name in ("add", "create", "save"):
            body = [f"self._store[{pname}.id] = {pname}"]
        elif name == "update":
            body = [
                f"if {pname}.id not in self._store:",
                f'    raise NotFoundError("{agg} not found", {{"id": str({pname}.id)}})',
                f"self._store[{pname}.id] = {pname}",
            ]
        elif name == "delete":
            body = [
                f"if {pname} not in self._store:",
                f'    raise NotFoundError("{agg} not found", {{"id": str({pname})}})',
                f"del self._store[{pname}]",
            ]
        elif name == "list":
            # Mechanical fake: return all rows in insertion order. Filtering/ordering
            # are body contracts (the real repo derives them from behaviour + the
            # signature); the fake does not anticipate them via a schema field.
            body = [
                "items = tuple(self._store.values())",
                "return items, len(items)",
            ]
        elif name == "count":
            body = ["return len(self._store)"]
        else:
            # No MECHANICAL convention for this verb (bulk ops like add_many, a semantic
            # search, delete_by_<field>, …). A fake double can't synthesize arbitrary in-
            # memory logic, and growing a closed verb table is the very disease this redesign
            # removed — so SCAFFOLD it (graceful, not a crash): the implementer fills the in-
            # memory behaviour, like any body. A scaffolded method makes the whole fake
            # write-once (see generate_fakes), so the fill is never clobbered.
            return {
                "signature": sig,
                "body": [
                    f"# No mechanical fake for {name!r}: implement the in-memory behaviour to",
                    f"# match {agg}Repository.{name}'s contract (the real adapter's store is {agg}).",
                    f'raise NotImplementedError("Fake{agg}Repository.{name}")',
                ],
                "scaffolded": True,
            }
        return {"signature": sig, "body": body, "scaffolded": False}

    def _fake_imports(self, proto: RepositoryProtocol, entity: str, exceptions: list[str]) -> str:
        # the aggregate + every domain type the protocol signatures reference (e.g. an
        # Email param, a TicketStatus filter), grouped by owning subdomain.
        referenced = {t for pm in proto.methods for t in type_tokens(pm.signature)}
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        domain_by_sub[self.domain_subdomains[entity]].add(entity)
        for token in referenced:
            if token in self.domain_subdomains:
                domain_by_sub[self.domain_subdomains[token]].add(token)
        first_party = [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(names))}"
            for sub, names in sorted(domain_by_sub.items())
        ]
        if exceptions:
            first_party.append(f"from {self.package}.domain.exceptions import {', '.join(sorted(exceptions))}")
        return "from uuid import UUID\n\n" + "\n".join(sorted(first_party))

    # ── canonical behaviour → tests (§9) ─────────────────────────────────────────
    # Per FILE the §9 degradation seam splits each node's scenarios:
    #   * FLAT scenarios → tests/unit/application/test_<node>_handler.py — generated
    #     in full from arrange/act/then, ALWAYS overwritten (a transcription of the
    #     manifest; the implementer makes them GREEN at T6 by filling the scaffold).
    #   * NON-FLAT scenarios → ..._handler_manual.py — a stub created ONCE (write-once,
    #     like a body scaffold): each becomes a skipped function carrying its contract,
    #     so the reviewer still sees every scenario the manifest owns.
    #
    # The closed `then` verbs map to a flat-dictionary assertion (no relational /
    # temporal / failure-injection logic):
    #   raises X    → with pytest.raises(X): await handler.execute(<dto>)
    #   deletes E   → after execute, get_by_id(<act id>) raises NotFoundError
    #   persists E  → after execute, the entity is in the store (fetched by the act id,
    #                 or — for a create with no id in act — the store count grew)
    #   returns E   → single-entity read: the returned entity's id matches the act id
    # NON-FLAT (→ manual stub): a `returns <*Result>` aggregate (relational — the item
    # count depends on a cross-entity filter), or `logs` / `calls` (success-event /
    # dependency-call inspection — forbidden in a handler unit test, needs more than a
    # single flat assert). This is a MINIMAL rule: `then` is not grown into a test DSL.

    def generate_application_tests(self, tests_root: str | Path) -> list[Path]:
        base = Path(tests_root) / "unit" / "application"
        written = []
        for node in (*self.m.application.commands, *self.m.application.queries):
            if not node.behaviour:
                continue
            is_command = isinstance(node, Command)
            flat = [sc for sc in node.behaviour if self._is_flat(node, sc)]
            manual = [sc for sc in node.behaviour if not self._is_flat(node, sc)]
            if flat:
                path = base / f"test_{naming.snake_case(node.name)}_handler.py"
                written.append(self._write_file(path, self._render_handler_test(node, is_command, flat)))
            if manual:
                path = base / f"test_{naming.snake_case(node.name)}_handler_manual.py"
                # write-once: the implementer owns the manual stub once it exists (§9).
                if not path.exists():
                    written.append(self._write_file(path, self._render_manual_stub(node, is_command, manual)))
        return written

    def generate_domain_tests(self, tests_root: str | Path) -> list[Path]:
        """One write-once manual stub per entity that declares invariants — the canonical
        test the scaffolded `__post_init__` must satisfy (§9). Manual because a bound/range
        needs example inputs (§14.1); the implementer fills the ValidationError assertion."""
        base = Path(tests_root) / "unit" / "domain"
        written = []
        for e in self.m.domain.entities:
            if not e.invariants:
                continue
            functions = [
                {
                    "name": f"test_{naming.snake_case(e.name)}_{self._slug(inv.rule)}",
                    "contract": [
                        f"# invariant: {inv.rule}",
                        f"# field: {inv.field} · source: {inv.source}" if inv.field else f"# source: {inv.source}",
                    ],
                }
                for inv in e.invariants
            ]
            path = base / e.subdomain / f"test_{naming.snake_case(e.name)}_entity_manual.py"
            if not path.exists():  # write-once
                content = self.env.get_template("domain_entity_test_manual.py.j2").render(
                    entity=e.name, functions=functions
                )
                written.append(self._write_file(path, content))
        return written

    def _is_flat(self, node, sc) -> bool:
        """A scenario is FLAT iff its `then` is one flat-dictionary assertion with no
        relational / temporal / failure-injection logic (§9). `raises`, `deletes`,
        `persists`, and a single-entity `returns` (output is a domain entity) are flat;
        a `returns <*Result>` aggregate (relational), `logs`, and `calls` are not.

        The flat test injects exactly ONE fake repository, so a handler is flat-eligible
        only when it has exactly one dependency and that dependency is a repository. Any
        capability/service dependency — or a SECOND repository for a multi-aggregate write
        — makes it non-flat; wiring the extra fakes is the implementer's job (→ manual
        stub)."""
        repo_names = {p.name for p in self.m.domain.repository_protocols}
        deps = node.handler.dependencies
        if len(deps) != 1 or any(d not in repo_names for d in deps):
            return False
        then = sc.then
        if then.raises or then.deletes or then.persists:
            return True
        if then.returns:
            return then.returns in self.entity_subdomains  # a domain entity, not a *Result DTO
        return False  # logs / calls

    def _render_handler_test(self, node, is_command: bool, scenarios) -> str:
        proto = self._node_repo(node)
        dto = f"{node.name}Command" if is_command else f"{node.name}Query"
        handler_class = f"{node.name}Handler"
        fake_class = f"Fake{proto.aggregate}Repository"
        entity = self._entity(proto.aggregate)

        # A seed entity needs a `_make_<entity>` builder iff any scenario arranges one.
        needs_builder = any(sc.arrange for sc in scenarios)
        arg_keyword = "cmd" if is_command else "query"
        has_caller = is_command and self._command_has_caller(node)

        tests, seen, raised, needs_pytest = [], {}, set(), False
        for sc in scenarios:
            name = self._unique_test_name(sc.given, seen)
            seed_lines = self._seed_lines(sc, entity, fake_class)
            dto_lines = self._dto_lines(node, dto, has_caller, sc, arg_keyword)
            assert_lines, sc_raised, sc_pytest = self._flat_assert(node, sc, arg_keyword, entity)
            raised |= sc_raised
            needs_pytest = needs_pytest or sc_pytest
            tests.append({"name": name, "given": sc.given, "seed": seed_lines + dto_lines, "body": assert_lines})

        # UUID(...) literals appear iff some act addresses a UUID input or a seed
        # overrides a UUID field — otherwise importing UUID is a dead (F401) import.
        needs_uuid_ctor = self._tests_use_uuid_literal(node, entity, scenarios)
        # domain types a `then.with` post-state assert references (e.g. TicketStatus) must
        # be imported even when there is no builder to import them.
        with_types: set[str] = set()
        for sc in scenarios:
            for field in sc.then.with_:
                for token in type_tokens(self._entity_field_type(entity, field)):
                    if token in self.domain_subdomains:
                        with_types.add(token)
        import_block = self._test_imports(
            proto,
            dto,
            handler_class,
            fake_class,
            sorted(raised),
            has_pytest=needs_pytest,
            has_caller=has_caller,
            needs_builder=needs_builder,
            needs_uuid_ctor=needs_uuid_ctor,
            with_types=with_types,
        )
        builder = self._builder_lines(entity) if needs_builder else None
        return self.env.get_template("application_handler_test.py.j2").render(
            import_block=import_block,
            tests=tests,
            fake_class=fake_class,
            handler_class=handler_class,
            has_caller=has_caller,
            builder=builder,
        )

    def _render_manual_stub(self, node, is_command: bool, scenarios) -> str:
        """A write-once stub (§9): each NON-FLAT scenario becomes a skipped function
        carrying its full contract-comment, so the reviewer sees every scenario the
        manifest owns. The implementer replaces the skip with a real assertion."""
        seen = {}
        functions = []
        for sc in scenarios:
            name = self._unique_test_name(sc.given, seen)
            functions.append({"name": name, "contract": self._manual_contract(node, sc)})
        return self.env.get_template("application_handler_test_manual.py.j2").render(
            node_name=node.name, functions=functions
        )

    def _manual_contract(self, node, sc) -> list[str]:
        lines = [f"# given: {sc.given}"]
        if sc.arrange:
            seeds = "; ".join(f"{s.entity}({s.fields})" for s in sc.arrange)
            lines.append(f"# arrange: {seeds}")
        if sc.act:
            lines.append(f"# act: {sc.act}")
        lines.append(f"# then: {self._then_outcome(sc.then)}")
        lines.append(f"# Source: {', '.join(node.sources)}.")
        return lines

    @staticmethod
    def _unique_test_name(given: str, seen: dict[str, int]) -> str:
        base_name = f"test_{Generator._slug(given)}"
        name = base_name if base_name not in seen else f"{base_name}_{seen[base_name]}"
        seen[base_name] = seen.get(base_name, 1) + 1
        return name

    def _builder_lines(self, entity: Entity) -> list[str]:
        """A module-level `_make_<entity>(**overrides)` builder (house style — see the
        test-domain-entity skill): a fully-defaulted entity the seed overrides per
        scenario, so seed lines stay short and only carry the fields that matter."""
        snake = naming.snake_case(entity.name)
        lines = [f"def _make_{snake}(**overrides: object) -> {entity.name}:", "    defaults = dict("]
        for f in entity.fields:
            lines.append(f"        {f.name}={f.default if f.default is not None else self._field_filler(f)},")
        lines.append("    )")
        lines.append(f"    return {entity.name}(**{{**defaults, **overrides}})")
        return lines

    def _field_filler(self, field) -> str:
        """A deterministic placeholder for a required entity field — keyed off the
        declared type (UUID → uuid4(), str → a label, datetime → a fixed instant).
        The exact value is incidental to a FLAT assert (the seed overrides what matters)."""
        base = _base_type(field.type)
        return {
            "UUID": "uuid4()",
            "str": f'"{field.name}"',
            "bool": "False",
            "int": "0",
            "datetime": "datetime(2026, 1, 1)",
        }[base]

    def _seed_lines(self, sc, entity: Entity, fake_class: str) -> list[str]:
        """Seed the fake's starting state from `arrange`: each seed is the builder with
        only the scenario's literal field overrides; the rest default from the builder."""
        if not sc.arrange:
            return [f"repo = {fake_class}()"]
        snake = naming.snake_case(entity.name)
        seeds = []
        for seed in sc.arrange:
            overrides = ", ".join(
                f"{k}={self._py_literal(v, self._entity_field_type(entity, k))}" for k, v in seed.fields.items()
            )
            seeds.append(f"_make_{snake}({overrides})")
        return [f"repo = {fake_class}(", f"    items=[{', '.join(seeds)}],", ")"]

    @staticmethod
    def _entity_field_type(entity: Entity, name: str) -> str:
        return next((f.type for f in entity.fields if f.name == name), "str")

    def _dto_lines(self, node, dto: str, has_caller: bool, sc, arg_keyword: str) -> list[str]:
        """Bind the command/query DTO to a local (`cmd`/`query`) from the scenario's
        `act` (input field name → literal). A caller-bearing command prepends
        caller_id=_CALLER. The local keeps the `handler.execute(<dto>)` line short."""
        input_types = {f.name: f.type for f in node.input}
        args = ["caller_id=_CALLER"] if has_caller else []
        for key, value in sc.act.items():
            args.append(f"{key}={self._py_literal(value, input_types.get(key, 'str'))}")
        single = f"{arg_keyword} = {dto}({', '.join(args)})"
        if len(single) <= 100:
            return [single]
        body = [f"{arg_keyword} = {dto}("] + [f"    {a}," for a in args] + [")"]
        return body

    def _flat_assert(self, node, sc, arg_keyword: str, entity: Entity):
        """The then→verb assertion table (§9). Returns (lines, raised_set, needs_pytest).
        The DTO is bound to `cmd`/`query` by `_dto_lines`; we dispatch that local."""
        then = sc.then
        call = f"await handler.execute({arg_keyword})"
        if then.raises:
            return ([f"with pytest.raises({then.raises}):", f"    {call}"], {then.raises}, True)
        if then.deletes:
            act_id = self._act_id_literal(node, sc)
            return (
                [call, "", "with pytest.raises(NotFoundError):", f"    await repo.get_by_id({act_id})"],
                {"NotFoundError"},
                True,
            )
        if then.persists:
            act_id = self._act_id_literal(node, sc)
            if act_id is not None:
                lines = [call, "", f"stored = await repo.get_by_id({act_id})", f"assert stored.id == {act_id}"]
                # post-state (`then.with`): assert each expected field on the saved entity —
                # this is what makes a no-op "re-save unchanged" body go RED.
                for field, value in then.with_.items():
                    ftype = self._entity_field_type(entity, field)
                    lines.append(f"assert stored.{field} == {self._py_literal(value, ftype)}")
                return (lines, set(), False)
            # a create with no id in `act`: the handler mints the id — assert the store
            # grew (count) rather than fetch by an id we don't have.
            lines = [
                "before = (await repo.list(True))[1]",
                call,
                "",
                "after = (await repo.list(True))[1]",
                "assert after == before + 1",
            ]
            return (lines, set(), False)
        # single-entity returns: the returned entity's id matches the act id
        act_id = self._act_id_literal(node, sc)
        return ([f"result = {call}", "", f"assert result.id == {act_id}"], set(), False)

    def _act_id_literal(self, node, sc) -> str | None:
        """The identity literal the act addresses (the lone UUID input), rendered as a
        Python literal — used to fetch back / assert. None when act carries no id (a
        create, whose id the handler mints)."""
        input_types = {f.name: f.type for f in node.input}
        for key, value in sc.act.items():
            if _base_type(input_types.get(key, "")) == "UUID":
                return self._py_literal(value, "UUID")
        return None

    def _py_literal(self, value, declared_type: str) -> str:
        """Render a YAML scalar as a Python literal, keyed off the field's declared type:
        UUID → UUID("…"), str → quoted, bool/int → as-is, a domain enum → Enum.MEMBER.
        Centralized so seed ids, act ids, and post-state asserts all match."""
        base = _base_type(declared_type)
        for en in self.m.domain.enums:
            if en.name == base:
                member = next((m for m in en.members if str(value) in (m.name, m.value)), None)
                if member is None:
                    raise ValueError(f"{value!r} is not a member of enum {en.name}")
                return f"{en.name}.{member.name}"
        if base == "UUID":
            return f'UUID("{value}")'
        if base == "str":
            return repr(str(value))
        if base == "bool":
            return "True" if value else "False"
        if base == "int":
            return str(int(value))
        return repr(value)

    @staticmethod
    def _then_str(then) -> str:
        for verb in ("returns", "persists", "deletes", "logs", "calls"):
            value = getattr(then, verb)
            if value:
                return f"{verb} {value}"
        return "outcome"

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

    def _tests_use_uuid_literal(self, node, entity: Entity, scenarios) -> bool:
        """A `UUID("…")` literal is rendered iff an act addresses a UUID input field or
        a seed overrides a UUID entity field. (A pure-`name` create needs no UUID ctor.)"""
        input_types = {f.name: f.type for f in node.input}
        for sc in scenarios:
            if any(_base_type(input_types.get(k, "")) == "UUID" for k in sc.act):
                return True
            for seed in sc.arrange:
                if any(_base_type(self._entity_field_type(entity, k)) == "UUID" for k in seed.fields):
                    return True
        return False

    def _test_imports(
        self,
        proto,
        dto,
        handler_class,
        fake_class,
        raised,
        *,
        has_pytest,
        has_caller,
        needs_builder,
        needs_uuid_ctor,
        with_types=frozenset(),
    ) -> str:
        # uuid symbols: UUID(...) for act/seed id literals (when present); uuid4 for the
        # _CALLER (commands) and the seed builder's required-UUID fillers.
        uuid_symbols: set[str] = set()
        if needs_uuid_ctor:
            uuid_symbols.add("UUID")
        if has_caller or needs_builder:
            uuid_symbols.add("uuid4")
        stdlib = [f"from uuid import {', '.join(sorted(uuid_symbols))}"] if uuid_symbols else []
        if needs_builder and self._builder_uses_datetime(proto):
            stdlib.insert(0, "from datetime import datetime")
        groups = ["\n".join(stdlib)]
        if has_pytest:
            groups.append("import pytest")
        app_names = ", ".join(sorted([dto, handler_class]))
        first_party = [f"from {self.package}.application.{proto.subdomain} import {app_names}"]
        # Domain types to import (grouped by owning subdomain): the builder constructs the
        # entity directly → it + every domain type its fields reference; and any enum/VO a
        # `then.with` post-state assert names (TicketStatus) — even with no builder.
        domain_by_sub: dict[str, set[str]] = defaultdict(set)
        if needs_builder:
            entity = self._entity(proto.aggregate)
            domain_by_sub[entity.subdomain].add(entity.name)
            for f in entity.fields:
                for token in type_tokens(f.type):
                    if token in self.domain_subdomains:
                        domain_by_sub[self.domain_subdomains[token]].add(token)
        for token in with_types:
            domain_by_sub[self.domain_subdomains[token]].add(token)
        first_party += [
            f"from {self.package}.domain.{sub} import {', '.join(sorted(names))}"
            for sub, names in sorted(domain_by_sub.items())
        ]
        if raised:
            first_party.append(f"from {self.package}.domain.exceptions import {', '.join(raised)}")
        fake_module = f"fake_{naming.snake_case(proto.aggregate)}_repository"
        first_party.append(f"from tests.unit.fakes.{fake_module} import {fake_class}")
        groups.append("\n".join(sorted(first_party)))
        return "\n\n".join(g for g in groups if g)

    def _builder_uses_datetime(self, proto) -> bool:
        entity = self._entity(proto.aggregate)
        return any(_base_type(f.type) == "datetime" and f.default is None for f in entity.fields)

    @staticmethod
    def _write_file(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def _write(self, rel: PurePosixPath, content: str) -> Path:
        return self._write_file(self.root / rel, content)

    def _write_scaffold(self, rel: PurePosixPath, content: str) -> Path | None:
        """Write a body-bearing scaffold ONCE (§4): never overwrite an existing file.

        Once the implementer LLM owns the file, the generator never touches it again —
        contract drift surfaces as red mypy on the existing body, not a clobber. Returns
        None when the file already exists (nothing written)."""
        path = self.root / rel
        if path.exists():
            return None
        return self._write_file(path, content)

    def _copy_scaffold(self, scaffold_name: str, rel: PurePosixPath) -> Path:
        """Copy a §8 scaffold file verbatim into the target. These reference-app
        files are package-agnostic (relative imports only), so they are copied,
        not generated from the manifest. See codegen/scaffold/README.md."""
        return self._write(rel, (_SCAFFOLD / scaffold_name).read_text())
