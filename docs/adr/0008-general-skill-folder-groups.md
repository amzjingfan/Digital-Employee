# ADR 0008: Keep folder-imported general skills together in the open plaza

Date: 2026-10-12

Status: Accepted

## Context

A selected folder can contain several `SKILL.md` packages. Batch import stores each package as an independent general skill, but previously discarded their common source folder. The open plaza could only render independent cards, so one imported collection was scattered among unrelated skills. Older imports have no reliable source-folder record.

## Decision

When a folder batch has a folder display name, the API assigns one server-generated group ID and that name to every selected skill's `metadata_json`, including a batch of one. Groups are scoped by the existing tenant and gallery access rules. The ID, rather than the display name, determines membership; two imports with the same folder name stay separate. The API rejects a grouped batch that mixes tenants or agent scopes.

The open plaza groups published skills into an expandable folder card on its overview and full Skill list, even when only one member is visible. Each member remains an independent skill with its original slug, permissions, use and removal behavior. Counts remain skill counts. Search matches member content and folder name.

An administrator may select one or more existing published gallery skills and assign a folder name. This operation validates every selected ID in the same tenant and gallery before writing any group metadata. An administrator may rename an existing folder: the API checks its gallery members, changes their shared display name, and preserves the group ID and membership. It does not infer historical membership from similar names or timestamps. Ordinary edits preserve group metadata; a later grouped batch import moves matching skills into that batch's new group. Untrusted Skill frontmatter cannot set group IDs.

## Alternatives and consequences

Grouping by folder name alone could merge unrelated imports. Merging all child Skills into one database row would change their execution and permission identity. Inferring historical folders from slugs would misclassify content. The chosen metadata approach needs no schema migration and keeps original Skill records intact, but older imports need an administrator to group them explicitly. Removing the metadata keys from affected skills restores the former card layout without deleting Skill content.

## Evidence

Focused backend import, edit, authorization and private-skill tests plus frontend plaza grouping and admin-selection tests are in `src/tests/backend/test_general_skills.py` and `src/tests/frontend/pages/`.
