from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taskrelaymcp.models import Priority, Status


class ProjectCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    color: str | None = None


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = None
    archived: bool | None = None


class ProjectOut(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived: bool
    created_at: datetime


class ProjectSummaryOut(ProjectOut):
    todo_count: int
    done_count: int
    last_activity_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    target_project: str
    origin_project: str | None = None
    priority: Priority = Priority.NORMAL
    tags: list[str] = Field(default_factory=list)
    assigned_agent: str | None = None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    target_project: str | None = None
    tags: list[str] | None = None
    assigned_agent: str | None = None

    @field_validator("status")
    @classmethod
    def require_semantic_completion(cls, value: Status | None) -> Status | None:
        if value == Status.DONE:
            raise ValueError("Use complete_task so completion has a summary and notification")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return sorted({value.strip().lower() for value in values if value.strip()})


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


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
    created_by: str
    assigned_agent: str | None
    tags: list[str]
    comments: list[dict]
    events: list[dict]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    task_id: int
    type: str
    message: str
    created_at: datetime
    read_at: datetime | None
