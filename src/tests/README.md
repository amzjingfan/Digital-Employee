# Repository test suites

All executable repository tests live under this root and are grouped by purpose.

| Category | Directory | Current status |
| --- | --- | --- |
| Backend | `src/tests/src/backend/` | Active; contains the Python pytest suite. |
| Frontend | `src/tests/frontend/` | Active; contains the TypeScript Vitest suite. |
| Integration | `src/tests/integration/` | Active; contains cross-module acceptance and replay runners. |
| Packaging | `src/tests/src/packaging/` | Active; contains platform and bundled-runtime smoke runners. |

Run all commands from the repository root.

Backend tests:

```powershell
src\backend\.venv\Scripts\python.exe -m pytest -c pytest.ini src\tests\backend
```

Frontend tests and type checking:

```powershell
npm --prefix frontend-enterprise test
npm --prefix frontend-enterprise run test:typecheck
```

The TikTok replay is deterministic and must report `external_writes=false`:

```powershell
src\backend\.venv\Scripts\python.exe src\tests\integration\run_tiktok_mock_sop_replay.py
```

The DesignKit acceptance runner needs a real downloaded image and writes acceptance
records to the configured PostgreSQL database and object storage. Run it only against
the intended test tenant:

```powershell
src\backend\.venv\Scripts\python.exe src\tests\integration\run_designkit_e2e.py <image-file>
```

Packaging checks take a prepared runtime or package artifact. The macOS application
and Linux Docker checks require their target platforms:

```powershell
src\backend\.venv\Scripts\python.exe src\tests\src\packaging\smoke_sandbox_bundle.py <sandbox-runtime>
src\backend\.venv\Scripts\python.exe src\tests\src\packaging\smoke_sandbox_runtime.py <sandbox-runtime>
bash src/tests/src/packaging/smoke_macos_app.sh [StaffDeck.app]
docker run --rm --platform linux/amd64 -v "${PWD}:/work" ubuntu:22.04 bash /work/src/tests/src/packaging/docker_test_linux.sh
```

Check the repository boundary after staging changes so the command reads the updated
Git index:

```powershell
src\backend\.venv\Scripts\python.exe src\tests\check_test_layout.py
```

Place executable repository tests under the matching `src/tests/` category. Python test
modules use `test_*.py` or `*_test.py`; frontend tests use `*.test.ts` or
`*.test.tsx`, matching both Vitest collection and the test TypeScript project.
`.spec.*` files and JavaScript variants such as `*.test.js`, `*.test.mjs`, and
`*.test.cjs` are rejected because this repository does not collect or type-check them.
Support setup such as `src/frontend-enterprise/src/test/setup.ts` remains with production
tooling. Skill evaluation data at `skills/*/evals/cases.json` remains with each
published skill package because it is runtime data, not an executable test.
