from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taskrelaymcp.models import Priority

USERNAME_PATTERN = r"^[a-z][a-z0-9._-]{2,63}$"


class Login(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=1024)


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    display_name: str = Field(min_length=1, max_length=120)
    temporary_password: str = Field(min_length=12, max_length=1024)
    is_admin: bool = False

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class PasswordReset(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=1024)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str
    active: bool
    is_admin: bool
    must_change_password: bool


class MCPKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    color: str | None = None
    tasks_enabled: bool = True
    notes_enabled: bool = False


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = None
    archived: bool | None = None
    tasks_enabled: bool | None = None
    notes_enabled: bool | None = None


class ProjectOut(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived: bool
    created_at: datetime
    role: str | None = None


class ProjectTaskPreviewOut(BaseModel):
    id: int
    title: str
    priority: str
    assignee: str | None
    updated_at: datetime


class ProjectRecentNoteOut(BaseModel):
    id: int
    title: str
    updated_at: datetime
    updater: str | None
    folder_path: str | None


class ProjectActivityOut(BaseModel):
    action: str
    object_type: str
    object_id: int
    object_title: str
    actor: str | None
    created_at: datetime


class ProjectSummaryOut(ProjectOut):
    todo_count: int
    done_count: int
    last_activity_at: datetime
    note_count: int
    todo_preview: list[ProjectTaskPreviewOut]
    recent_note: ProjectRecentNoteOut | None
    latest_activity: ProjectActivityOut | None


class MembershipChange(BaseModel):
    username: str


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    target_project: str
    origin_project: str | None = None
    priority: Priority = Priority.NORMAL
    tag_ids: list[int] = Field(default_factory=list)
    assigned_user: str | None = None


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    priority: Priority | None = None
    target_project: str | None = None
    tag_ids: list[int] | None = None
    assigned_user: str | None = None


class CompleteTask(BaseModel):
    summary: str = Field(min_length=1)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    target_project: str
    origin_project: str
    creator: str
    assignee: str | None
    completer: str | None
    tags: list[TagOut]
    comments: list[dict]
    events: list[dict]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


TAG_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class TagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=TAG_NAME_PATTERN, max_length=64)
    color: str = Field(pattern=COLOR_PATTERN)
    description: str = Field(default="", max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower() if value is not None and value is not ... else value

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value: str) -> str:
        return value.strip() if value is not None and value is not ... else value


class TagPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, pattern=TAG_NAME_PATTERN, max_length=64)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TagOut(BaseModel):
    id: int
    project: str
    name: str
    color: str
    description: str
    archived_at: datetime | None
    usage_count: int
    creator: str | None
    created_at: datetime
    updated_at: datetime


class TagProposalApproval(TagPatch):
    apply_requested_tasks: bool = True


class TagProposalOut(BaseModel):
    id: int
    project: str
    name: str
    color: str
    description: str
    status: str
    proposed_by: str | None
    mcp_key: str | None
    created_at: datetime
    expires_at: datetime
    decided_by: str | None
    decided_at: datetime | None
    resolved_tag_id: int | None
    task_ids: list[int]


class NoteFolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=240)
    parent_id: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class NoteFolderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=240)
    parent_id: int | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    markdown: str = Field(max_length=1024 * 1024)
    folder_id: int | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return value.strip()


class NotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    markdown: str | None = Field(default=None, max_length=1024 * 1024)
    folder_id: int | None = None
    archived: bool | None = None
    expected_version: int = Field(ge=1)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None
