# 0004 — Add project notes, folders, links, and dashboard controls

## Status

Accepted for release 0.4.0.

## Decision

- Projects independently enable Tasks and Notes; at least one capability is required. Existing projects migrate as Tasks-only.
- Capabilities may be enabled later. A capability with existing content cannot be disabled.
- Notes belong to a project and optionally to a nested folder. The project root is implicit.
- Folders have unique sibling names, cannot contain themselves transitively, and cannot be deleted while non-empty.
- Notes have stable numeric identities rendered as `N-<id>`, one folder location, title, Markdown body, archive state, author/updater attribution, timestamps, and an integer version.
- Note updates use optimistic concurrency and preserve revisions. Explicit saves are used instead of autosave.
- Wiki links use `[[N-42]]` or `[[N-42|Label]]`. Links are stable across renames and moves, remain within one project, produce backlinks, and may visibly remain unresolved rather than blocking a save.
- Markdown preview must not execute embedded HTML or unsafe URLs.
- Project membership and inspection-mode rules apply equally to notes and folders.
- MCP exposes explicit note and folder read/write/move/archive operations. It does not create folders implicitly.
- The authenticated Angular application uses a persistent responsive sidebar. Project content, project settings, Account, and Admin remain directly navigable.
- Project creation is initiated from a top-level button and modal, using a native color input.
- Project settings and member management are separate from normal project content routes.
- Project cards may show description, bounded TODO previews, latest activity, and a recent note according to non-sensitive browser-local preferences. The default task preview is three TODOs ordered by priority then recent update.

## Deferred

Explicit task–note relationships, cross-project note links, attachments, public links, offline support, and simultaneous collaborative editing.
