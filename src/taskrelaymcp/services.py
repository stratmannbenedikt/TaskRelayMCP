from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from taskrelaymcp.config import Principal
from taskrelaymcp.models import (
    AuditEvent,
    Comment,
    Note,
    NoteFolder,
    NoteLink,
    NoteRevision,
    Notification,
    Project,
    ProjectMembership,
    Role,
    Status,
    Tag,
    TagProposal,
    TagProposalStatus,
    Task,
    TaskEvent,
    TaskTag,
    User,
)
from taskrelaymcp.schemas import (
    NoteCreate,
    NoteFolderCreate,
    NoteFolderPatch,
    NotePatch,
    ProjectCreate,
    ProjectPatch,
    TaskCreate,
    TaskPatch,
)


class NotFound(ValueError):
    pass


class Conflict(ValueError):
    pass


def membership(session: Session, project_id: int, user_id: int) -> ProjectMembership | None:
    return session.get(ProjectMembership, (project_id, user_id))


def project_by_key(session: Session, key: str, principal: Principal | None = None, inspection: bool = False) -> Project:
    project = session.scalar(select(Project).where(Project.key == key))
    if not project or (principal and not membership(session, project.id, principal.user_id) and not inspection):
        raise NotFound(f"Project '{key}' not found")
    if principal and inspection and not membership(session, project.id, principal.user_id):
        if not principal.is_admin or principal.channel != "WEB":
            raise NotFound(f"Project '{key}' not found")
        audit_inspection(session, principal, "project", str(project.id))
    return project


def require_member(session: Session, project: Project, principal: Principal) -> ProjectMembership:
    item = membership(session, project.id, principal.user_id)
    if not item:
        raise NotFound(f"Project '{project.key}' not found")
    return item


def require_owner(session: Session, project: Project, principal: Principal) -> ProjectMembership:
    item = require_member(session, project, principal)
    if item.role != Role.OWNER:
        raise NotFound(f"Project '{project.key}' not found")
    return item


def audit_inspection(session: Session, principal: Principal, object_type: str, object_id: str) -> None:
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            channel=principal.channel,
            action="INSPECTION_READ",
            object_type=object_type,
            object_id=object_id,
        )
    )


def create_project(session: Session, data: ProjectCreate, principal: Principal) -> Project:
    if not data.tasks_enabled and not data.notes_enabled:
        raise Conflict("A project must enable tasks or notes")
    project = Project(**data.model_dump())
    session.add(project)
    session.flush()
    session.add(ProjectMembership(project_id=project.id, user_id=principal.user_id, role=Role.OWNER))
    session.flush()
    return project


def patch_project(session: Session, project: Project, data: ProjectPatch, principal: Principal) -> Project:
    require_member(session, project, principal)
    changes = data.model_dump(exclude_unset=True)
    tasks_enabled = changes.get("tasks_enabled", project.tasks_enabled)
    notes_enabled = changes.get("notes_enabled", project.notes_enabled)
    if not tasks_enabled and not notes_enabled:
        raise Conflict("A project must enable tasks or notes")
    if (
        project.tasks_enabled
        and not tasks_enabled
        and session.scalar(select(Task.id).where(Task.target_project_id == project.id))
    ):
        raise Conflict("Cannot disable tasks while tasks exist")
    if (
        project.notes_enabled
        and not notes_enabled
        and session.scalar(select(Note.id).where(Note.project_id == project.id))
    ):
        raise Conflict("Cannot disable notes while notes exist")
    for key, value in changes.items():
        setattr(project, key, value)
    session.flush()
    return project


def list_members(session: Session, project: Project, principal: Principal) -> list[ProjectMembership]:
    require_member(session, project, principal)
    return list(
        session.scalars(
            select(ProjectMembership)
            .options(selectinload(ProjectMembership.user))
            .where(ProjectMembership.project_id == project.id)
            .order_by(ProjectMembership.role.desc(), ProjectMembership.user_id)
        )
    )


def add_member(session: Session, project: Project, username: str, principal: Principal) -> ProjectMembership:
    require_owner(session, project, principal)
    user = session.scalar(select(User).where(User.username == username.strip().lower(), User.active.is_(True)))
    if not user:
        raise NotFound("Active user not found")
    item = membership(session, project.id, user.id)
    if item:
        return item
    item = ProjectMembership(project_id=project.id, user_id=user.id, role=Role.MEMBER)
    session.add(item)
    session.flush()
    return item


def remove_member(session: Session, project: Project, username: str, principal: Principal) -> None:
    require_owner(session, project, principal)
    item = session.scalar(
        select(ProjectMembership)
        .join(User)
        .where(ProjectMembership.project_id == project.id, User.username == username.strip().lower())
    )
    if not item:
        raise NotFound("Membership not found")
    if item.role == Role.OWNER:
        raise Conflict("Transfer ownership before removing the owner")
    if session.scalar(
        select(Task.id).where(
            Task.target_project_id == project.id,
            Task.assigned_user_id == item.user_id,
            Task.status == Status.TODO,
        )
    ):
        raise Conflict("Reassign or complete this member's TODO tasks before removal")
    session.delete(item)


def transfer_owner(session: Session, project: Project, username: str, principal: Principal) -> None:
    old = require_owner(session, project, principal)
    user = session.scalar(select(User).where(User.username == username.strip().lower(), User.active.is_(True)))
    if not user:
        raise NotFound("Active user not found")
    new = membership(session, project.id, user.id)
    if not new:
        raise Conflict("New owner must already be a project member")
    old.role = Role.MEMBER
    new.role = Role.OWNER
    session.flush()


def _tag_objects(
    session: Session, project: Project, tag_ids: list[int], allowed_archived_ids: set[int] | None = None
) -> list[Tag]:
    ids = sorted(set(tag_ids))
    tags = list(session.scalars(select(Tag).where(Tag.id.in_(ids)))) if ids else []
    allowed_archived_ids = allowed_archived_ids or set()
    if len(tags) != len(ids) or any(
        tag.project_id != project.id or (tag.archived_at is not None and tag.id not in allowed_archived_ids)
        for tag in tags
    ):
        raise Conflict("Tags must be active tags in the target project")
    return tags


def create_tag(
    session: Session, project: Project, name: str, color: str, description: str, principal: Principal
) -> Tag:
    require_member(session, project, principal)
    tag = Tag(
        project_id=project.id, name=name, color=color, description=description, created_by_user_id=principal.user_id
    )
    try:
        with session.begin_nested():
            session.add(tag)
            session.flush()
    except IntegrityError as exc:
        raise Conflict("A tag with this name already exists in this project") from exc
    session.add(
        AuditEvent(
            actor_user_id=principal.user_id,
            channel=principal.channel,
            action="TAG_CREATED",
            object_type="TAG",
            object_id=str(tag.id),
        )
    )
    return tag


def patch_tag(session: Session, tag: Tag, changes: dict, principal: Principal) -> Tag:
    require_member(session, tag.project, principal)
    if "name" in changes:
        require_owner(session, tag.project, principal)
    for key, value in changes.items():
        setattr(tag, key, value)
    try:
        session.flush()
    except IntegrityError as exc:
        raise Conflict("A tag with this name already exists in this project") from exc
    return tag


def archive_tag(session: Session, tag: Tag, principal: Principal) -> Tag:
    require_owner(session, tag.project, principal)
    if tag.archived_at is None:
        tag.archived_at = datetime.now(UTC)
        session.flush()
    return tag


def list_tags(
    session: Session,
    principal: Principal,
    project_key: str | None = None,
    include_archived: bool = False,
    inspection: bool = False,
) -> list[Tag]:
    if inspection and (not principal.is_admin or principal.channel != "WEB"):
        raise NotFound("Not Found")
    statement = select(Tag).options(selectinload(Tag.project), selectinload(Tag.creator)).order_by(Tag.name, Tag.id)
    if project_key:
        project = project_by_key(session, project_key, principal, inspection)
        statement = statement.where(Tag.project_id == project.id)
    elif not inspection:
        statement = statement.where(
            Tag.project_id.in_(
                select(ProjectMembership.project_id).where(ProjectMembership.user_id == principal.user_id)
            )
        )
    if not include_archived:
        statement = statement.where(Tag.archived_at.is_(None))
    tags = list(session.scalars(statement))
    if inspection and any(not membership(session, tag.project_id, principal.user_id) for tag in tags):
        audit_inspection(session, principal, "tag-list", "*")
    return tags


def tag_dict(session: Session, tag: Tag) -> dict:
    return {
        "id": tag.id,
        "project": tag.project.key,
        "name": tag.name,
        "color": tag.color,
        "description": tag.description,
        "archived_at": tag.archived_at,
        "usage_count": session.scalar(
            select(func.count()).select_from(Task).join(TaskTag).where(TaskTag.tag_id == tag.id)
        ),
        "creator": tag.creator.display_name if tag.creator else None,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
    }


def _expire_proposal(proposal: TagProposal) -> None:
    expires_at = proposal.expires_at.replace(tzinfo=UTC) if proposal.expires_at.tzinfo is None else proposal.expires_at
    if proposal.status == TagProposalStatus.PENDING and expires_at <= datetime.now(UTC):
        proposal.status = TagProposalStatus.EXPIRED


def _proposal_tasks(session: Session, project: Project, task_ids: list[int], principal: Principal) -> list[Task]:
    ids = sorted(set(task_ids))
    tasks = list(session.scalars(select(Task).where(Task.id.in_(ids)))) if ids else []
    if len(tasks) != len(ids) or any(
        task.target_project_id != project.id or task.status != Status.TODO or not _task_access(session, task, principal)
        for task in tasks
    ):
        raise Conflict("Proposal tasks must be accessible TODO tasks targeting the home project")
    return tasks


def create_tag_proposal(
    session: Session,
    project: Project,
    name: str,
    color: str,
    description: str,
    task_ids: list[int],
    principal: Principal,
) -> TagProposal:
    require_member(session, project, principal)
    tasks = _proposal_tasks(session, project, task_ids, principal)

    def pending() -> TagProposal | None:
        return session.scalar(
            select(TagProposal)
            .options(selectinload(TagProposal.tasks))
            .where(
                TagProposal.project_id == project.id,
                TagProposal.name == name,
                TagProposal.status == TagProposalStatus.PENDING,
            )
        )

    existing = pending()
    if existing:
        _expire_proposal(existing)
        session.flush()
        if existing.status == TagProposalStatus.PENDING:
            existing.tasks.extend(task for task in tasks if task not in existing.tasks)
            existing.requested_task_ids = json.dumps(
                sorted({*json.loads(existing.requested_task_ids), *(task.id for task in tasks)})
            )
            session.flush()
            return existing
    proposal = TagProposal(
        project_id=project.id,
        proposed_by_user_id=principal.user_id,
        mcp_key_id=principal.mcp_key_id,
        name=name,
        color=color,
        description=description,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        requested_task_ids=json.dumps([task.id for task in tasks]),
        tasks=tasks,
    )
    try:
        with session.begin_nested():
            session.add(proposal)
            session.flush()
    except IntegrityError:
        proposal = pending()
        if not proposal:
            raise Conflict("Could not create tag proposal")
        proposal.tasks.extend(task for task in tasks if task not in proposal.tasks)
        proposal.requested_task_ids = json.dumps(
            sorted({*json.loads(proposal.requested_task_ids), *(task.id for task in tasks)})
        )
        session.flush()
    return proposal


def proposal_dict(proposal: TagProposal) -> dict:
    _expire_proposal(proposal)
    return {
        "id": proposal.id,
        "project": proposal.project.key,
        "name": proposal.name,
        "color": proposal.color,
        "description": proposal.description,
        "status": proposal.status,
        "proposed_by": proposal.proposer.display_name if proposal.proposer else None,
        "mcp_key": proposal.mcp_key.name if proposal.mcp_key else None,
        "created_at": proposal.created_at,
        "expires_at": proposal.expires_at,
        "decided_by": proposal.decider.display_name if proposal.decider else None,
        "decided_at": proposal.decided_at,
        "resolved_tag_id": proposal.resolved_tag_id,
        "task_ids": [task.id for task in proposal.tasks],
    }


def get_tag_proposal(session: Session, proposal_id: int, principal: Principal) -> TagProposal:
    proposal = session.scalar(
        select(TagProposal)
        .options(
            selectinload(TagProposal.project),
            selectinload(TagProposal.proposer),
            selectinload(TagProposal.mcp_key),
            selectinload(TagProposal.decider),
            selectinload(TagProposal.tasks),
        )
        .where(TagProposal.id == proposal_id)
    )
    if not proposal:
        raise NotFound("Tag proposal not found")
    require_member(session, proposal.project, principal)
    _expire_proposal(proposal)
    return proposal


def list_tag_proposals(
    session: Session,
    principal: Principal,
    project_key: str | None = None,
    status: str | None = None,
    inspection: bool = False,
) -> list[TagProposal]:
    statement = select(TagProposal).options(
        selectinload(TagProposal.project),
        selectinload(TagProposal.proposer),
        selectinload(TagProposal.mcp_key),
        selectinload(TagProposal.decider),
        selectinload(TagProposal.tasks),
    )
    if project_key:
        project = project_by_key(session, project_key, principal, inspection)
        statement = statement.where(TagProposal.project_id == project.id)
    elif not inspection:
        statement = statement.where(
            TagProposal.project_id.in_(
                select(ProjectMembership.project_id).where(ProjectMembership.user_id == principal.user_id)
            )
        )
    elif not principal.is_admin or principal.channel != "WEB":
        raise NotFound("Not Found")
    if status:
        statement = statement.where(TagProposal.status == status)
    proposals = list(session.scalars(statement.order_by(TagProposal.created_at.desc())))
    for proposal in proposals:
        _expire_proposal(proposal)
    return proposals


