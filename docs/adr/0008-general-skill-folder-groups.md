# ADR 0008: Keep folder-imported general skills together in the open plaza

Date: 2026-10-12

Status: Accepted

## Context

A selected folder can contain several `SKILL.md` packages. Batch import stores each package as an independent general skill, but previously discarded their common source folder. The open plaza could only render independent cards, so one imported collection was scattered among unrelated skills. Older imports have no reliable source-folder record.

## Decision

When a folder batch contains multiple selected skills, the API assigns one server-generated group ID and the submitted folder display name to each imported skill's `metadata_json`. Groups are scoped by the existing tenant and gallery access rules. The ID, rather than the display name, determines membership; two imports with the same folder name stay separate. The API rejects a grouped batch that mixes tenants or agent scopes. A single imported skill remains an ordinary card.

The open plaza groups published skills into an expandable folder card on its overview and full Skill list. Each member remains an independent skill with its original slug, permissions, use and removal behavior. Counts remain skill counts. Search matches member content and folder name. If only one visible member remains, it appears as an ordinary card.

An administrator may select existing published gallery skills and assign a folder name. This operation validates every selected ID in the same tenant and gallery before writing any group metadata. It does not infer historical membership from similar names or timestamps. Import and edit paths preserve group metadata; untrusted Skill frontmatter cannot set group IDs.

## Alternatives and consequences

Grouping by folder name alone could merge unrelated imports. Merging all child Skills into one database row would change their execution and permission identity. Inferring historical folders from slugs would misclassify content. The chosen metadata approach needs no schema migration and keeps original Skill records intact, but older imports need an administrator to group them explicitly. Removing the metadata keys from affected skills restores the former card layout without deleting Skill content.

## Evidence

Focused backend import, edit, authorization and private-skill tests plus frontend plaza grouping and admin-selection tests are in `src/tests/backend/test_general_skills.py` and `src/tests/frontend/pages/`.
