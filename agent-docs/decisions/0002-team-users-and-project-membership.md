# 0002 — Add team users and private project membership

## Status

Accepted; supersedes the user and ACL non-goals in decision 0001.

## Decision

- One deployment remains one team/workspace; organizations and public signup remain out of scope.
- A bootstrap administrator creates, deactivates, and resets local user accounts. Users are deactivated, not deleted.
- Browser users authenticate with username/password and an HTTP-only session cookie.
- Users may create named, revocable MCP keys. Keys are shown once, stored hashed, and act as their owning user.
- A project has one `OWNER` and zero or more `MEMBER`s. Its creator is its owner. Owners manage membership; both roles may work with tasks.
- Normal reads and all writes require project membership. Unauthorized resources appear not found.
- Administrators may explicitly enable a read-only inspection mode in the browser to see all projects. Inspection mode grants no write access and overridden reads are auditable.
- Cross-project task creation requires the acting user to belong to both origin and target projects.
- Tasks record the creating user, one optional assigned user, and the completing user. Activity records whether an action came from the browser or a named MCP key.
- Notification consumption is tracked per user rather than once for the whole project.
- Existing projects become owned by the bootstrap administrator during upgrade; anonymous workspace bearer tokens are retired.

## Non-goals

No organizations, public registration, email delivery or password recovery, pending invitations, viewer role, multiple assignees, per-task ACLs, time allocation, estimates, calendars, or workflow expansion.