def decide_tag_proposal(
    session: Session, proposal: TagProposal, principal: Principal, approve: bool, changes: dict | None = None
) -> TagProposal:
    require_member(session, proposal.project, principal)
    _expire_proposal(proposal)
    if proposal.status != TagProposalStatus.PENDING:
        return proposal
    if not approve:
        proposal.status = TagProposalStatus.REJECTED
        proposal.decided_by_user_id = principal.user_id
        proposal.decided_at = datetime.now(UTC)
        session.flush()
        return proposal
    changes = changes or {}
    name = changes.get("name", proposal.name)
    color = changes.get("color", proposal.color)
    description = changes.get("description", proposal.description)
    task_ids = json.loads(proposal.requested_task_ids)
    tasks = list(session.scalars(select(Task).where(Task.id.in_(task_ids)))) if task_ids else []
    if len(tasks) != len(task_ids) or any(
        task.status != Status.TODO or task.target_project_id != proposal.project_id for task in tasks
    ):
        raise Conflict("Requested tasks must still be TODO tasks in the proposal project")
    tag = session.scalar(select(Tag).where(Tag.project_id == proposal.project_id, Tag.name == name))
    if tag and tag.archived_at is not None:
        raise Conflict("Archived tag names cannot be approved")
    now = datetime.now(UTC)
    try:
        with session.begin_nested():
            result = session.execute(
                update(TagProposal)
                .where(TagProposal.id == proposal.id, TagProposal.status == TagProposalStatus.PENDING)
                .values(
                    status=TagProposalStatus.APPROVED,
                    name=name,
                    color=color,
                    description=description,
                    decided_by_user_id=principal.user_id,
                    decided_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                session.expire(proposal)
                return proposal
            if not tag:
                tag = Tag(
                    project_id=proposal.project_id,
                    name=name,
                    color=color,
                    description=description,
                    created_by_user_id=principal.user_id,
                )
                session.add(tag)
                session.flush()
            if changes.get("apply_requested_tasks", True):
                for task in tasks:
                    if tag not in task.tags:
                        task.tags.append(tag)
            session.execute(
                update(TagProposal)
                .where(TagProposal.id == proposal.id)
                .values(resolved_tag_id=tag.id)
                .execution_options(synchronize_session=False)
            )
            session.flush()
    except IntegrityError as exc:
        raise Conflict("Could not resolve approved tag") from exc
    session.expire(proposal)
    return proposal


def task_query():
    return select(Task).options(
        selectinload(Task.target_project),
        selectinload(Task.origin_project),
        selectinload(Task.creator),
        selectinload(Task.assignee),
        selectinload(Task.completer),
        selectinload(Task.tag_links).selectinload(TaskTag.tag).selectinload(Tag.project),
        selectinload(Task.tag_links).selectinload(TaskTag.tag).selectinload(Tag.creator),
        selectinload(Task.comments),
        selectinload(Task.events).selectinload(TaskEvent.actor_user),
        selectinload(Task.events).selectinload(TaskEvent.mcp_key),
    )


def list_project_summaries(
    session: Session, principal: Principal, include_archived: bool = False, inspection: bool = False
) -> list[dict]:
    if inspection and (not principal.is_admin or principal.channel != "WEB"):
        raise NotFound("Not Found")
    last_activity = func.coalesce(func.max(Task.updated_at), Project.created_at)
    statement = (
        select(
            Project,
            ProjectMembership.role,
            func.coalesce(func.sum(case((Task.status == Status.TODO, 1), else_=0)), 0).label("todo_count"),
            func.coalesce(func.sum(case((Task.status == Status.DONE, 1), else_=0)), 0).label("done_count"),
            last_activity.label("last_activity_at"),
        )
        .outerjoin(
            ProjectMembership,
            (ProjectMembership.project_id == Project.id) & (ProjectMembership.user_id == principal.user_id),
        )
        .outerjoin(Task, Task.target_project_id == Project.id)
        .group_by(Project.id, ProjectMembership.role)
        .order_by(last_activity.desc())
    )
    if not inspection:
        statement = statement.where(ProjectMembership.user_id == principal.user_id)
    if not include_archived:
        statement = statement.where(Project.archived.is_(False))
    rows = list(session.execute(statement))
    if inspection and any(role is None for _, role, *_ in rows):
        audit_inspection(session, principal, "project-list", "*")
    summaries = []
    for project, role, todo_count, done_count, activity in rows:
        # ponytail: bounded per-project queries; batch if dashboard scale is measured to require it.
        previews = list(
            session.scalars(
                select(Task)
                .options(selectinload(Task.assignee))
                .where(Task.target_project_id == project.id, Task.status == Status.TODO)
                .order_by(
                    case(
                        (Task.priority == "URGENT", 4),
                        (Task.priority == "HIGH", 3),
                        (Task.priority == "NORMAL", 2),
                        else_=1,
                    ).desc(),
                    Task.updated_at.desc(),
                )
                .limit(10)
            )
        )
        notes = list(
            session.scalars(
                select(Note)
                .options(selectinload(Note.folder), selectinload(Note.updater))
                .where(Note.project_id == project.id)
                .order_by(Note.updated_at.desc())
            )
        )
        folders = {
            folder.id: folder
            for folder in session.scalars(select(NoteFolder).where(NoteFolder.project_id == project.id))
        }

        def folder_path(note: Note) -> str | None:
            names = []
            folder = note.folder
            while folder:
                names.append(folder.name)
                folder = folders.get(folder.parent_id)
            return " / ".join(reversed(names)) or None

        recent_note = next((note for note in notes if note.archived_at is None), None)
        latest_note = notes[0] if notes else None
        latest_task_row = session.execute(
            select(TaskEvent, Task)
            .join(Task)
            .options(selectinload(TaskEvent.actor_user))
            .where(Task.target_project_id == project.id)
            .order_by(TaskEvent.created_at.desc())
            .limit(1)
        ).first()
        latest_task, latest_task_object = latest_task_row or (None, None)
        assert latest_task is None or latest_task_object is not None
        candidates = (
            [
                (
                    latest_task.created_at,
                    {
                        "action": latest_task.event_type,
                        "object_type": "TASK",
                        "object_id": latest_task_object.id,
                        "object_title": latest_task_object.title,
                        "actor": latest_task.actor_user.display_name if latest_task.actor_user else latest_task.actor,
                        "created_at": latest_task.created_at,
                    },
                )
            ]
            if latest_task
            else []
        )
        if latest_note:
            candidates.append(
                (
                    latest_note.updated_at,
                    {
                        "action": "NOTE_CREATED" if latest_note.version == 1 else "NOTE_UPDATED",
                        "object_type": "NOTE",
                        "object_id": latest_note.id,
                        "object_title": latest_note.title,
                        "actor": latest_note.updater.display_name if latest_note.updater else None,
                        "created_at": latest_note.updated_at,
                    },
                )
            )
        latest_activity = max(candidates, key=lambda item: item[0])[1] if candidates else None
        summaries.append(
            {
                "id": project.id,
                "key": project.key,
                "name": project.name,
                "description": project.description,
                "color": project.color,
                "archived": project.archived,
                "tasks_enabled": project.tasks_enabled,
                "notes_enabled": project.notes_enabled,
                "created_at": project.created_at,
                "role": role,
                "todo_count": todo_count,
                "done_count": done_count,
                "last_activity_at": max([activity, *(item[0] for item in candidates)]),
                "note_count": session.scalar(
                    select(func.count()).select_from(Note).where(Note.project_id == project.id)
                ),
                "todo_preview": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "priority": task.priority,
                        "assignee": task.assignee.display_name if task.assignee else None,
                        "updated_at": task.updated_at,
                    }
                    for task in previews
                ],
                "recent_note": (
                    {
                        "id": recent_note.id,
                        "title": recent_note.title,
                        "updated_at": recent_note.updated_at,
                        "updater": recent_note.updater.display_name if recent_note.updater else None,
                        "folder_path": folder_path(recent_note),
                    }
                    if recent_note
                    else None
                ),
                "latest_activity": latest_activity,
            }
        )
    return sorted(summaries, key=lambda item: (item["last_activity_at"], item["key"]), reverse=True)


