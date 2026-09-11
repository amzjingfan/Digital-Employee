## Problem and resulting behavior

Describe the concrete trigger, current behavior, and resulting behavior after this change.

## Implementation

Describe the implementation and any compatibility choices a reviewer should assess.

## Risk and rollback

- Risk level and likely failure modes:
- Rollback or recovery steps:

## Validation

List the exact commands run and their results. Include browser evidence for visible behavior.

## Access and data impact

- Routes or entry points affected:
- User roles and tenant scopes checked:
- Schema or migration impact, including RLS and rollback:
- External integrations or authorization flows affected:

## Documentation and decisions

- Documentation updated:
- ADR added or updated, or reason none is needed:

## Review checklist

- [ ] The change is scoped to one problem and has focused regression coverage.
- [ ] Root test-layout, relevant backend/frontend CI gates, and affected browser routes pass.
- [ ] Permission checks cover every affected role and tenant boundary.
- [ ] Schema changes include forward migration, safe rollback, ownership, and RLS verification.
- [ ] External writes, release gates, retries, audit evidence, and failure recovery were assessed.
- [ ] User-facing behavior, runbooks, project memory, session handoff, and ADRs are current where applicable.
- [ ] No credentials, connection strings, cookies, private keys, or raw external authorization payloads appear in the PR, commits, fixtures, logs, or screenshots.
