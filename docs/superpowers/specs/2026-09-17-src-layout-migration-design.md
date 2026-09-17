# `src/` Repository Layout Migration Design

## Goal

Move every executable project area below one repository-level `src/` directory while keeping repository governance and documentation at the root. The application must retain the same supported development, test, packaging, and single-port runtime behavior after the move.

## Target layout

```text
joukir/
├── src/
│   ├── backend/
│   ├── deploy/
│   ├── frontend-enterprise/
│   ├── packaging/
│   ├── scripts/
│   ├── skills/
│   └── tests/
├── docs/
├── .github/
├── AGENTS.md
├── CONTRIBUTING.md
├── README.md
├── README.zh.md
├── pytest.ini
└── ruff.toml
```

Repository-wide policy, CI metadata, public documentation, and root configuration remain at the root. Runtime configuration and ignored dependency/build directories move with their owning project, including `src/backend/.env`, `src/backend/.venv`, and `src/frontend-enterprise/node_modules`.

## Path rules

- Root commands address executable areas through `src/`.
- Lifecycle scripts derive the repository root from `src/scripts/` and keep runtime state in root `.dev/`.
- Python imports use `src/backend` through `pytest.ini` and command working directories.
- Frontend tests remain outside the frontend package at `src/tests/frontend` and extend `src/frontend-enterprise/tsconfig.json`.
- CI, release, packaging, deployment, and migration verification paths use the new layout.
- Historical evidence files retain historical path statements where changing them would rewrite the record; current indexes and runbooks point to the new paths.

## Verification contract

The migration is accepted only after tracked layout checks, Python compile/import checks, the test-layout gate, backend tests, frontend tests/typecheck/i18n/config/build checks, migration evidence checks, and a real detached single-port startup plus `/api/health` request succeed or are shown to have only documented pre-existing external-service failures. The application is stopped again after the smoke test.

## Risks and controls

- Relative-path assumptions can remain in scripts and CI. A repository scan and platform-specific smoke tests cover active references.
- Moving an existing virtual environment can preserve stale absolute launcher paths. Verification calls the environment's Python executable directly and rebuilds the environment if it is unusable.
- Local secrets must move without being printed or staged. Git status and ignore checks verify `src/backend/.env` remains ignored.
- Packaging commands can be platform-specific. Windows checks run locally; Linux/macOS paths are updated and validated structurally in CI configuration and test scripts.