def _task_access(session: Session, task: Task, principal: Principal) -> bool:
    return bool(
        membership(session, task.target_project_id, principal.user_id)
        or membership(session, task.origin_project_id, principal.user_id)
    )


def get_task(session: Session, task_id: int, principal: Principal, inspection: bool = False) -> Task:
    task = session.scalar(task_query().where(Task.id == task_id))
    if not task:
        raise NotFound(f"Task {task_id} not found")
    if not _task_access(session, task, principal):
        if not (inspection and principal.is_admin and principal.channel == "WEB"):
            raise NotFound(f"Task {task_id} not found")
        audit_inspection(session, principal, "task", str(task.id))
    return task


def _assignee(session: Session, username: str | None, project: Project) -> User | None:
    if not username:
        return None
    user = session.scalar(select(User).where(User.username == username.strip().lower(), User.active.is_(True)))
    if not user or not membership(session, project.id, user.id):
        raise Conflict("Assignee must be an active member of the target project")
    return user


def _event(task: Task, principal: Principal, event_type: str, payload: dict | None = None) -> TaskEvent:
    return TaskEvent(
        task_id=task.id,
        actor=principal.actor,
        actor_user_id=principal.user_id,
        channel=principal.channel,
        mcp_key_id=principal.mcp_key_id,
        event_type=event_type,
        payload_json=json.dumps(payload or {}, default=str),
    )


def create_task(session: Session, data: TaskCreate, principal: Principal, forced_origin: str | None = None) -> Task:
    target = project_by_key(session, data.target_project, principal)
    if not target.tasks_enabled:
        raise Conflict("Tasks are disabled for this project")
    origin = project_by_key(session, forced_origin or data.origin_project or data.target_project, principal)
    assignee = _assignee(session, data.assigned_user, target)
    task = Task(
        title=data.title,
        description=data.description,
        priority=data.priority,
        target_project=target,
        origin_project=origin,
        created_by=principal.actor,
        created_by_user_id=principal.user_id,
        assigned_user_id=assignee.id if assignee else None,
        tags=_tag_objects(session, target, data.tag_ids),
    )
    session.add(task)
    session.flush()
    session.add(_event(task, principal, "CREATED"))
    session.flush()
    return get_task(session, task.id, principal)


def _require_task_write(session: Session, task: Task, principal: Principal) -> None:
    require_member(session, task.origin_project, principal)
    require_member(session, task.target_project, principal)


