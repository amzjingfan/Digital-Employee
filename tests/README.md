# Repository test suites

All executable repository tests live under this root and are grouped by purpose.

| Category | Directory | Current status |
| --- | --- | --- |
| Backend | `tests/backend/` | Active; contains the Python pytest suite. |
| Frontend | `tests/frontend/` | Reserved for the planned Vitest migration. |
| Integration | `tests/integration/` | Reserved for cross-module runners. |
| Packaging | `tests/packaging/` | Reserved for platform smoke tests. |

From the repository root, run the backend suite with:

```powershell
backend\.venv\Scripts\python.exe -m pytest -c pytest.ini tests\backend
```

Place new Python backend tests under `tests/backend/` and name modules `test_*.py`.
Skill evaluation data under `skills/*/evals/` remains with its published skill package;
those files are runtime assets rather than repository test executables.
