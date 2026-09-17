# 0007 — Make Home project cards actionable

## Status

Accepted.

## Decision

- Home project cards show project identity, an owner settings cog, equal-width Tasks and Notes capability controls, bounded actionable previews, and one human-readable latest activity.
- Enabled capability controls include useful counts and navigate to their project page. Disabled controls retain the same space but are noninteractive and clearly muted.
- Task previews are compact links showing priority, title, assignee, and update time. They deep-link to `/projects/:key/tasks/:taskId`, where the existing task drawer opens.
- The recent note is the non-archived note most recently updated. Its preview includes folder path when present, updater, and update time, and opens the global read-only note route.
- Latest activity identifies actor, action, object title, object type, and time; the referenced object is navigable.
- Relative time is shown for scanning and exact time remains available as a tooltip.
- Enabled empty capabilities use human wording rather than unexplained zero counts.
- Existing project/task/note data is sufficient; no database migration is required.
