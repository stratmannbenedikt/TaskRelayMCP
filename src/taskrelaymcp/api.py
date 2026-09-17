from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskrelaymcp.auth import (
    SESSION_COOKIE,
    CurrentAdmin,
    CurrentUser,
    ReadyUser,
    hash_password,
    hash_secret,
    new_session,
    same_origin,
    verify_password,
)
from taskrelaymcp.config import Principal, secure_cookies
from taskrelaymcp.db import session_scope
from taskrelaymcp.models import BrowserSession, MCPKey, Project, ProjectMembership, Status, Tag, User
from taskrelaymcp.schemas import (
    CompleteTask,
    Login,
    MCPKeyCreate,
    MembershipChange,
    NoteCreate,
    NoteFolderCreate,
    NoteFolderPatch,
    NotePatch,
    PasswordChange,
    PasswordReset,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    ProjectSummaryOut,
    TagCreate,
    TagOut,
    TagPatch,
    TagProposalApproval,
    TagProposalOut,
    TaskCreate,
    TaskOut,
    TaskPatch,
    UserCreate,
    UserOut,
)
from taskrelaymcp.services import (
    Conflict,
    NotFound,
    _folder,
    _note,
    add_member,
    archive_tag,
    complete_task,
    create_note,
    create_note_folder,
    create_project,
    create_tag,
    create_task,
    decide_tag_proposal,
    delete_note_folder,
    folder_dict,
    get_tag_proposal,
    get_task,
    list_members,
    list_note_folders,
    list_note_revisions,
    list_notes,
    list_project_summaries,
    list_tag_proposals,
    list_tags,
    list_tasks,
    note_dict,
    patch_note,
    patch_note_folder,
    patch_project,
    patch_tag,
    patch_task,
    project_by_key,
    proposal_dict,
    remove_member,
    restore_note,
    tag_dict,
    task_dict,
    transfer_owner,
)
from taskrelaymcp.services import (
    delete_task as remove_task,
)


def reject_inspection_writes(request: Request) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-TaskRelay-Inspection") == "true":
        raise HTTPException(403, "Inspection mode is read-only")


router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(reject_inspection_writes)])


def db_session():
    with session_scope() as session:
        yield session


DB = Annotated[Session, Depends(db_session)]


def missing(exc: NotFound) -> HTTPException:
    return HTTPException(404, str(exc))


def conflict(exc: Conflict) -> HTTPException:
    return HTTPException(409, str(exc))


def member_tag(db: Session, tag_id: int, principal: Principal) -> Tag:
    tag = db.scalar(
        select(Tag)
        .join(ProjectMembership, ProjectMembership.project_id == Tag.project_id)
        .where(Tag.id == tag_id, ProjectMembership.user_id == principal.user_id)
    )
    if not tag:
        raise HTTPException(404, "Tag not found")
    return tag


@router.post("/auth/login")
def login(data: Login, request: Request, response: Response, db: DB) -> dict:
    same_origin(request)
    user = db.scalar(select(User).where(User.username == data.username.strip().lower(), User.active.is_(True)))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    secret = new_session(db, user)
    response.set_cookie(
        SESSION_COOKIE,
        secret,
        httponly=True,
        secure=secure_cookies(),
        samesite="strict",
        max_age=14 * 24 * 60 * 60,
        path="/",
    )
    return user_view(user)


@router.post("/auth/logout", status_code=204)
def logout(
    _: CurrentUser,
    request: Request,
    response: Response,
    db: DB,
) -> Response:
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        db.query(BrowserSession).filter(BrowserSession.token_hash == hash_secret(session_token)).delete()
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure_cookies(), httponly=True, samesite="strict")
    response.status_code = 204
    return response


def user_view(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "active": user.active,
        "is_admin": user.is_admin,
        "must_change_password": user.must_change_password,
    }


@router.get("/auth/me")
def me(principal: CurrentUser, db: DB) -> dict:
    return user_view(db.get(User, principal.user_id))


@router.post("/auth/password")
def change_password(data: PasswordChange, principal: CurrentUser, db: DB) -> dict:
    user = db.get(User, principal.user_id)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    db.query(BrowserSession).filter(BrowserSession.user_id == user.id).delete()
    return {"changed": True}


@router.get("/users", response_model=list[UserOut])
def users(_: CurrentAdmin, db: DB) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.get("/directory")
def directory(_: ReadyUser, db: DB) -> list[dict]:
    return [
        {"username": user.username, "display_name": user.display_name}
        for user in db.scalars(select(User).where(User.active.is_(True)).order_by(User.username))
    ]


@router.post("/users", response_model=UserOut, status_code=201)
def add_user(data: UserCreate, _: CurrentAdmin, db: DB) -> User:
    try:
        user = User(
            username=data.username,
            display_name=data.display_name,
            password_hash=hash_password(data.temporary_password),
            is_admin=data.is_admin,
            active=True,
            must_change_password=True,
        )
        db.add(user)
        db.flush()
        return user
    except IntegrityError as exc:
        raise HTTPException(409, "Username already exists") from exc


@router.post("/users/{user_id}/reset-password", status_code=204)
def reset_password(user_id: int, data: PasswordReset, _: CurrentAdmin, db: DB) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.password_hash = hash_password(data.temporary_password)
    user.must_change_password = True
    db.query(BrowserSession).filter(BrowserSession.user_id == user.id).delete()
    return Response(status_code=204)


@router.post("/users/{user_id}/deactivate", status_code=204)
def deactivate_user(user_id: int, principal: CurrentAdmin, db: DB) -> Response:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if not user.active:
        return Response(status_code=204)
    if (
        user.is_admin
        and db.scalar(select(func.count()).select_from(User).where(User.active.is_(True), User.is_admin.is_(True))) <= 1
    ):
        raise HTTPException(409, "Cannot deactivate the final active administrator")
    if db.scalar(
        select(ProjectMembership).where(ProjectMembership.user_id == user.id, ProjectMembership.role == "OWNER")
    ):
        raise HTTPException(409, "Transfer owned projects before deactivating this user")
    user.active = False
    db.query(BrowserSession).filter(BrowserSession.user_id == user.id).delete()
    db.query(MCPKey).filter(MCPKey.user_id == user.id, MCPKey.revoked_at.is_(None)).update(
        {"revoked_at": datetime.now(UTC)}
    )
    return Response(status_code=204)


@router.get("/mcp-keys")
def mcp_keys(principal: ReadyUser, db: DB) -> list[dict]:
    return [
        {"id": key.id, "name": key.name, "created_at": key.created_at, "revoked_at": key.revoked_at}
        for key in db.scalars(
            select(MCPKey).where(MCPKey.user_id == principal.user_id).order_by(MCPKey.created_at.desc())
        )
    ]


@router.post("/mcp-keys", status_code=201)
def add_mcp_key(data: MCPKeyCreate, principal: ReadyUser, db: DB) -> dict:
    secret = f"trm_{secrets.token_urlsafe(32)}"
    try:
        key = MCPKey(user_id=principal.user_id, name=data.name.strip(), secret_hash=hash_secret(secret))
        db.add(key)
        db.flush()
        return {"id": key.id, "name": key.name, "secret": secret, "created_at": key.created_at, "revoked_at": None}
    except IntegrityError as exc:
        raise HTTPException(409, "Key name already exists") from exc


@router.delete("/mcp-keys/{key_id}", status_code=204)
def revoke_mcp_key(key_id: int, principal: ReadyUser, db: DB) -> Response:
    key = db.scalar(select(MCPKey).where(MCPKey.id == key_id, MCPKey.user_id == principal.user_id))
    if not key:
        raise HTTPException(404, "Key not found")
    key.revoked_at = datetime.now(UTC)
    return Response(status_code=204)


@router.get("/projects", response_model=list[ProjectSummaryOut])
def projects(principal: ReadyUser, db: DB, include_archived: bool = False, inspection: bool = False) -> list[dict]:
    try:
        return list_project_summaries(db, principal, include_archived, inspection)
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/projects", response_model=ProjectOut, status_code=201)
def add_project(data: ProjectCreate, principal: ReadyUser, db: DB) -> Project:
    try:
        return create_project(db, data, principal)
    except Conflict as exc:
        raise conflict(exc) from exc
    except IntegrityError as exc:
        raise HTTPException(409, "Project key already exists") from exc


@router.patch("/projects/{key}", response_model=ProjectOut)
def update_project(key: str, data: ProjectPatch, principal: ReadyUser, db: DB) -> Project:
    try:
        return patch_project(db, project_by_key(db, key, principal), data, principal)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/projects/{key}/members")
