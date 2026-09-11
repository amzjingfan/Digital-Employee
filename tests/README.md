# Repository test suites

All executable repository tests live under this root and are grouped by purpose.

| Category | Directory | Current status |
| --- | --- | --- |
| Backend | `tests/backend/` | Active; contains the Python pytest suite. |
| Frontend | `tests/frontend/` | Active; contains the TypeScript Vitest suite. |
| Integration | `tests/integration/` | Active; contains cross-module acceptance and replay runners. |
| Packaging | `tests/packaging/` | Active; contains platform and bundled-runtime smoke runners. |

Run all commands from the repository root.

Backend tests:

```powershell
backend\.venv\Scripts\python.exe -m pytest -c pytest.ini tests\backend
```

Frontend tests and type checking:

```powershell
npm --prefix frontend-enterprise test
npm --prefix frontend-enterprise run test:typecheck
```

The TikTok replay is deterministic and must report `external_writes=false`:

```powershell
backend\.venv\Scripts\python.exe tests\integration\run_tiktok_mock_sop_replay.py
```

The DesignKit acceptance runner needs a real downloaded image and writes acceptance
records to the configured PostgreSQL database and object storage. Run it only against
the intended test tenant:

```powershell
backend\.venv\Scripts\python.exe tests\integration\run_designkit_e2e.py <image-file>
```

Packaging checks take a prepared runtime or package artifact. The macOS application
and Linux Docker checks require their target platforms:

```powershell
backend\.venv\Scripts\python.exe tests\packaging\smoke_sandbox_bundle.py <sandbox-runtime>
backend\.venv\Scripts\python.exe tests\packaging\smoke_sandbox_runtime.py <sandbox-runtime>
bash tests/packaging/smoke_macos_app.sh [StaffDeck.app]
docker run --rm --platform linux/amd64 -v "${PWD}:/work" ubuntu:22.04 bash /work/tests/packaging/docker_test_linux.sh
```

Check the repository boundary after staging changes so the command reads the updated
Git index:

```powershell
backend\.venv\Scripts\python.exe tests\check_test_layout.py
```

Place executable repository tests under the matching `tests/` category. Python test
modules use `test_*.py` or `*_test.py`; JavaScript and TypeScript tests use `.test.*`
or `.spec.*`. Support setup such as `frontend-enterprise/src/test/setup.ts` remains
with production tooling. Skill evaluation data at `skills/*/evals/cases.json` remains
with each published skill package because it is runtime data, not an executable test.
