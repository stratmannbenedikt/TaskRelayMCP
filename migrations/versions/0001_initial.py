"""Initial 0.4 schema.

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("tasks_enabled", sa.Boolean(), nullable=False),
        sa.Column("notes_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_key", "projects", ["key"], unique=True)
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_tags_project_name"),
        sa.UniqueConstraint("project_id", "id", name="uq_tags_project_id_id"),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"])
    op.create_index("ix_tags_project_name", "tags", ["project_id", "name"])
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_browser_sessions_user_id", "browser_sessions", ["user_id"])
    op.create_index("ix_browser_sessions_token_hash", "browser_sessions", ["token_hash"], unique=True)
    op.create_table(
        "mcp_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_mcp_keys_user_name"),
    )
    op.create_index("ix_mcp_keys_user_id", "mcp_keys", ["user_id"])
    op.create_index("ix_mcp_keys_secret_hash", "mcp_keys", ["secret_hash"], unique=True)
    op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("target_project_id", sa.Integer(), nullable=False),
        sa.Column("origin_project_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("assigned_agent", sa.String(length=120), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["origin_project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["target_project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_project_id", "id", name="uq_tasks_target_project_id_id"),
    )
    op.create_table(
        "note_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "parent_id"], ["note_folders.project_id", "note_folders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_note_folders_project_id_id"),
    )
    op.create_index("ix_note_folders_project_id", "note_folders", ["project_id"])
    op.create_index("ix_note_folders_parent_id", "note_folders", ["parent_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_note_folders_project_parent_name "
        "ON note_folders (project_id, COALESCE(parent_id, -1), name)"
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "folder_id"], ["note_folders.project_id", "note_folders.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notes_project_id", "notes", ["project_id"])
    op.create_index("ix_notes_folder_id", "notes", ["folder_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_notes_project_folder_title ON notes (project_id, COALESCE(folder_id, -1), title)"
    )
    op.create_table(
        "note_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["edited_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id", "version", name="uq_note_revisions_note_version"),
    )
    op.create_index("ix_note_revisions_note_id", "note_revisions", ["note_id"])
    op.create_table(
        "note_links",
        sa.Column("source_note_id", sa.Integer(), nullable=False),
        sa.Column("target_note_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["source_note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_note_id", "target_note_id"),
    )
    op.create_table(
        "task_tags",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id", "tag_id"], ["tags.project_id", "tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "task_id"], ["tasks.target_project_id", "tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )
    op.create_table(
        "tag_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("proposed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("mcp_key_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_task_ids", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_tag_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["mcp_key_id"], ["mcp_keys.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_proposals_project_id", "tag_proposals", ["project_id"])
    op.create_index("ix_tag_proposals_project_status", "tag_proposals", ["project_id", "status"])
    op.create_index(
        "uq_tag_proposals_pending_project_name",
        "tag_proposals",
        ["project_id", "name"],
        unique=True,
        sqlite_where=sa.text("status = 'PENDING'"),
    )
    op.create_table(
        "tag_proposal_tasks",
        sa.Column("proposal_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["tag_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("proposal_id", "task_id"),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comments_task_id", "comments", ["task_id"])
    op.create_table(
        "task_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=8), nullable=True),
        sa.Column("mcp_key_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["mcp_key_id"], ["mcp_keys.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_project_id", "notifications", ["project_id"])
    op.create_index("ix_notifications_task_id", "notifications", ["task_id"])
    op.create_table(
        "notification_reads",
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("notification_id", "user_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(length=8), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("object_type", sa.String(length=40), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("notification_reads")
    op.drop_index("ix_notifications_task_id", table_name="notifications")
    op.drop_index("ix_notifications_project_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_comments_task_id", table_name="comments")
    op.drop_table("comments")
    op.drop_table("tag_proposal_tasks")
    op.drop_index("uq_tag_proposals_pending_project_name", table_name="tag_proposals")
    op.drop_index("ix_tag_proposals_project_status", table_name="tag_proposals")
    op.drop_index("ix_tag_proposals_project_id", table_name="tag_proposals")
    op.drop_table("tag_proposals")
    op.drop_table("task_tags")
    op.drop_table("note_links")
    op.drop_index("ix_note_revisions_note_id", table_name="note_revisions")
    op.drop_table("note_revisions")
    op.drop_index("uq_notes_project_folder_title", table_name="notes")
    op.drop_index("ix_notes_folder_id", table_name="notes")
    op.drop_index("ix_notes_project_id", table_name="notes")
    op.drop_table("notes")
    op.drop_index("uq_note_folders_project_parent_name", table_name="note_folders")
    op.drop_index("ix_note_folders_parent_id", table_name="note_folders")
    op.drop_index("ix_note_folders_project_id", table_name="note_folders")
    op.drop_table("note_folders")
    op.drop_table("tasks")
    op.drop_table("project_memberships")
    op.drop_index("ix_mcp_keys_secret_hash", table_name="mcp_keys")
    op.drop_index("ix_mcp_keys_user_id", table_name="mcp_keys")
    op.drop_table("mcp_keys")
    op.drop_index("ix_browser_sessions_token_hash", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_user_id", table_name="browser_sessions")
    op.drop_table("browser_sessions")
    op.drop_index("ix_tags_project_name", table_name="tags")
    op.drop_index("ix_tags_project_id", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_projects_key", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