def members(key: str, principal: ReadyUser, db: DB) -> list[dict]:
    try:
        return [
            {"username": item.user.username, "display_name": item.user.display_name, "role": item.role}
            for item in list_members(db, project_by_key(db, key, principal), principal)
        ]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/projects/{key}/members", status_code=201)
def create_membership(key: str, data: MembershipChange, principal: ReadyUser, db: DB) -> dict:
    try:
        item = add_member(db, project_by_key(db, key, principal), data.username, principal)
        return {"username": item.user.username, "display_name": item.user.display_name, "role": item.role}
    except NotFound as exc:
        raise missing(exc) from exc


@router.delete("/projects/{key}/members/{username}", status_code=204)
def delete_membership(key: str, username: str, principal: ReadyUser, db: DB) -> Response:
    try:
        remove_member(db, project_by_key(db, key, principal), username, principal)
        return Response(status_code=204)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.post("/projects/{key}/transfer-owner", status_code=204)
def change_owner(key: str, data: MembershipChange, principal: ReadyUser, db: DB) -> Response:
    try:
        transfer_owner(db, project_by_key(db, key, principal), data.username, principal)
        return Response(status_code=204)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/projects/{key}/note-folders")
def note_folders(key: str, principal: ReadyUser, db: DB, inspection: bool = False) -> list[dict]:
    try:
        return [
            folder_dict(item)
            for item in list_note_folders(db, project_by_key(db, key, principal, inspection), principal, inspection)
        ]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/projects/{key}/note-folders", status_code=201)
def add_note_folder(key: str, data: NoteFolderCreate, principal: ReadyUser, db: DB) -> dict:
    try:
        return folder_dict(create_note_folder(db, project_by_key(db, key, principal), data, principal))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.patch("/note-folders/{folder_id}")
def update_note_folder(folder_id: int, data: NoteFolderPatch, principal: ReadyUser, db: DB) -> dict:
    try:
        return folder_dict(patch_note_folder(db, _folder(db, folder_id, principal), data, principal))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.delete("/note-folders/{folder_id}", status_code=204)
def remove_note_folder(folder_id: int, principal: ReadyUser, db: DB) -> Response:
    try:
        delete_note_folder(db, _folder(db, folder_id, principal), principal)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc
    return Response(status_code=204)


@router.get("/projects/{key}/notes")
def notes(
    key: str,
    principal: ReadyUser,
    db: DB,
    q: str | None = None,
    inspection: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict]:
    try:
        return [
            note_dict(item)
            for item in list_notes(db, project_by_key(db, key, principal, inspection), principal, q, inspection, limit)
        ]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/projects/{key}/notes", status_code=201)
def add_note(key: str, data: NoteCreate, principal: ReadyUser, db: DB) -> dict:
    try:
        return note_dict(create_note(db, project_by_key(db, key, principal), data, principal), db)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/notes/{note_id}")
def note(note_id: int, principal: ReadyUser, db: DB, inspection: bool = False) -> dict:
    try:
        return note_dict(_note(db, note_id, principal, inspection), db)
    except NotFound as exc:
        raise missing(exc) from exc


@router.patch("/notes/{note_id}")
def update_note(note_id: int, data: NotePatch, principal: ReadyUser, db: DB) -> dict:
    try:
        return note_dict(patch_note(db, _note(db, note_id, principal), data, principal), db)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/notes/{note_id}/revisions")
def note_revisions(note_id: int, principal: ReadyUser, db: DB, inspection: bool = False) -> list[dict]:
    try:
        return [
            {
                "version": item.version,
                "title": item.title,
                "markdown": item.markdown,
                "folder_id": item.folder_id,
                "archived_at": item.archived_at,
                "editor": item.editor.display_name,
                "created_at": item.created_at,
            }
            for item in list_note_revisions(db, _note(db, note_id, principal, inspection), principal, inspection)
        ]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/notes/{note_id}/revisions/{version}/restore")
def restore_note_revision(note_id: int, version: int, data: NotePatch, principal: ReadyUser, db: DB) -> dict:
    try:
        return note_dict(restore_note(db, _note(db, note_id, principal), version, data.expected_version, principal), db)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/tasks", response_model=list[TaskOut])
