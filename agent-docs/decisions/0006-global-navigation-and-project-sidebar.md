# 0006 — Separate global navigation from project navigation

## Status

Accepted for the Angular client.

## Decision

- The project dashboard is named Home and uses `/home`; `/projects` remains a compatibility redirect.
- Global primary pages are Home, Tasks, and Notes.
- Global Tasks combines tasks from every accessible project and supports URL-backed filtering and sorting.
- Global Notes presents notes-enabled projects as tree roots, their nested folders and notes beneath them, and a read-only Markdown preview with an explicit link to the project editor.
- The sidebar visually separates primary navigation, a scrollable My Projects region, and bottom-pinned Account/Admin/Logout utilities.
- Each project is a compact container bordered by its project color. Its title uses an accessible derivative of that color and its owner-only settings cog is right-aligned in the title row.
- Every project container always shows stable Tasks and Notes capability positions. Disabled capabilities remain visible but non-interactive and clearly muted.
- Primary navigation, project capabilities, icon controls, and utility navigation use distinct styles rather than a shared button-like anchor treatment.
- Existing project-specific Task and Note routes remain the editing surfaces. No database migration or new aggregate API is required initially.

## Deferred

Server-side global Notes aggregation, pagination beyond current bounded APIs, visual snapshot tests, and persisted cross-device filter preferences.
