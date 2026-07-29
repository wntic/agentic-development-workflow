# The single definition of "green" for this project: these four commands, no more. A human and an
# agent both learn the state of the code the same way — by running `make check` and reading it.

.PHONY: check

check:
	uv run ruff check
	uv run ruff format --check
	uv run mypy src tests
	uv run pytest
