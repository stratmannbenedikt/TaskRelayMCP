# 0008 — Make tags project-scoped, colored, and explicitly created

## Status

Accepted before the first supported deployment; the single database baseline may change and temporary development data may be reset.

## Decision

- Tags are project-scoped definitions with a normalized unique name, required color, description, creator, timestamps, archive state, and usage count.
- Tasks reference tag identities. Unknown tag names never create definitions implicitly.
- Project members may create tags in the web UI, assign existing tags, approve or reject agent proposals, and edit tag color/description.
- Project owners additionally rename and archive tags.
- Archived tags remain on historical tasks but cannot be newly assigned. Tags in use are not hard-deleted.
- Agents can list available project tags and assign existing tags by name.
- `create_project_tag` prefers MCP elicitation. Accepted elicitation creates the tag; decline/cancel creates nothing and must not fall back.
- If elicitation is unsupported, the tool returns a structured `ELICITATION_UNSUPPORTED` result naming `propose_project_tag` as the fallback.
- `propose_project_tag` is asynchronous and returns immediately with `PENDING`. It may reference existing same-project tasks for retroactive assignment.
- A browser-authenticated project member may edit, approve, or reject a pending proposal. Approval atomically creates or resolves the tag and applies it to the approved referenced tasks. MCP credentials cannot approve proposals.
- Agent proposals expire after seven days. Duplicate pending proposals in a project resolve to the existing proposal rather than creating approval noise.
- Tag filtering is categorical and URL-backed. Task presentation uses colored chips and a prominent project-color marker.

## Non-goals

No implicit tag creation, free-text tag filtering, cross-project tag identity, agent approval rights, automatic fallback after user decline/cancel, tag hierarchy, or synonym ontology.
