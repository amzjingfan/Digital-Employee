# Migration evidence tools

These scripts preserve the one-time verification for the 2026-09-11 repository
migration. They are audit utilities, not product tests. Executable test suites
remain under the categorized root `src/tests/` directory.

Run commands from the repository root:

```powershell
src\backend\.venv\Scripts\python.exe src\scripts\migration\verify_source_map.py
src\backend\.venv\Scripts\python.exe src\scripts\migration\security_scan.py --worktree
src\backend\.venv\Scripts\python.exe src\scripts\migration\summarize_junit.py .dev\task8-new-20260911-verify\pytest-new.xml
src\backend\.venv\Scripts\python.exe src\scripts\migration\compare_pytest_summaries.py .dev\new-summary.json .dev\old-summary.json
```

The source-map verifier pins the pre-layout snapshot and the final functional
source commit. It checks the complete intervening commit chain, every indexed
path and blob, case-insensitive destination collisions, and the three reviewed
Unix executable-bit changes. It writes the tracked
`docs/migration/final-source-map.tsv`; its summary and addition list are ignored
under `.dev/`. A later feature commit does not change this historical map.

The security scanner compares the immutable handover tag with the current
working tree or `HEAD`. It prints only category counts and stores candidate
locations in ignored `.dev/` output. A zero new-candidate count is a migration
delta check, not a credential audit of the original handover contents. The
scanner exits nonzero if a new candidate or tracked runtime artifact appears.

To repeat the legacy backend suite, supply the old checkout explicitly:

```powershell
& src\scripts\migration\run_legacy_backend_suite.ps1 -OldRepository 'E:\develop\数字员工\joukir-enterprise'
```

The runner uses an isolated SQLite database, data directory, dotenv path and
pytest temporary directory under ignored `.dev/`, and compares the old Git
status before and after. It does not print configuration values. This command
requires the old checkout and its existing virtual environment; it is not part
of normal development or CI.

`verify_live.py` performs the safe, no-credential HTTP/OIDC check. The
`cutover_web.ps1` script records the one-time local port-5173 cutover and has
strict old/new process identity checks and a rollback path. It should only be
run when the old checkout still owns that port; it refuses a different owner.

JUnit summary and comparison tools distinguish assertion failures, errors and
skips by normalized test node, and require all five result counts and outcome
sets to match. The dated [verification record](../../docs/migration/VERIFICATION_20260911.md)
contains the actual run paths, results, environment differences and limits.