def tasks(
    principal: ReadyUser,
    db: DB,
    project: str | None = None,
    status: Status | None = None,
    priority: str | None = None,
    tag: int | None = None,
    q: str | None = None,
    inspection: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[dict]:
    try:
        return [
            task_dict(item)
            for item in list_tasks(
                db,
                principal,
                project=project,
                status=status,
                priority=priority,
                tag=tag,
                query=q,
                limit=limit,
                inspection=inspection,
            )
        ]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/tasks", response_model=TaskOut, status_code=201)
def add_task(data: TaskCreate, principal: ReadyUser, db: DB) -> dict:
    try:
        return task_dict(create_task(db, data, principal))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/tasks/{task_id}", response_model=TaskOut)
def task(task_id: int, principal: ReadyUser, db: DB, inspection: bool = False) -> dict:
    try:
        return task_dict(get_task(db, task_id, principal, inspection))
    except NotFound as exc:
        raise missing(exc) from exc


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskPatch, principal: ReadyUser, db: DB) -> dict:
    try:
        return task_dict(patch_task(db, get_task(db, task_id, principal), data, principal))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, principal: ReadyUser, db: DB) -> Response:
    try:
        remove_task(db, get_task(db, task_id, principal), principal)
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc
    return Response(status_code=204)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def finish(task_id: int, data: CompleteTask, principal: ReadyUser, db: DB) -> dict:
    try:
        return task_dict(complete_task(db, get_task(db, task_id, principal), principal, data.summary))
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.get("/tags", response_model=list[TagOut])
def tags(
    principal: ReadyUser, db: DB, project: str | None = None, include_archived: bool = False, inspection: bool = False
) -> list[dict]:
    try:
        return [tag_dict(db, tag) for tag in list_tags(db, principal, project, include_archived, inspection)]
    except NotFound as exc:
        raise missing(exc) from exc


@router.get("/projects/{key}/tags", response_model=list[TagOut])
def project_tags(
    key: str, principal: ReadyUser, db: DB, include_archived: bool = False, inspection: bool = False
) -> list[dict]:
    try:
        return [tag_dict(db, tag) for tag in list_tags(db, principal, key, include_archived, inspection)]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/projects/{key}/tags", response_model=TagOut, status_code=201)
def add_tag(key: str, data: TagCreate, principal: ReadyUser, db: DB) -> dict:
    try:
        return tag_dict(
            db, create_tag(db, project_by_key(db, key, principal), **data.model_dump(), principal=principal)
        )
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.patch("/tags/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, data: TagPatch, principal: ReadyUser, db: DB) -> dict:
    try:
        return tag_dict(
            db, patch_tag(db, member_tag(db, tag_id, principal), data.model_dump(exclude_unset=True), principal)
        )
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.post("/tags/{tag_id}/archive", response_model=TagOut)
def archive_tag_route(tag_id: int, principal: ReadyUser, db: DB) -> dict:
    try:
        return tag_dict(db, archive_tag(db, member_tag(db, tag_id, principal), principal))
    except NotFound as exc:
        raise missing(exc) from exc


@router.get("/tag-proposals", response_model=list[TagProposalOut])
def tag_proposals(
    principal: ReadyUser, db: DB, project: str | None = None, status: str | None = None, inspection: bool = False
) -> list[dict]:
    try:
        return [proposal_dict(proposal) for proposal in list_tag_proposals(db, principal, project, status, inspection)]
    except NotFound as exc:
        raise missing(exc) from exc


@router.post("/tag-proposals/{proposal_id}/approve", response_model=TagProposalOut)
def approve_tag_proposal(proposal_id: int, data: TagProposalApproval, principal: ReadyUser, db: DB) -> dict:
    try:
        return proposal_dict(
            decide_tag_proposal(
                db, get_tag_proposal(db, proposal_id, principal), principal, True, data.model_dump(exclude_unset=True)
            )
        )
    except NotFound as exc:
        raise missing(exc) from exc
    except Conflict as exc:
        raise conflict(exc) from exc


@router.post("/tag-proposals/{proposal_id}/reject", response_model=TagProposalOut)
def reject_tag_proposal(proposal_id: int, principal: ReadyUser, db: DB) -> dict:
    try:
        return proposal_dict(decide_tag_proposal(db, get_tag_proposal(db, proposal_id, principal), principal, False))
    except NotFound as exc:
        raise missing(exc) from exc
