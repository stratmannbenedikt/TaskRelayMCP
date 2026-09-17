# 0009 — Use read-first task and note interaction

## Status

Accepted.

## Decision

- Existing tasks and notes open in read-only mode. Editing is an explicit temporary state.
- Task result presentation is shared between global and project pages. Rows show a one-line description preview with an explicit More/Less expansion, priority indicator, assignment, colored tags, update time, and project identity only on the global page.
- The left row border consistently represents priority; project identity uses its own colored badge.
- TODO is omitted from normal TODO rows. DONE remains visibly distinguished when mixed or completed results are shown.
- Project and global task filters share behavior; the project page omits only project selection.
- Project task creation uses a complete form for title, description, priority, assignee, and existing tags. Tag search filters definitions and explicitly offers creation only when no exact tag exists.
- Existing task detail opens read-only. Edit, Complete, and Delete are separate actions. Save returns to read-only; dirty cancellation requires confirmation; DONE tasks remain immutable.
- Existing notes open as rendered Markdown. Edit switches to the existing editor; Save returns to rendered read-only mode; archived and inspection views remain read-only.
- New notes begin as unsaved local drafts. Cancel creates nothing; first Save creates the note and switches to its stable read-only route.
- Browser refreshes and direct links always begin in read-only mode.
- Project Notes uses the same two-column tree-and-content presentation as global Notes. The project root and each folder expose scoped note/folder creation; a note draft opened from a folder starts with that folder selected.
- Writable project Notes trees support dragging notes and folders onto folders or the project root. Existing folder management and note editing controls remain the keyboard and touch fallback, with compact folder actions aligned beside the folder name.
- Project and global Notes use explicit accessible tree disclosures, current-note highlighting, and search that reveals matching descendants. Drag handles are pointer-only affordances; folder management and the note editor remain the keyboard/touch move paths.
- Notes trees distinguish folders and documents with monochrome markers, indentation guides, and stronger folder typography. Deep trees scroll within the navigation pane rather than widening the page or clipping controls.
- On mobile, applied Task filters start behind a disclosure and selected Note content precedes the browse tree. Read-mode Note actions and metadata form the document header; `Preview` remains editor-only.
- The global Notes `Edit note` action passes a one-shot navigation intent into the permitted project editor. Ordinary links, direct URLs, refreshes, failed loads, and read-only contexts still open in read mode.
- Note editing uses a focused desktop split workspace with Markdown source on the left and live preview on the right, stacking on narrow screens. A native insertion toolbar exposes commonly used syntax without changing the supported Markdown language.
