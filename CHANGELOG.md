# Changelog

All notable changes to TaskRelayMCP are documented in this file.

## [0.5.0] - 2026-09-17

### Added

- Local users and sessions, project owner/member access controls, personal MCP keys, attribution, inspection mode, and per-user notifications.
- The Angular client-side application with Home, global Tasks and Notes, responsive project navigation, and actionable project summaries.
- Project Notes with nested folders, safe Markdown, wiki links, backlinks, revisions, and MCP note/folder operations.
- Project-scoped tags with explicit management, agent elicitation/proposals, and browser approval.
- Read-first task and note detail flows with explicit editing and dirty-navigation protection.
- Project and global Notes trees with search, nested-hierarchy guides, scoped creation, drag-and-drop moves, and keyboard/touch fallbacks.
- A focused split Markdown editor and live preview with an insertion toolbar and styled blockquotes, code, and tables.

### Changed

- Shared responsive task filtering and tables, richer task details, responsive navigation/mobile content ordering, and accessibility improvements.

### Fixed

- Duplicate note tree entries, stale deep-task loads, tag clearing/form submission, folder controls, and global Edit-note intent.

The database remains on the consolidated `0001_initial` baseline. Upgrading from the last tagged release, v0.2.0, requires the development database reset documented in the README; back up required data first.

[0.5.0]: https://github.com/stratmannbenedikt/TaskRelayMCP/compare/v0.2.0...v0.5.0