def patch_task(session: Session, task: Task, data: TaskPatch, principal: Principal) -> Task:
    _require_task_write(session, task, principal)
    if task.status == Status.DONE:
        raise Conflict("Completed tasks are immutable; create a follow-up task")
    changes = data.model_dump(exclude_unset=True)
    new_target = task.target_project
    moved = False
    if "target_project" in changes:
        new_target = project_by_key(session, changes.pop("target_project"), principal)
        moved = new_target.id != task.target_project_id
        task.target_project = new_target
        if not new_target.tasks_enabled:
            raise Conflict("Tasks are disabled for this project")
    if "assigned_user" in changes:
        task.assignee = _assignee(session, changes.pop("assigned_user"), task.target_project)
    elif task.assignee and not membership(session, task.target_project.id, task.assignee.id):
        raise Conflict("Choose an assignee who belongs to the new target project")
    if "tag_ids" in changes:
        archived_ids = {tag.id for tag in task.tags if tag.archived_at is not None} if not moved else set()
        task.tags = _tag_objects(session, new_target, changes.pop("tag_ids") or [], archived_ids)
    elif moved and task.tags:
        raise Conflict("Moving a task requires replacement tags valid in the target project")
    for key, value in changes.items():
        setattr(task, key, value)
    session.flush()
    session.add(_event(task, principal, "UPDATED", data.model_dump(exclude_unset=True)))
    session.flush()
    return get_task(session, task.id, principal)


def complete_task(session: Session, task: Task, principal: Principal, summary: str) -> Task:
    _require_task_write(session, task, principal)
    if task.status == Status.DONE:
        raise Conflict("Task is already completed")
    task.status = Status.DONE
    task.completed_at = datetime.now(UTC)
    task.completed_by_user_id = principal.user_id
    session.add(Comment(task_id=task.id, author=principal.actor, body=summary))
    session.add(_event(task, principal, "COMPLETED", {"summary": summary}))
    if task.origin_project_id != task.target_project_id:
        session.add(
            Notification(
                project_id=task.origin_project_id,
                task_id=task.id,
                type="TASK_COMPLETED",
                message=f"{task.target_project.name} completed #{task.id}: {task.title}",
            )
        )
    session.flush()
    return get_task(session, task.id, principal)


def delete_task(session: Session, task: Task, principal: Principal) -> None:
    _require_task_write(session, task, principal)
    if task.status == Status.DONE:
        raise Conflict("Completed tasks are immutable; create a follow-up task")
    session.delete(task)


def list_tasks(
    session: Session,
    principal: Principal,
    *,
    project: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    tag: int | None = None,
    query: str | None = None,
    limit: int = 100,
    inspection: bool = False,
) -> list[Task]:
    if inspection and (not principal.is_admin or principal.channel != "WEB"):
        raise NotFound("Not Found")
    accessible = select(ProjectMembership.project_id).where(ProjectMembership.user_id == principal.user_id)
    statement = task_query().order_by(Task.updated_at.desc()).limit(min(limit, 200))
    if not inspection:
        statement = statement.where(or_(Task.target_project_id.in_(accessible), Task.origin_project_id.in_(accessible)))
    if project:
        selected_project = project_by_key(session, project, principal, inspection)
        statement = statement.where(Task.target_project_id == selected_project.id)
    if status:
        statement = statement.where(Task.status == status)
    if priority:
        statement = statement.where(Task.priority == priority)
    if tag:
        statement = statement.join(Task.tag_links).where(TaskTag.tag_id == tag)
    if query:
        pattern = f"%{query}%"
        statement = statement.where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    tasks = list(session.scalars(statement).unique())
    if inspection and any(not _task_access(session, task, principal) for task in tasks):
        audit_inspection(session, principal, "task-list", "*")
    return tasks


def task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "target_project": task.target_project.key,
        "origin_project": task.origin_project.key,
        "creator": task.creator.display_name if task.creator else task.created_by,
        "assignee": task.assignee.display_name if task.assignee else None,
        "completer": task.completer.display_name if task.completer else None,
        "tags": [tag_dict_for_task(tag) for tag in task.tags],
        "comments": [
            {"id": item.id, "author": item.author, "body": item.body, "created_at": item.created_at}
            for item in task.comments
        ],
        "events": [
            {
                "id": item.id,
                "actor": item.actor_user.display_name if item.actor_user else item.actor,
                "channel": item.channel,
                "mcp_key": item.mcp_key.name if item.mcp_key else None,
                "type": item.event_type,
                "payload": json.loads(item.payload_json),
                "created_at": item.created_at,
            }
            for item in task.events
        ],
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "completed_at": task.completed_at,
    }


def tag_dict_for_task(tag: Tag) -> dict:
    return {
        "id": tag.id,
        "project": tag.project.key,
        "name": tag.name,
        "color": tag.color,
        "description": tag.description,
        "archived_at": tag.archived_at,
        "usage_count": len(tag.tasks),
        "creator": tag.creator.display_name if tag.creator else None,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
    }


WIKI_LINK = re.compile(r"\[\[N-(\d+)(?:\|[^\]]*)?\]\]")


def _require_notes(project: Project) -> None:
    if not project.notes_enabled:
        raise NotFound(f"Project '{project.key}' not found")


def _folder(session: Session, folder_id: int, principal: Principal, inspection: bool = False) -> NoteFolder:
    folder = session.get(NoteFolder, folder_id)
    if not folder:
        raise NotFound("Folder not found")
    project_by_key(session, folder.project.key, principal, inspection)
    _require_notes(folder.project)
    return folder


def _note(session: Session, note_id: int, principal: Principal, inspection: bool = False) -> Note:
    note = session.scalar(
        select(Note)
        .options(
            selectinload(Note.project),
            selectinload(Note.folder),
            selectinload(Note.creator),
            selectinload(Note.updater),
        )
        .where(Note.id == note_id)
    )
    if not note:
        raise NotFound(f"Note {note_id} not found")
    project_by_key(session, note.project.key, principal, inspection)
    _require_notes(note.project)
    return note


def list_note_folders(
    session: Session, project: Project, principal: Principal, inspection: bool = False
) -> list[NoteFolder]:
    project_by_key(session, project.key, principal, inspection)
    _require_notes(project)
    return list(
        session.scalars(
            select(NoteFolder).where(NoteFolder.project_id == project.id).order_by(NoteFolder.name, NoteFolder.id)
        )
    )


def _validate_folder(session: Session, project: Project, folder_id: int | None) -> NoteFolder | None:
    if folder_id is None:
        return None
    folder = session.get(NoteFolder, folder_id)
    if not folder or folder.project_id != project.id:
        raise NotFound("Folder not found")
    return folder


def _unique_folder(
    session: Session, project_id: int, parent_id: int | None, name: str, exclude_id: int | None = None
) -> None:
    statement = select(NoteFolder.id).where(NoteFolder.project_id == project_id, NoteFolder.name == name)
    statement = statement.where(
        NoteFolder.parent_id.is_(None) if parent_id is None else NoteFolder.parent_id == parent_id
    )
    if exclude_id:
        statement = statement.where(NoteFolder.id != exclude_id)
    if session.scalar(statement):
        raise Conflict("A folder with this name already exists here")


def create_note_folder(session: Session, project: Project, data: NoteFolderCreate, principal: Principal) -> NoteFolder:
    require_member(session, project, principal)
    _require_notes(project)
    parent = _validate_folder(session, project, data.parent_id)
    _unique_folder(session, project.id, parent.id if parent else None, data.name)
    folder = NoteFolder(
        project_id=project.id,
        parent_id=parent.id if parent else None,
        name=data.name,
        created_by_user_id=principal.user_id,
    )
    try:
        with session.begin_nested():
            session.add(folder)
            session.flush()
    except IntegrityError as exc:
        raise Conflict("A folder with this name already exists here") from exc
    return folder


def patch_note_folder(session: Session, folder: NoteFolder, data: NoteFolderPatch, principal: Principal) -> NoteFolder:
    require_member(session, folder.project, principal)
    _require_notes(folder.project)
    changes = data.model_dump(exclude_unset=True)
    parent_id = changes.get("parent_id", folder.parent_id)
    parent = _validate_folder(session, folder.project, parent_id)
    cursor = parent
    while cursor:
        if cursor.id == folder.id:
            raise Conflict("Folders cannot contain themselves")
        cursor = cursor.parent
    name = changes.get("name", folder.name)
    _unique_folder(session, folder.project_id, parent.id if parent else None, name, folder.id)
    try:
        with session.begin_nested():
            folder.parent_id = parent.id if parent else None
            folder.name = name
            session.flush()
    except IntegrityError as exc:
        session.expire(folder)
        raise Conflict("A folder with this name already exists here") from exc
    return folder


def delete_note_folder(session: Session, folder: NoteFolder, principal: Principal) -> None:
    require_member(session, folder.project, principal)
    _require_notes(folder.project)
    if session.scalar(select(NoteFolder.id).where(NoteFolder.parent_id == folder.id)) or session.scalar(
        select(Note.id).where(Note.folder_id == folder.id)
    ):
        raise Conflict("Cannot delete a non-empty folder")
    session.delete(folder)


def _unique_note(
    session: Session, project_id: int, folder_id: int | None, title: str, exclude_id: int | None = None
) -> None:
    statement = select(Note.id).where(Note.project_id == project_id, Note.title == title)
    statement = statement.where(Note.folder_id.is_(None) if folder_id is None else Note.folder_id == folder_id)
    if exclude_id:
        statement = statement.where(Note.id != exclude_id)
    if session.scalar(statement):
        raise Conflict("A note with this title already exists here")


def _refresh_links(session: Session, note: Note) -> None:
    ids = {int(match) for match in WIKI_LINK.findall(note.markdown)}
    targets = (
        set(session.scalars(select(Note.id).where(Note.id.in_(ids), Note.project_id == note.project_id)))
        if ids
        else set()
    )
    session.query(NoteLink).filter(NoteLink.source_note_id == note.id).delete()
    session.add_all(NoteLink(source_note_id=note.id, target_note_id=target_id) for target_id in targets)


