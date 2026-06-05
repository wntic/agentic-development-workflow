"""Path and name derivation (MANIFEST_SCHEMA.md "Path and naming derivation").

The manifest carries identifiers only; module paths and file names are derived
here. Paths are returned relative to the generated package root (e.g. src/myapp).
"""

import re
from pathlib import PurePosixPath


def snake_case(name: str) -> str:
    """PascalCase → snake_case. `ITagRepository` → `i_tag_repository`.

    Acronym runs (e.g. OTP) are not yet special-cased; revisit when an OTP-style
    identifier reaches the pipeline.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def entity_path(name: str, subdomain: str) -> PurePosixPath:
    return PurePosixPath("domain", subdomain, f"{snake_case(name)}.py")


def protocol_path(name: str, subdomain: str) -> PurePosixPath:
    # `name` already carries the I-prefix and Repository suffix (ITagRepository).
    return PurePosixPath("domain", subdomain, f"{snake_case(name)}.py")


def domain_path(name: str, subdomain: str) -> PurePosixPath:
    """Generic domain module path (enum / value object / service / capability protocol):
    one module per artifact, named the artifact in snake_case, under its subdomain."""
    return PurePosixPath("domain", subdomain, f"{snake_case(name)}.py")


def settings_module(name: str) -> str:
    """Module STEM for a settings class: one class per module, named after the class
    (`JwtSettings` → `jwt_settings`). Several settings can then share a subpackage without
    clobbering a single `settings.py` (the house rule: a module is named for its one class)."""
    return snake_case(name)


def settings_path(name: str, subpackage: str) -> PurePosixPath:
    return PurePosixPath("infrastructure", subpackage, f"{settings_module(name)}.py")


def capability_adapter_path(class_name: str, subpackage: str) -> PurePosixPath:
    """`infrastructure/<subpackage>/<snake(class_name)>.py` — the module is named for its one
    adapter class (e.g. OpenaiTextEmbedder → openai_text_embedder.py), per the house rule."""
    return PurePosixPath("infrastructure", subpackage, f"{snake_case(class_name)}.py")


def exceptions_path() -> PurePosixPath:
    return PurePosixPath("domain", "exceptions.py")


def command_dto_path(name: str, subdomain: str) -> PurePosixPath:
    return PurePosixPath("application", subdomain, f"{snake_case(name)}_command.py")


def query_dto_path(name: str, subdomain: str) -> PurePosixPath:
    return PurePosixPath("application", subdomain, f"{snake_case(name)}_query.py")


def result_dto_path(result_name: str, subdomain: str) -> PurePosixPath:
    return PurePosixPath("application", subdomain, f"{snake_case(result_name)}.py")


def handler_path(name: str, subdomain: str) -> PurePosixPath:
    return PurePosixPath("application", subdomain, f"{snake_case(name)}_handler.py")


def pluralize(word: str) -> str:
    if word.endswith("y") and word[-2:-1] not in "aeiou":
        return f"{word[:-1]}ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return f"{word}es"
    return f"{word}s"


def table_name(aggregate: str) -> str:
    return pluralize(snake_case(aggregate))


def table_path(aggregate: str, subpackage: str) -> PurePosixPath:
    return PurePosixPath("infrastructure", subpackage, "tables", f"{table_name(aggregate)}.py")


def repository_path(aggregate: str, subpackage: str) -> PurePosixPath:
    return PurePosixPath("infrastructure", subpackage, "repositories", f"{snake_case(aggregate)}_repository.py")


def package_init_path(*parts: str) -> PurePosixPath:
    return PurePosixPath(*parts, "__init__.py")
