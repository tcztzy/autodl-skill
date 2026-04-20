# Repository Instructions

## Scope

These instructions apply to the whole repository.

## Python Style

- Target Python 3.14 or newer.
- Write module, class, function, and method docstrings in Google style.
- Treat Python code as statically typed code. Add and maintain explicit type annotations for public and internal functions.
- Prefer built-in generic syntax, for example `list[str]`, `dict[str, int]`, `set[str]`, and `tuple[str, ...]`.
- Use `T | None` instead of `Optional[T]`.
- Do not add `from __future__ import annotations`.
- Do not use legacy aliases such as `typing.List`, `typing.Dict`, `typing.Set`, `typing.Tuple`, or `typing.Optional`.
- Prefer precise types, `TypedDict`, `Protocol`, `Literal`, `type` aliases, and `collections.abc` interfaces over broad dynamic types.
- Avoid `Any` unless there is no practical typed boundary.

## Quality Gates

Use Ruff and ty as the project quality controls. Before handing off Python changes, run:

```sh
uv run ruff format --check src/autodl
uv run ruff check src/autodl
uv run ty check src/autodl
```

When formatting is needed, run:

```sh
uv run ruff format src/autodl
```

Fix quality gate failures in code instead of weakening annotations or suppressing diagnostics.

## Change Discipline

- Keep diffs focused on the requested behavior or cleanup.
- Do not rewrite unrelated files or revert user changes.
- Keep CLI behavior and JSON output stable unless the task explicitly asks for a behavior change.
