package llm

import (
	"context"
	"strings"
)

type ModuleRegistryInput struct {
	TenantID  string
	ProjectID string
}

type ModuleRecord struct {
	ModuleKey   string `json:"module_key"`
	Group       string `json:"group"`
	Label       string `json:"label"`
	Description string `json:"description"`
}

type ModuleRegistry interface {
	ListModules(context.Context, ModuleRegistryInput) ([]ModuleRecord, error)
}

type StaticModuleRegistry struct {
	modules []ModuleRecord
}

func NewStaticModuleRegistry() StaticModuleRegistry {
	return StaticModuleRegistry{modules: documentedModules()}
}

func (r StaticModuleRegistry) ListModules(ctx context.Context, input ModuleRegistryInput) ([]ModuleRecord, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ProjectID) == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	modules := append([]ModuleRecord(nil), r.modules...)
	return modules, nil
}

func documentedModules() []ModuleRecord {
	return []ModuleRecord{
		{ModuleKey: "story_ontology", Group: "Seed / Graph", Label: "Story Ontology", Description: "Generate the project story ontology."},
		{ModuleKey: "local_block_facts", Group: "Seed / Graph", Label: "Local Block Facts", Description: "Extract local facts from text blocks."},
		{ModuleKey: "contextual_block_analysis", Group: "Seed / Graph", Label: "Contextual Block Analysis", Description: "Analyze text blocks with project context."},
		{ModuleKey: "anchor_point_summary", Group: "Seed / Graph", Label: "Anchor Point Summary", Description: "Summarize narrative anchor points."},
		{ModuleKey: "entity_resolution", Group: "Seed / Graph", Label: "Entity Resolution", Description: "Resolve aliases and canonical entities."},
		{ModuleKey: "novel_chapter_summarizer", Group: "Seed / Graph", Label: "Novel Chapter Summarizer", Description: "Summarize chapter-level narrative state."},
		{ModuleKey: "sequential_reading", Group: "Seed / Graph", Label: "Sequential Reading", Description: "Read source text in order and produce structured notes."},
		{ModuleKey: "analysis_planner", Group: "Seed / Graph", Label: "Analysis Planner", Description: "Plan novel analysis tasks and write the analysis workspace task pack."},
		{ModuleKey: "analysis_worker", Group: "Seed / Graph", Label: "Analysis Worker", Description: "Process source segments and write analysis notes and candidates into the workspace."},
		{ModuleKey: "character_agent_profile", Group: "Seed / Graph", Label: "Character Agent Profile", Description: "Generate character profiles for agent use."},
		{ModuleKey: "graph_bond_generator", Group: "Seed / Graph", Label: "Graph Bond Generator", Description: "Generate candidate graph bonds and relationships."},
		{ModuleKey: "narrative_archives", Group: "Archive / Assets", Label: "Narrative Archives", Description: "Build narrative archive records."},
		{ModuleKey: "asset_ingestion", Group: "Archive / Assets", Label: "Asset Ingestion", Description: "Ingest freeform material into assets."},
		{ModuleKey: "asset_search_embedding", Group: "Archive / Assets", Label: "Asset Search Embedding", Description: "Embed asset search queries for vector and hybrid retrieval."},
		{ModuleKey: "style_extractor", Group: "Archive / Assets", Label: "Style Extractor", Description: "Extract reusable style and voice assets."},
		{ModuleKey: "character_dialogue", Group: "Character Console", Label: "Character Dialogue", Description: "Generate character dialogue turns and candidate state updates."},
		{ModuleKey: "parallel_world_config", Group: "Worldline", Label: "Parallel World Config", Description: "Prepare worldline configuration."},
		{ModuleKey: "worldline_cast_planner", Group: "Worldline", Label: "Worldline Cast Planner", Description: "Analyze a simulation goal and select participating agents and context refs."},
		{ModuleKey: "worldline_agent_prepare", Group: "Worldline", Label: "Worldline Agent Prepare", Description: "Prepare worldline character agents."},
		{ModuleKey: "worldline_agent_dialogue", Group: "Worldline", Label: "Worldline Agent Dialogue", Description: "Generate worldline agent dialogue turns."},
		{ModuleKey: "worldline_character_proposal", Group: "Worldline", Label: "Worldline Character Proposal", Description: "Propose character actions in worldline runs."},
		{ModuleKey: "worldline_director", Group: "Worldline", Label: "Worldline Director", Description: "Direct worldline simulation steps."},
		{ModuleKey: "worldline_agent_action", Group: "Worldline", Label: "Worldline Agent Action", Description: "Generate worldline agent actions."},
		{ModuleKey: "worldline_goal_evaluator", Group: "Worldline", Label: "Worldline Goal Evaluator", Description: "Evaluate worldline run goals."},
		{ModuleKey: "writer_retrieval_planner", Group: "Writer", Label: "Writer Retrieval Planner", Description: "Plan retrieval before writing."},
		{ModuleKey: "writer_orchestrator", Group: "Writer", Label: "Writer Orchestrator", Description: "Call tools and assemble writing context."},
		{ModuleKey: "writer_composer", Group: "Writer", Label: "Writer Composer", Description: "Write draft prose from a writing brief."},
		{ModuleKey: "writer_dedup_extractor", Group: "Writer", Label: "Writer Dedup Extractor", Description: "Extract repeated-risk patterns from adopted manuscript."},
		{ModuleKey: "writer_book_planner", Group: "Writer", Label: "Writer Book Planner", Description: "Generate candidate plans for persisted draft book plans."},
		{ModuleKey: "writer_asset_distiller", Group: "Writer", Label: "Writer Asset Distiller", Description: "Distill adopted manuscript into disabled asset candidates with evidence."},
		{ModuleKey: "writer_reviewer", Group: "Writer", Label: "Writer Reviewer", Description: "Review drafts for style, continuity, and repetition."},
	}
}
