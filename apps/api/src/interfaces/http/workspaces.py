from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from src.bootstrap.database import resolve_database_engine
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


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


@router.get("", responses={501: {"model": ErrorResponse}})
def list_workspaces(request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    with engine.connect() as connection:
        rows = connection.execute(select(metadata.tables["workspaces"])).all()
    return {
        "data": [
            {
                "workspace_id": row.workspace_id,
                "name": row.name,
                "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
                "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
            }
            for row in rows
        ],
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.get("/{workspace_id}", responses={501: {"model": ErrorResponse}})
def get_workspace(workspace_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    with engine.connect() as connection:
        row = connection.execute(
            select(metadata.tables["workspaces"]).where(metadata.tables["workspaces"].c.workspace_id == workspace_id)
        ).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "trace_id": x_trace_id or "trace-not-provided",
                "error": {
                    "code": "workspace_not_found",
                    "message": "Workspace not found",
                    "details": {"workspace_id": workspace_id},
                    "retryable": False,
                },
            },
        )
    return {
        "data": {
            "workspace_id": row.workspace_id,
            "name": row.name,
            "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
            "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.post("/{workspace_id}/ingests", responses={501: {"model": ErrorResponse}})
def create_workspace_ingest(workspace_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(
        x_trace_id or "trace-not-provided",
        "workspace_ingest_not_implemented",
        "Workspace ingest contract is frozen, workflow implementation lands next",
        {"workspace_id": workspace_id},
    )
