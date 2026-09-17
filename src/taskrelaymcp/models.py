from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskrelaymcp.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Status(StrEnum):
    TODO = "TODO"
    DONE = "DONE"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Role(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class TagProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


tag_proposal_tasks = Table(
    "tag_proposal_tasks",
    Base.metadata,
    Column("proposal_id", Integer, ForeignKey("tag_proposals.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class MCPKey(Base):
    __tablename__ = "mcp_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_mcp_keys_user_name"),)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[str | None] = mapped_column(String(32))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    tasks_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    memberships: Mapped[list[ProjectMembership]] = relationship(cascade="all, delete-orphan")


class NoteFolder(Base):
    __tablename__ = "note_folders"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(240))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project: Mapped[Project] = relationship()
    parent: Mapped[NoteFolder | None] = relationship(remote_side=[project_id, id], overlaps="project")
    creator: Mapped[User] = relationship()
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_note_folders_project_id_id"),
        ForeignKeyConstraint(["project_id", "parent_id"], ["note_folders.project_id", "note_folders.id"]),
        Index(
            "uq_note_folders_project_parent_name",
            "project_id",
            func.coalesce(parent_id, -1),
            "name",
            unique=True,
        ),
    )


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(240))
    markdown: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project: Mapped[Project] = relationship()
    folder: Mapped[NoteFolder | None] = relationship(foreign_keys=[project_id, folder_id], overlaps="project")
    creator: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    updater: Mapped[User] = relationship(foreign_keys=[updated_by_user_id])
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "folder_id"], ["note_folders.project_id", "note_folders.id"]),
        Index(
            "uq_notes_project_folder_title",
            "project_id",
            func.coalesce(folder_id, -1),
            "title",
            unique=True,
        ),
    )


class NoteRevision(Base):
    __tablename__ = "note_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    markdown: Mapped[str] = mapped_column(Text)
    folder_id: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    editor: Mapped[User] = relationship()
    __table_args__ = (UniqueConstraint("note_id", "version", name="uq_note_revisions_note_version"),)


class NoteLink(Base):
    __tablename__ = "note_links"
    source_note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    target_note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    user: Mapped[User] = relationship()


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(7))
    description: Mapped[str] = mapped_column(String(500), default="")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project: Mapped[Project] = relationship()
    creator: Mapped[User] = relationship()
    task_links: Mapped[list[TaskTag]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
        primaryjoin="and_(Tag.id == foreign(TaskTag.tag_id), Tag.project_id == foreign(TaskTag.project_id))",
        overlaps="task,tag_links",
    )
    tasks = association_proxy(
        "task_links", "task", creator=lambda task: TaskTag(project_id=task.target_project_id, task=task)
    )
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_tags_project_name"),
        UniqueConstraint("project_id", "id", name="uq_tags_project_id_id"),
        Index("ix_tags_project_name", "project_id", "name"),
    )


class TagProposal(Base):
    __tablename__ = "tag_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    proposed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mcp_key_id: Mapped[int] = mapped_column(ForeignKey("mcp_keys.id"))
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(7))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default=TagProposalStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_task_ids: Mapped[str] = mapped_column(Text, default="[]")
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_tag_id: Mapped[int | None] = mapped_column(ForeignKey("tags.id"))
    project: Mapped[Project] = relationship()
    proposer: Mapped[User] = relationship(foreign_keys=[proposed_by_user_id])
    mcp_key: Mapped[MCPKey] = relationship()
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
    resolved_tag: Mapped[Tag | None] = relationship()
    tasks: Mapped[list[Task]] = relationship(secondary=tag_proposal_tasks)
    __table_args__ = (
        Index("ix_tag_proposals_project_status", "project_id", "status"),
        Index(
            "uq_tag_proposals_pending_project_name",
            "project_id",
            "name",
            unique=True,
            sqlite_where=status == TagProposalStatus.PENDING,
        ),
    )


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=Status.TODO)
    priority: Mapped[str] = mapped_column(String(32), default=Priority.NORMAL)
    target_project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    origin_project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    created_by: Mapped[str] = mapped_column(String(120))
    assigned_agent: Mapped[str | None] = mapped_column(String(120))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_project: Mapped[Project] = relationship(foreign_keys=[target_project_id])
    origin_project: Mapped[Project] = relationship(foreign_keys=[origin_project_id])
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    completer: Mapped[User | None] = relationship(foreign_keys=[completed_by_user_id])
    tag_links: Mapped[list[TaskTag]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        primaryjoin="and_(Task.id == foreign(TaskTag.task_id), Task.target_project_id == foreign(TaskTag.project_id))",
        overlaps="tag,task_links",
    )
    tags = association_proxy("tag_links", "tag", creator=lambda tag: TaskTag(project_id=tag.project_id, tag=tag))
    comments: Mapped[list[Comment]] = relationship(cascade="all, delete-orphan", order_by="Comment.created_at")
    events: Mapped[list[TaskEvent]] = relationship(cascade="all, delete-orphan", order_by="TaskEvent.created_at")
    __table_args__ = (UniqueConstraint("target_project_id", "id", name="uq_tasks_target_project_id_id"),)


class TaskTag(Base):
    __tablename__ = "task_tags"
    task_id: Mapped[int] = mapped_column(primary_key=True)
    tag_id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(nullable=False)
    task: Mapped[Task] = relationship(
        back_populates="tag_links",
        primaryjoin="and_(foreign(TaskTag.task_id) == Task.id, foreign(TaskTag.project_id) == Task.target_project_id)",
        overlaps="tag,task_links",
    )
    tag: Mapped[Tag] = relationship(
        back_populates="task_links",
        primaryjoin="and_(foreign(TaskTag.tag_id) == Tag.id, foreign(TaskTag.project_id) == Tag.project_id)",
        overlaps="task,tag_links",
    )
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "task_id"], ["tasks.target_project_id", "tasks.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["project_id", "tag_id"], ["tags.project_id", "tags.id"], ondelete="CASCADE"),
    )


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    author: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str | None] = mapped_column(String(8))
    mcp_key_id: Mapped[int | None] = mapped_column(ForeignKey("mcp_keys.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_user: Mapped[User | None] = relationship()
    mcp_key: Mapped[MCPKey | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationRead(Base):
    __tablename__ = "notification_reads"
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(8))
    action: Mapped[str] = mapped_column(String(40))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
