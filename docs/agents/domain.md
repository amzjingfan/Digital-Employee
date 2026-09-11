# Documentation domain policy

Use one canonical document for each kind of project context:

- Stable architecture and working agreements belong in `docs/PROJECT_MEMORY.md`.
- Mutable branch state, verified results, blockers, and next actions belong in `docs/SESSION_HANDOFF.md`.
- Chronological implementation evidence is appended to `docs/DEVELOPMENT_LOG.md`.
- Lasting architecture or workflow decisions belong in `docs/adr/`.
- Product requirements belong in `docs/prd/`; operational procedures belong in `docs/runbooks/`.

Update the existing canonical document instead of creating parallel summaries. Keep dated handover and development-branch documents as historical evidence and label them as snapshots when linking to them. Never store credentials, connection strings, cookies, private keys, personal data, or raw external authorization payloads in documentation.
