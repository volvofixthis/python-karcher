# AGENTS.md
Guidance for coding agents working in `python-karcher`.

## Scope
- This repo is a Python library and CLI for Kärcher Home robots.
- Main package: `karcher/`.
- Tests live in `tests/` and currently use `unittest`.
- Packaging is setuptools-based via `setup.py`.
- CI behavior is defined in `.github/workflows/python.yml`.

## Rules Files
- No repository-specific Cursor rules were found in `.cursor/rules/`.
- No `.cursorrules` file was found.
- No Copilot instructions file was found at `.github/copilot-instructions.md`.
- If any of those files are added later, treat them as higher-priority repo guidance and update this file.

## Environment Notes
- CI targets Python `3.9`.
- Ruff runs with `--target-version=py39`.
- Prefer changes that remain compatible with Python 3.9+.
- Do not hand-edit generated artifacts in `build/`, `dist/`, `*.egg-info/`, or `__pycache__/`.

## Repository Layout
- `karcher/cli.py`: Click CLI entrypoint exposed as `karcher-home`.
- `karcher/karcher.py`: main async HTTP client and MQTT-facing control methods.
- `karcher/device.py`, `karcher/auth.py`, `karcher/user.py`: model objects.
- `karcher/utils.py`: crypto, casing helpers, ids, and timestamps.
- `karcher/map.py`: protobuf map parsing.
- `karcher/mapdata_pb2.py` and `karcher/mapdata_pb2.pyi`: generated protobuf output.
- `tests/test_enc.py`: current regression tests for encryption helpers.
- `build/lib/karcher/`: build output mirror of the package; do not edit directly.

## Install And Setup
Use these commands for a clean local environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install ruff twine build
pip install -e .
```

## Build Commands
- Package build: `python -m build`
- Validate artifacts: `python -m twine check dist/*`
- Bytecode sanity check: `python -m compileall karcher`

Recommended local release-quality sequence:

```bash
ruff --target-version=py39 . && python -m unittest discover -s tests -p 'test_*.py' && python -m build && python -m twine check dist/*
```

## Lint Commands
CI runs Ruff in two passes:

```bash
ruff --output-format=github --select=E9,F63,F7,F82 --target-version=py39 .
ruff --output-format=github --target-version=py39 .
```

Useful local variants:
- Full lint: `ruff --target-version=py39 .`
- One file: `ruff --target-version=py39 karcher/cli.py`
- Tests only: `ruff --target-version=py39 tests`

Ruff config notes from `ruff.toml`:
- Generated protobuf files matching `*_pb2.py*` are excluded.
- `E501` is ignored for `tests/test_*.py` and `karcher/consts.py`.

## Test Commands
Primary test runner is `unittest`, not `pytest`.

- Run all tests: `python -m unittest discover -s tests -p 'test_*.py'`
- Run default discovery: `python -m unittest discover`
- Run one test module: `python -m unittest tests.test_enc`
- Run one test class: `python -m unittest tests.test_enc.TestEncryption`
- Run one test method: `python -m unittest tests.test_enc.TestEncryption.test_encrypt`

When adding tests:
- Put them in `tests/`.
- Name files `test_*.py`.
- Prefer deterministic unit tests with no network dependency.
- Follow existing `unittest.TestCase` style unless the repo is intentionally migrated.

## CLI And Runtime Checks
- Installed CLI entrypoint: `karcher-home`
- Prefer `karcher-home --help` after editable install rather than inventing a new wrapper.
- If you need a quick sanity check without packaging, use `python -m compileall karcher` or a tiny one-off Python snippet.

## Code Style
Follow existing file-local style first; this repo is not fully auto-formatted.

### Imports
- Group imports as standard library, third-party, then local package imports.
- Prefer explicit imports; do not use wildcard imports.
- Keep package-local imports in `karcher/` using the existing relative `.module` style.
- Remove unused imports; Ruff will catch many of them.

### Formatting
- Use 4-space indentation.
- Keep surrounding file style consistent.
- Older modules often prefer single quotes; some newer CLI code uses double quotes. Do not churn files just to normalize quoting.
- Use blank lines to separate top-level defs and logical sections.
- Keep comments sparse and practical.
- Avoid unrelated formatting changes in focused patches.

### Types
- Add type hints for new or modified public functions when reasonable.
- Improve typing incrementally; do not force a repo-wide annotation pass.
- Match the surrounding file's style for generics and annotations.
- Existing code commonly uses `typing.List` and `typing.Any`; consistency matters more than modernization.
- Be careful with model type changes because API payloads may be partial or loosely shaped.

### Naming
- Functions, methods, and variables use `snake_case`.
- Classes use `PascalCase`.
- Enum members follow local enum style; preserve existing casing.
- Preserve upstream API field names exactly inside HTTP and MQTT payloads.
- Convert remote camelCase fields to snake_case at model boundaries, following existing helpers.

### Data Models
- Models in `auth.py`, `device.py`, and `user.py` use `@dataclass(init=False)` plus custom `__init__` parsing.
- When extending these models, keep constructor behavior tolerant of partial payloads.
- Use `fields(self)` name filtering, matching current patterns.
- Do not break deserialization from real API responses.

### Async And Networking
- `KarcherHome.create`, `login`, `logout`, `get_devices`, and similar HTTP methods are async.
- Preserve the current split: HTTP work is async, MQTT control helpers are mostly sync wrappers.
- Always close owned `aiohttp` sessions with `await kh.close()`.
- Reuse `_request()` and `_process_response()` for HTTP work instead of duplicating auth headers or signing logic.
- Keep request-signing behavior intact; it is central to compatibility.

### Error Handling
- Raise `KarcherHomeAccessDenied` when session/auth state is missing.
- Raise `KarcherHomeException` or a specific subclass for API/domain failures.
- In CLI code, use `click.BadParameter` for invalid user input.
- Preserve exception chaining with `raise ... from ex` when translating parse or IO errors.
- Do not silently swallow protocol or parsing failures unless the surrounding code already intentionally does so.

### CLI Conventions
- New commands belong in `karcher/cli.py` and should follow the existing Click decorator pattern.
- Reuse the shared `authorize()` helper.
- For device-targeted commands, resolve the device by iterating `await kh.get_devices()` and matching `device_id`.
- If a device is missing, raise `click.BadParameter("Device ID not found.")`.
- Print results through `ctx.obj.print(...)` so output-format flags keep working.
- Let Click derive hyphenated command names from underscored function names.

### API Payload Conventions
- Preserve server field casing exactly as expected by the upstream API.
- Keep payload construction localized in `karcher/karcher.py` methods.
- MQTT helpers should keep returning dicts with keys like `published`, `topic`, `qos`, `payload`, and `reply` when applicable.
- HTTP helpers should generally return processed results from `_process_response()`.

### Testing Expectations
- If you touch crypto or utility helpers, add or update unit tests.
- If you touch CLI parsing, prefer tests around parsing helpers when feasible.
- For network-facing features, prefer testing pure payload construction or response handling over live calls.
- If no good automated test fits, at minimum run Ruff and `python -m compileall karcher`.

## Files To Avoid Editing Directly
- `build/lib/**`: generated build output.
- `karcher/mapdata_pb2.py` and `karcher/mapdata_pb2.pyi`: generated protobuf code unless regeneration is intentional.
- Cache directories such as `__pycache__/`.

## Good Agent Behavior In This Repo
- Make focused edits with minimal diffs.
- Preserve public CLI and library compatibility unless the task explicitly changes it.
- Verify commands against actual repo config instead of assuming pytest, black, or mypy are in use.
- When documenting commands for users, prefer the installed `karcher-home` CLI name.
