from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import or_, select

from src.bootstrap.database import resolve_database_engine
from src.modules.graph.command_service import update_graph_template_config as update_graph_template_config_command
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["graph"])


class GraphTemplateConfigCommand(BaseModel):
    status: str
    project_id: str | None = None
    config_artifact_id: str | None = None


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


def _error(trace_id: str, status_code: int, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=status_code,
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


@router.post("/graph-builds", responses={501: {"model": ErrorResponse}})
def start_graph_build(workspace_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(
        x_trace_id or "trace-not-provided",
        "graph_build_not_implemented",
        "Graph build contract is frozen, workflow implementation lands next",
        {"workspace_id": workspace_id},
    )


@router.get("/graph", responses={501: {"model": ErrorResponse}})
def get_workspace_graph(workspace_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    projects = metadata.tables["projects"]
    graph_nodes = metadata.tables["graph_nodes"]
    graph_edges = metadata.tables["graph_edges"]
    with engine.connect() as connection:
        project_ids = [
            row.project_id
            for row in connection.execute(
                select(projects.c.project_id).where(projects.c.workspace_id == workspace_id)
            ).all()
        ]
        nodes = connection.execute(
            select(graph_nodes).where(graph_nodes.c.project_id.in_(project_ids))
        ).all() if project_ids else []
        edges = connection.execute(
            select(graph_edges).where(graph_edges.c.project_id.in_(project_ids))
        ).all() if project_ids else []
    return {
        "data": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": [
                {
                    "graph_node_id": row.graph_node_id,
                    "project_id": row.project_id,
                    "canonical_name": row.canonical_name,
                    "display_name": row.display_name,
                    "node_type": row.node_type,
                    "summary": row.summary,
                }
                for row in nodes
            ],
            "edges": [
                {
                    "graph_edge_id": row.graph_edge_id,
                    "project_id": row.project_id,
                    "source_node_id": row.source_node_id,
                    "target_node_id": row.target_node_id,
                    "edge_type": row.edge_type,
                    "summary": row.summary,
                }
                for row in edges
            ],
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.get("/graph/nodes/{node_id}", responses={501: {"model": ErrorResponse}})
def get_graph_node(workspace_id: str, node_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    projects = metadata.tables["projects"]
    graph_nodes = metadata.tables["graph_nodes"]
    graph_edges = metadata.tables["graph_edges"]
    with engine.connect() as connection:
        project_ids = [
            row.project_id
            for row in connection.execute(
                select(projects.c.project_id).where(projects.c.workspace_id == workspace_id)
            ).all()
        ]
        node = connection.execute(
            select(graph_nodes)
            .where(graph_nodes.c.graph_node_id == node_id)
            .where(graph_nodes.c.project_id.in_(project_ids))
        ).first() if project_ids else None
        edges = connection.execute(
            select(graph_edges).where(
                or_(
                    graph_edges.c.source_node_id == node_id,
                    graph_edges.c.target_node_id == node_id,
                )
            )
        ).all() if node is not None else []
    if node is None:
        raise HTTPException(
            status_code=404,
            detail={
                "trace_id": x_trace_id or "trace-not-provided",
                "error": {
                    "code": "graph_node_not_found",
                    "message": "Graph node not found",
                    "details": {"workspace_id": workspace_id, "node_id": node_id},
                    "retryable": False,
                },
            },
        )
    return {
        "data": {
            "node": {
                "graph_node_id": node.graph_node_id,
                "project_id": node.project_id,
                "canonical_name": node.canonical_name,
                "display_name": node.display_name,
                "node_type": node.node_type,
                "summary": node.summary,
            },
            "edges": [
                {
                    "graph_edge_id": row.graph_edge_id,
                    "project_id": row.project_id,
                    "source_node_id": row.source_node_id,
                    "target_node_id": row.target_node_id,
                    "edge_type": row.edge_type,
                    "summary": row.summary,
                }
                for row in edges
            ],
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.patch("/graph-template-configs/{template_key}", responses={501: {"model": ErrorResponse}})
def update_graph_template_config(
    workspace_id: str,
    template_key: str,
    payload: GraphTemplateConfigCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = update_graph_template_config_command(engine, workspace_id, template_key, payload.model_dump())
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "没有可用 project" in message else 400
        raise _error(
            x_trace_id or "trace-not-provided",
            status_code,
            "graph_template_config_invalid",
            message,
            {"workspace_id": workspace_id, "template_key": template_key},
        )
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}
