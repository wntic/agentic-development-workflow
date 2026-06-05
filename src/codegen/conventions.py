"""Shared house-style constants the pipeline derives from (not per-epic data).

These encode skill-catalog conventions both the validator (resolution) and the
generator (emission) need. They are NOT manifest data — they are the fixed
vocabulary the skills define.
"""

# domain-exception standard catalog: name → (code, http_status, parent).
# `DomainError` is the always-present root and is not listed here. An epic
# references these by name (in `raises:` / `errors:`); the generator emits only
# the ones the graph actually reaches, plus their parent chain.
STANDARD_EXCEPTIONS: dict[str, tuple[str, int, str]] = {
    "NotFoundError": ("NOT_FOUND", 404, "DomainError"),
    "ConflictError": ("CONFLICT", 409, "DomainError"),
    "ValidationError": ("VALIDATION_ERROR", 422, "DomainError"),
    "ForbiddenError": ("FORBIDDEN", 403, "DomainError"),
    "UnauthorizedError": ("UNAUTHORIZED", 401, "DomainError"),
    "InUseError": ("IN_USE", 409, "ConflictError"),
}

# NOTE: there is deliberately no enumeration of "supported operations" here, and
# no generate-vs-scaffold axis. Under scaffold-first (spec §3) the generator emits
# declarative + glue deterministically and SCAFFOLDS every body — there are no
# templated body shapes to enumerate. Whether a node is generated or scaffolded is
# DERIVED from its category (every handler / repository / endpoint body is a
# scaffold the implementer LLM fills), never declared. Putting an operation
# vocabulary here would be a second source of truth and a false ceiling on what
# apps the pipeline can describe.
