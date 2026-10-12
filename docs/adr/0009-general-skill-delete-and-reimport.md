# ADR 0009: Delete gallery Skill definitions and update on matching imports

Date: 2026-10-12

Status: Accepted

## Context

The open-plaza delete action previously marked only its resource binding as `deleted`. The `general_skills` row retained its tenant-wide unique slug, so importing the same Skill failed with a slug conflict even though users could no longer see it.

## Decision

An open-plaza administrator deleting a general Skill removes its definition and all of its resource bindings in one database transaction. A Skill still bound to an employee with a non-deleted binding cannot be deleted until that binding is removed. Removing a Skill from an individual employee continues to hide only that employee's binding.

Importing an existing gallery Skill with the same tenant and slug updates the existing row and republishes it, including revival of a previously deleted gallery binding. Its ID remains stable. A new slug creates a new row. The import response identifies `created` or `updated`; batch import remains atomic, rejects duplicate slugs within the batch, and assigns one folder group to all selected members. A gallery import does not overwrite a private employee Skill with the same slug.

## Consequences

Physical deletion releases the slug and cannot be undone through the application; a later import creates a new ID. Existing execution history remains historical evidence. A backup is required before removing old production records. There is no schema migration and no change to PostgreSQL RLS or role privileges.
