"""Native FastAPI novel analysis routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.project import ProjectManager
from app.services.archive_candidate_builder import ArchiveCandidateBuilder
from app.services.archive_library_service import ArchiveLibraryService
from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
from app.services.narrative_entity_archivist import NarrativeEntityArchivist
from app.services.parallel_world_config_generator import ParallelWorldConfigGenerator
from app.services.plot_inspiration_engine import PlotInspirationEngine
from app.services.reviewer_prompt import REVIEWER_SYSTEM_PROMPT
from app.services.worldline_engine_factory import build_worldline_engine
from app.services.worldline_single_world import current_world, resolve_branch_id
from app.services.zep_entity_reader import EntityNode, ZepEntityReader

from app.schemas.novel_schemas import (
    ArchiveCandidatesRequest,
    ChapterContextRequest,
    GenerateArchivesRequest,
    ParallelWorldConfigRequest,
    PlotInspirationRequest,
    ReviewerRulesRequest,
    SeedAnalysisRequest,
)

from .common import err, ok
from .graph_defaults import graph_entity_types

router = APIRouter(prefix="/novel", tags=["novel"])

# Lazy singletons — initialized on first use to avoid get_engine() before init_db()
_archive_candidate_builder = None
_chapter_context_pack_builder = None

def _get_archive_candidate_builder():
    global _archive_candidate_builder
    if _archive_candidate_builder is None:
        _archive_candidate_builder = ArchiveCandidateBuilder()
    return _archive_candidate_builder

def _get_chapter_context_pack_builder():
    global _chapter_context_pack_builder
    if _chapter_context_pack_builder is None:
        _chapter_context_pack_builder = ChapterContextPackBuilder()
    return _chapter_context_pack_builder


def _resolve_project_context(data: dict):
    project_id = data.get("project_id")
    graph_id = data.get("graph_id")
    project = None
    if project_id:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        graph_id = graph_id or project.graph_id
    return graph_id, project


def _load_seed_analysis(project):
    return ProjectManager.load_project_json(project.project_id, "seed_analysis.json") if project else None


def _build_entities_from_seed_analysis(seed_analysis):
    entities = []
    for item in seed_analysis.get("characters", []):
        entities.append(EntityNode(uuid=f"seed_character_{item.get('name', '')}", name=item.get("name", ""), labels=["Entity", "Character"], summary=item.get("profile_summary", ""), attributes={"importance_tier": item.get("importance_tier", "supporting"), "identity_hint": item.get("identity_hint", "角色")}))
    for item in seed_analysis.get("organizations", []):
        entities.append(EntityNode(uuid=f"seed_org_{item.get('name', '')}", name=item.get("name", ""), labels=["Entity", "Organization"], summary=item.get("summary", ""), attributes={"organization_type": item.get("organization_type", "organization"), "importance_tier": item.get("importance_tier", "major")}))
    return entities


def _candidate_override_map(data: dict) -> dict:
    overrides = {}
    for item in data.get("tier_overrides", []) or []:
        entity_uuid = str(item.get("entity_uuid") or item.get("candidate_id") or "").strip()
        tier = str(item.get("importance_tier") or "").strip()
        if entity_uuid and tier:
            overrides[entity_uuid] = tier
    for item in data.get("candidate_snapshot", []) or []:
        entity_uuid = str(item.get("entity_uuid") or item.get("candidate_id") or "").strip()
        tier = str(item.get("selected_importance_tier") or "").strip()
        if entity_uuid and tier:
            overrides.setdefault(entity_uuid, tier)
    return overrides


def _archive_candidates(graph_id, project, entity_types):
    if graph_id:
        filtered = ZepEntityReader().filter_defined_entities(graph_id=graph_id, defined_entity_types=entity_types, enrich_with_edges=True)
        return _get_archive_candidate_builder().build_from_entities(filtered.entities), {item.uuid: item for item in filtered.entities}, list(filtered.entity_types) + ["Relationship"]
    seed_analysis = _load_seed_analysis(project)
    if not seed_analysis:
        raise ValueError("当前项目既没有 graph_id，也没有可用的 seed_analysis.json")
    return _get_archive_candidate_builder().build_from_seed_analysis(seed_analysis), {}, ["Character", "Organization", "Relationship"]


@router.post("/archives/candidates")
async def list_archive_candidates(body: ArchiveCandidatesRequest):
    try:
        payload = body.model_dump()
        graph_id, project = _resolve_project_context(payload)
        candidates, _, types = _archive_candidates(graph_id, project, graph_entity_types(payload.get("entity_types"), graph_id))
        return ok({"project_id": project.project_id if project else None, "graph_id": graph_id, "count": len(candidates), "entity_types": types, "candidates": candidates})
    except Exception as exc:
        return err(exc)


@router.post("/archives/generate")
async def generate_archives(body: GenerateArchivesRequest):
    try:
        payload = body.model_dump()
        graph_id, project = _resolve_project_context(payload)
        candidates, entity_lookup, types = _archive_candidates(graph_id, project, graph_entity_types(payload.get("entity_types"), graph_id))
        raw = ProjectManager.load_project_json(project.project_id, "agent_profiles.json") if project else None
        archives = NarrativeEntityArchivist(candidate_builder=_get_archive_candidate_builder()).generate_archives_from_candidates(candidates, use_llm=payload.get("use_llm", True), tier_overrides=_candidate_override_map(payload), entity_lookup=entity_lookup, agent_profiles=(raw or {}).get("profiles", {}))
        data = {"graph_id": graph_id, "project_id": project.project_id if project else None, "count": len(archives), "entity_types": types, "archives": [item.to_dict() for item in archives]}
        if project:
            ProjectManager.save_project_json(project.project_id, "narrative_archives.json", data)
            synced = ArchiveLibraryService().sync_project_archives(project.project_id, force=True)
            archive_map = {item["entity_uuid"]: item["archive_id"] for item in synced}
            data["archives"] = [{**item, "archive_id": archive_map.get(item.get("entity_uuid"))} for item in data["archives"]]
        return ok(data)
    except Exception as exc:
        return err(exc)


@router.post("/parallel-world/config")
async def generate_parallel_world_config(body: ParallelWorldConfigRequest):
    try:
        payload = body.model_dump()
        graph_id, project = _resolve_project_context(payload)
        goal = payload.get("focus_question") or (project.analysis_goal if project else "") or "分析当前小说世界在变量注入后的持续演化"
        if graph_id:
            entities = ZepEntityReader().filter_defined_entities(graph_id=graph_id, defined_entity_types=graph_entity_types(payload.get("entity_types"), graph_id), enrich_with_edges=False).entities
        else:
            seed = _load_seed_analysis(project)
            if not seed:
                raise ValueError("当前项目既没有 graph_id，也没有可用的 seed_analysis.json")
            entities = _build_entities_from_seed_analysis(seed)
        config = ParallelWorldConfigGenerator().generate(analysis_goal=goal, entities=entities, variables=payload.get("variables", []), branch_count=payload.get("branch_count"), use_llm=payload.get("use_llm", True))
        if project:
            ProjectManager.save_project_json(project.project_id, "parallel_world_config.json", config.to_dict())
        return ok({"project_id": project.project_id if project else None, "graph_id": graph_id, "config": config.to_dict()})
    except Exception as exc:
        return err(exc)


@router.get("/seed-analysis/{project_id}")
async def get_seed_analysis(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return err(f"项目不存在: {project_id}", status_code=404)
    seed = _load_seed_analysis(project)
    return ok(seed) if seed else err("该项目尚未生成 seed_analysis", status_code=404)


@router.post("/seed-analysis")
async def run_seed_analysis(body: SeedAnalysisRequest):
    try:
        payload = body.model_dump()
        _, project = _resolve_project_context(payload)
        if not project:
            return err("请提供 project_id", status_code=400)
        seed = _load_seed_analysis(project)
        if not seed:
            text = ProjectManager.get_extracted_text(project.project_id)
            if not text:
                return err("项目缺少可用文本，无法生成种子分析", status_code=400)
            from app.services.novel_seed_analyzer import NovelSeedAnalyzer
            seed = NovelSeedAnalyzer().analyze_text(text=text, analysis_goal=payload.get("analysis_goal") or project.analysis_goal or "", project_name=project.name)
            ProjectManager.save_project_json(project.project_id, "seed_analysis.json", seed)
        return ok(seed)
    except Exception as exc:
        return err(exc)


@router.post("/plot/inspiration")
async def generate_plot_inspiration(body: PlotInspirationRequest):
    try:
        payload = body.model_dump()
        graph_id, project = _resolve_project_context(payload)
        creator_prompt = (payload.get("creator_prompt") or "").strip()
        if not creator_prompt:
            return err("请提供 creator_prompt", status_code=400)
        session_id = payload.get("session_id")
        focus_question = project.analysis_goal if project and project.analysis_goal else ""
        variables, actors, recent_events, branch_summary, branch_id = [], {}, [], {}, None
        if session_id:
            session = build_worldline_engine().get_session(session_id, project_id=project.project_id if project else None, graph_id=graph_id)
            if not session:
                return err(f"世界线会话不存在: {session_id}", status_code=404)
            focus_question = session.focus_question or focus_question
            variables = [item.to_dict() for item in session.world_variables]
            resolve_branch_id(payload.get("branch_id"))
            branch = current_world(session)
            branch_id = branch.branch_id
            branch_summary = {"branch_id": branch.branch_id, "title": branch.title, "core_change": branch.core_change}
            actors = branch.actor_states
            recent_events = [item.to_dict() for item in branch.timeline[-4:]]
        else:
            seed = _load_seed_analysis(project) if project else None
            if seed:
                actors = {item.get("name", ""): {"drive": "推动自身命运与故事主线", "tension": item.get("profile_summary", "")} for item in seed.get("characters", [])[:6] if item.get("name")}
                recent_events = seed.get("chapter_beats", [])[:4]
            branch_summary = {"title": "原始世界线", "core_change": focus_question or "沿原始小说主线推进"}
        result = PlotInspirationEngine().generate(focus_question=focus_question, branch_summary=branch_summary, creator_prompt=creator_prompt, variables=variables, recent_events=recent_events, actors=actors)
        return ok({"project_id": project.project_id if project else None, "graph_id": graph_id, "session_id": session_id, "branch_id": branch_id, "result": result})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/chapter-context/options")
async def chapter_context_options(project_id: str = ""):
    try:
        if not project_id.strip():
            return err("请提供 project_id", status_code=400)
        return ok(_get_chapter_context_pack_builder().build_options(project_id))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/chapter-context")
async def build_chapter_context(body: ChapterContextRequest):
    try:
        payload = body.model_dump()
        return ok(_get_chapter_context_pack_builder().build(payload))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/reviewer-rules")
async def get_reviewer_rules(project_id: str = ""):
    if not project_id:
        return err("需要 project_id", status_code=400)
    data = ProjectManager.load_project_json(project_id, "reviewer_rules.json")
    custom_prompt = (data or {}).get("custom_prompt", "")
    return ok({"custom_prompt": custom_prompt, "default_prompt": REVIEWER_SYSTEM_PROMPT, "is_custom": bool(custom_prompt)})


@router.put("/reviewer-rules")
async def save_reviewer_rules(body: ReviewerRulesRequest):
    payload = body.model_dump()
    project_id = payload.get("project_id", "")
    if not project_id:
        return err("需要 project_id", status_code=400)
    from datetime import datetime
    ProjectManager.save_project_json(project_id, "reviewer_rules.json", {"custom_prompt": payload.get("custom_prompt", ""), "updated_at": datetime.now().isoformat()})
    return ok(None)