def create_note(session: Session, project: Project, data: NoteCreate, principal: Principal) -> Note:
    require_member(session, project, principal)
    _require_notes(project)
    folder = _validate_folder(session, project, data.folder_id)
    _unique_note(session, project.id, folder.id if folder else None, data.title)
    note = Note(
        project_id=project.id,
        folder_id=folder.id if folder else None,
        title=data.title,
        markdown=data.markdown,
        created_by_user_id=principal.user_id,
        updated_by_user_id=principal.user_id,
    )
    try:
        with session.begin_nested():
            session.add(note)
            session.flush()
            _refresh_links(session, note)
            session.flush()
    except IntegrityError as exc:
        raise Conflict("A note with this title already exists here") from exc
    return _note(session, note.id, principal)


def _revision(session: Session, note: Note, principal: Principal) -> None:
    session.add(
        NoteRevision(
            note_id=note.id,
            version=note.version,
            title=note.title,
            markdown=note.markdown,
            folder_id=note.folder_id,
            archived_at=note.archived_at,
            edited_by_user_id=principal.user_id,
        )
    )


def patch_note(session: Session, note: Note, data: NotePatch, principal: Principal) -> Note:
    require_member(session, note.project, principal)
    _require_notes(note.project)
    changes = data.model_dump(exclude_unset=True, exclude={"expected_version"})
    folder = _validate_folder(session, note.project, changes.get("folder_id", note.folder_id))
    title = changes.get("title", note.title)
    _unique_note(session, note.project_id, folder.id if folder else None, title, note.id)
    values = {
        "folder_id": folder.id if folder else None,
        "title": title,
        "markdown": changes.get("markdown", note.markdown),
        "archived_at": datetime.now(UTC)
        if changes.get("archived")
        else None
        if "archived" in changes
        else note.archived_at,
        "version": data.expected_version + 1,
        "updated_by_user_id": principal.user_id,
        "updated_at": datetime.now(UTC),
    }
    try:
        with session.begin_nested():
            result = session.execute(
                update(Note)
                .where(Note.id == note.id, Note.version == data.expected_version)
                .values(**values)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise Conflict("Note version is stale")
            _revision(session, note, principal)
            session.flush()
    except IntegrityError as exc:
        session.expire(note)
        raise Conflict("A note with this title already exists here") from exc
    session.expire(note)
    note = _note(session, note.id, principal)
    _refresh_links(session, note)
    session.flush()
    return note


def list_notes(
    session: Session,
    project: Project,
    principal: Principal,
    query: str | None = None,
    inspection: bool = False,
    limit: int = 100,
) -> list[Note]:
    project_by_key(session, project.key, principal, inspection)
    _require_notes(project)
    statement = (
        select(Note)
        .options(
            selectinload(Note.project),
            selectinload(Note.folder),
            selectinload(Note.creator),
            selectinload(Note.updater),
        )
        .where(Note.project_id == project.id)
        .order_by(Note.updated_at.desc(), Note.id.desc())
    )
    if query:
        pattern = f"%{query}%"
        statement = statement.where(or_(Note.title.ilike(pattern), Note.markdown.ilike(pattern)))
    return list(session.scalars(statement.limit(limit)))


def list_note_revisions(
    session: Session, note: Note, principal: Principal, inspection: bool = False
) -> list[NoteRevision]:
    project_by_key(session, note.project.key, principal, inspection)
    return list(
        session.scalars(
            select(NoteRevision)
            .options(selectinload(NoteRevision.editor))
            .where(NoteRevision.note_id == note.id)
            .order_by(NoteRevision.version.desc())
        )
    )


def restore_note(session: Session, note: Note, version: int, expected_version: int, principal: Principal) -> Note:
    revision = session.scalar(
        select(NoteRevision).where(NoteRevision.note_id == note.id, NoteRevision.version == version)
    )
    if not revision:
        raise NotFound("Revision not found")
    return patch_note(
        session,
        note,
        NotePatch(
            title=revision.title,
            markdown=revision.markdown,
            folder_id=revision.folder_id,
            archived=revision.archived_at is not None,
            expected_version=expected_version,
        ),
        principal,
    )


def folder_dict(folder: NoteFolder) -> dict:
    return {
        "id": folder.id,
        "project": folder.project.key,
        "parent_id": folder.parent_id,
        "name": folder.name,
        "creator": folder.creator.display_name if folder.creator else None,
        "created_at": folder.created_at,
    }


def note_dict(note: Note, session: Session | None = None) -> dict:
    result = {
        "id": note.id,
        "project": note.project.key,
        "folder_id": note.folder_id,
        "title": note.title,
        "markdown": note.markdown,
        "version": note.version,
        "creator": note.creator.display_name if note.creator else None,
        "updater": note.updater.display_name if note.updater else None,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "archived_at": note.archived_at,
    }
    if session:
        outgoing = list(
            session.scalars(
                select(Note)
                .join(NoteLink, NoteLink.target_note_id == Note.id)
                .where(NoteLink.source_note_id == note.id)
            )
        )
        backlinks = list(
            session.scalars(
                select(Note)
                .join(NoteLink, NoteLink.source_note_id == Note.id)
                .where(NoteLink.target_note_id == note.id)
            )
        )
        result["references"] = [{"id": item.id, "title": item.title} for item in outgoing]
        result["backlinks"] = [{"id": item.id, "title": item.title} for item in backlinks]
    return result
