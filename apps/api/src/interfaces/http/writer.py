from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from src.bootstrap.database import resolve_database_engine
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(tags=["writer"])


class ReviewerRulesCommand(BaseModel):
    custom_prompt: str = ""

DEFAULT_REVIEWER_PROMPT = """你是一名专业的小说连续性审校编辑。

你的工作是检查一段新生成的小说正文，从以下四个维度做结构化审核，并给出整体判断。

1. 连续性
2. 角色一致性
3. 悬念与伏笔
4. 风格一致性
"""


def _not_implemented(trace_id: str, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )


def _not_found(trace_id: str, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )


@router.get("/chapter-context/options", responses={501: {"model": ErrorResponse}})
def get_chapter_context_options(
    request: Request,
    project_id: str = Query(...),
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    chapters_stmt = (
        select(metadata.tables["chapters"])
        .where(metadata.tables["chapters"].c.project_id == project_id)
        .order_by(metadata.tables["chapters"].c.chapter_order.asc())
    )
    project_stmt = select(metadata.tables["projects"]).where(metadata.tables["projects"].c.project_id == project_id)
    entity_stmt = (
        select(metadata.tables["entities"])
        .where(metadata.tables["entities"].c.project_id == project_id)
        .where(metadata.tables["entities"].c.entity_kind == "Character")
        .order_by(metadata.tables["entities"].c.display_name.asc())
    )
    with engine.connect() as connection:
        project = connection.execute(project_stmt).first()
        chapters = connection.execute(chapters_stmt).all()
        entities = connection.execute(entity_stmt).all()
    if project is None:
        raise HTTPException(
            status_code=404,
            detail={
                "trace_id": x_trace_id or "trace-not-provided",
                "error": {
                    "code": "project_not_found",
                    "message": "Project not found",
                    "details": {"project_id": project_id},
                    "retryable": False,
                },
            },
        )
    return {
        "data": {
            "project_id": project.project_id,
            "project_name": project.name,
            "chapters": [
                {
                    "chapter_id": row.chapter_id,
                    "order": row.chapter_order,
                    "title": row.title,
                    "head_context": row.summary_text,
                }
                for row in chapters
            ],
            "pov_characters": [row.display_name for row in entities],
            "continuity_summary": project.analysis_summary or "",
            "available_scope_types": ["project_chapter", "worldline_branch"],
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.post("/chapter-context/builds", responses={501: {"model": ErrorResponse}})
def build_chapter_context(x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "chapter_context_build_not_implemented", "Chapter context build contract is frozen, implementation lands next", {})


@router.post("/drafts", responses={501: {"model": ErrorResponse}})
def create_draft(x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "draft_create_not_implemented", "Draft contract is frozen, implementation lands next", {})


@router.post("/drafts/{draft_id}/revisions", responses={501: {"model": ErrorResponse}})
def revise_draft(draft_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "draft_revision_not_implemented", "Draft revision contract is frozen, implementation lands next", {"draft_id": draft_id})


@router.post("/drafts/{draft_id}/finalizations", responses={501: {"model": ErrorResponse}})
def finalize_draft(draft_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "draft_finalization_not_implemented", "Draft finalization contract is frozen, implementation lands next", {"draft_id": draft_id})


@router.get("/workspaces/{workspace_id}/reviewer-rules", responses={501: {"model": ErrorResponse}})
def get_reviewer_rules(workspace_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["workspace_settings"]).where(
        metadata.tables["workspace_settings"].c.workspace_id == workspace_id
    )
    with engine.connect() as connection:
        row = connection.execute(stmt).first()
    custom_prompt = row.reviewer_rules_text if row else ""
    return {
        "data": {
            "custom_prompt": custom_prompt or "",
            "default_prompt": DEFAULT_REVIEWER_PROMPT,
            "is_custom": bool(custom_prompt),
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.put("/workspaces/{workspace_id}/reviewer-rules", responses={501: {"model": ErrorResponse}})
def save_reviewer_rules(
    workspace_id: str,
    payload: ReviewerRulesCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    workspaces = metadata.tables["workspaces"]
    settings = metadata.tables["workspace_settings"]
    with engine.begin() as connection:
        workspace = connection.execute(
            select(workspaces.c.workspace_id).where(workspaces.c.workspace_id == workspace_id)
        ).first()
        if workspace is None:
            raise _not_found(
                x_trace_id or "trace-not-provided",
                "workspace_not_found",
                "Workspace not found",
                {"workspace_id": workspace_id},
            )
        existing = connection.execute(
            select(settings.c.workspace_id).where(settings.c.workspace_id == workspace_id)
        ).first()
        values = {
            "workspace_id": workspace_id,
            "reviewer_rules_text": payload.custom_prompt,
            "updated_at": datetime.now(timezone.utc),
        }
        if existing is None:
            connection.execute(settings.insert().values(**values))
        else:
            connection.execute(
                settings.update().where(settings.c.workspace_id == workspace_id).values(**values)
            )
    return {
        "data": {
            "custom_prompt": payload.custom_prompt,
            "default_prompt": DEFAULT_REVIEWER_PROMPT,
            "is_custom": bool(payload.custom_prompt),
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }
