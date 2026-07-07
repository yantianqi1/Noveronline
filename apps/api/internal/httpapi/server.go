package httpapi

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"

	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/traces"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
)

type Config struct {
	SessionAuthSecret               string
	AuthReader                      auth.Reader
	Authorizer                      auth.Authorizer
	WriterStarter                   workflows.WriterStarter
	WriterReader                    workflows.WriterReader
	WriterEventReader               workflows.WriterEventReader
	WriterCanceller                 workflows.WriterCanceller
	DraftAdoptionStore              workflows.DraftAdoptionStore
	DraftReviewStore                workflows.DraftReviewStore
	ManuscriptReader                workflows.ManuscriptReader
	WorkflowReader                  workflows.WorkflowReader
	WorkflowEventReader             workflows.WorkflowEventReader
	WorkflowCanceller               workflows.WorkflowCanceller
	WorkflowRetrier                 workflows.WorkflowRetrier
	SeedStarter                     workflows.SeedRunStarter
	SeedRunReader                   workflows.SeedRunReader
	ProjectOverviewReader           projectoverview.Reader
	ProjectReadinessReader          projectreadiness.Reader
	AgentHelloStarter               workflows.AgentHelloStarter
	LLMResolver                     llm.Resolver
	LLMModuleRegistry               llm.ModuleRegistry
	LLMBindingStore                 llm.BindingStore
	LLMCatalogReader                llm.CatalogReader
	LLMChannelStore                 llm.ChannelStore
	LLMModelSyncer                  llm.ModelSyncer
	LLMSettingsReader               llm.SettingsReader
	LLMTelemetryReader              llm.TelemetryReader
	TraceReader                     traces.Reader
	TraceAccessChecker              traces.AccessChecker
	TraceExportAuditor              traces.ExportAuditor
	SourceFileStore                 sourcefiles.Store
	SourceFileObjectWriter          sourcefiles.ObjectWriter
	AssetReader                     assets.Reader
	ArchiveMemoryReader             assets.ArchiveMemoryReader
	ArchiveMemoryReviewStore        assets.ArchiveMemoryReviewStore
	AssetAdoptionStore              assets.AdoptionStore
	AssetMutationStore              assets.MutationStore
	AssetBulkActionStore            assets.BulkActionStore
	AssetIngestionStarter           workflows.AssetIngestionStarter
	AssetIngestionReader            workflows.AssetIngestionReader
	AssetReindexStarter             workflows.AssetReindexStarter
	StyleExtractionStarter          workflows.StyleExtractionStarter
	StyleExtractionReader           workflows.StyleExtractionReader
	StoryGraphBuildStarter          workflows.StoryGraphBuildStarter
	StoryGraphBondGenerationStarter workflows.StoryGraphBondGenerationStarter
	StoryGraphReader                storygraph.Reader
	StoryGraphEvidenceAccess        storygraph.EvidenceAccessChecker
	WorldlineSavedPathReader        worldline.SavedPathReader
	WorldlineSavedPathStore         worldline.SavedPathStore
	WorldlineSessionStarter         worldline.SessionStarter
	WorldlineStepStarter            worldline.StepStarter
	WorldlineSessionReader          worldline.SessionReader
	WorldlineTimelineReader         worldline.TimelineReader
	WorldlineEventReader            worldline.EventReader
	WorldlineEventAdoptionStore     worldline.EventAdoptionStore
	WorldlineEventMutationStore     worldline.EventMutationStore
	WorldlineVariableStore          worldline.VariableStore
	WorldlinePreparationStore       worldline.PreparationStore
	CharacterConsoleStore           characterconsole.Store
}

type Server struct {
	sessionAuthSecret               string
	authReader                      auth.Reader
	authorizer                      auth.Authorizer
	writerStarter                   workflows.WriterStarter
	writerReader                    workflows.WriterReader
	writerEventReader               workflows.WriterEventReader
	writerCanceller                 workflows.WriterCanceller
	draftAdoptionStore              workflows.DraftAdoptionStore
	draftReviewStore                workflows.DraftReviewStore
	manuscriptReader                workflows.ManuscriptReader
	workflowReader                  workflows.WorkflowReader
	workflowEventReader             workflows.WorkflowEventReader
	workflowCanceller               workflows.WorkflowCanceller
	workflowRetrier                 workflows.WorkflowRetrier
	seedStarter                     workflows.SeedRunStarter
	seedRunReader                   workflows.SeedRunReader
	projectOverviewReader           projectoverview.Reader
	projectReadinessReader          projectreadiness.Reader
	agentHelloStarter               workflows.AgentHelloStarter
	llmResolver                     llm.Resolver
	llmModuleRegistry               llm.ModuleRegistry
	llmBindingStore                 llm.BindingStore
	llmCatalogReader                llm.CatalogReader
	llmChannelStore                 llm.ChannelStore
	llmModelSyncer                  llm.ModelSyncer
	llmSettingsReader               llm.SettingsReader
	llmTelemetryReader              llm.TelemetryReader
	traceReader                     traces.Reader
	traceAccessChecker              traces.AccessChecker
	traceExportAuditor              traces.ExportAuditor
	sourceFileStore                 sourcefiles.Store
	sourceFileObjectWriter          sourcefiles.ObjectWriter
	assetReader                     assets.Reader
	archiveMemoryReader             assets.ArchiveMemoryReader
	archiveMemoryReviewStore        assets.ArchiveMemoryReviewStore
	assetAdoptionStore              assets.AdoptionStore
	assetMutationStore              assets.MutationStore
	assetBulkActionStore            assets.BulkActionStore
	assetIngestionStarter           workflows.AssetIngestionStarter
	assetIngestionReader            workflows.AssetIngestionReader
	assetReindexStarter             workflows.AssetReindexStarter
	styleExtractionStarter          workflows.StyleExtractionStarter
	styleExtractionReader           workflows.StyleExtractionReader
	storyGraphBuildStarter          workflows.StoryGraphBuildStarter
	storyGraphBondGenerationStarter workflows.StoryGraphBondGenerationStarter
	storyGraphReader                storygraph.Reader
	storyGraphEvidenceAccess        storygraph.EvidenceAccessChecker
	worldlineSavedPathReader        worldline.SavedPathReader
	worldlineSavedPathStore         worldline.SavedPathStore
	worldlineSessionStarter         worldline.SessionStarter
	worldlineStepStarter            worldline.StepStarter
	worldlineSessionReader          worldline.SessionReader
	worldlineTimelineReader         worldline.TimelineReader
	worldlineEventReader            worldline.EventReader
	worldlineEventAdoptionStore     worldline.EventAdoptionStore
	worldlineEventMutationStore     worldline.EventMutationStore
	worldlineVariableStore          worldline.VariableStore
	worldlinePreparationStore       worldline.PreparationStore
	characterConsoleStore           characterconsole.Store
}

type apiError struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	Details   map[string]any `json:"details"`
	RequestID string         `json:"request_id"`
}

const sessionCookieName = "mirofish_session"

type actorUserIDContextKey struct{}

type errorEnvelope struct {
	Error apiError `json:"error"`
}

type startWriterRunRequest struct {
	Mode        string         `json:"mode"`
	Instruction string         `json:"instruction"`
	Options     map[string]any `json:"options"`
}

type startWriterRunResponse struct {
	RunID     string `json:"run_id"`
	TraceID   string `json:"trace_id"`
	ProjectID string `json:"project_id"`
	Status    string `json:"status"`
}

type adoptDraftRequest struct {
	BodyTenantID string `json:"tenant_id"`
	ChapterID    string `json:"chapter_id"`
	SceneID      string `json:"scene_id"`
	BlockOrder   int    `json:"block_order"`
}

type startDraftReviewRequest struct {
	BodyTenantID  string         `json:"tenant_id"`
	BodyProjectID string         `json:"project_id"`
	RunID         string         `json:"run_id"`
	Note          string         `json:"note"`
	Options       map[string]any `json:"options"`
}

type startHelloAgentResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type startSeedRunRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	UploadID     string         `json:"upload_id"`
	Options      map[string]any `json:"options"`
}

type startWorldlineSessionRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Goal         string         `json:"goal"`
	AnchorPathID string         `json:"anchor_path_id"`
	Options      map[string]any `json:"options"`
}

type startWorldlineStepRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Mode         string         `json:"mode"`
	Options      map[string]any `json:"options"`
}

type createCharacterInteractionRequest struct {
	BodyTenantID       string         `json:"tenant_id"`
	BodyProjectID      string         `json:"project_id"`
	WorldlineSessionID string         `json:"worldline_session_id"`
	AnchorType         string         `json:"anchor_type"`
	AnchorID           string         `json:"anchor_id"`
	POVAgentID         string         `json:"pov_agent_id"`
	Mode               string         `json:"mode"`
	Title              string         `json:"title"`
	Summary            string         `json:"summary"`
	Metadata           map[string]any `json:"metadata"`
}

type appendCharacterInteractionTurnRequest struct {
	BodyTenantID    string         `json:"tenant_id"`
	ActorType       string         `json:"actor_type"`
	ActorID         string         `json:"actor_id"`
	TurnKind        string         `json:"turn_kind"`
	Summary         string         `json:"summary"`
	Action          map[string]any `json:"action"`
	WorldStateDelta map[string]any `json:"world_state_delta"`
	TraceID         string         `json:"trace_id"`
}

type updateCharacterInteractionStatusRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Status       string `json:"status"`
}

type convertCharacterInteractionToChapterDraftRequest struct {
	BodyTenantID      string   `json:"tenant_id"`
	TargetChapterID   string   `json:"target_chapter_id"`
	POVMode           string   `json:"pov_mode"`
	StyleAssetIDs     []string `json:"style_asset_ids"`
	AuthorInstruction string   `json:"author_instruction"`
}

type characterInteractionChapterDraftAdmissionResponse struct {
	InteractionID string `json:"interaction_id"`
	RunID         string `json:"run_id"`
	TraceID       string `json:"trace_id"`
	ProjectID     string `json:"project_id"`
	WorkflowType  string `json:"workflow_type"`
	Status        string `json:"status"`
}

type characterInteractionDetailResponse struct {
	characterconsole.InteractionRecord
	Turns []characterconsole.TurnRecord `json:"turns"`
}

type startWorldlineSessionResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type createWorldlinePreparationRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Goal         string         `json:"goal"`
	AnchorPathID string         `json:"anchor_path_id"`
	Options      map[string]any `json:"options"`
}

type injectWorldlineVariableRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Name         string `json:"name"`
	Description  string `json:"description"`
	ImpactAxis   string `json:"impact_axis"`
	Locked       bool   `json:"locked"`
	Source       string `json:"source"`
}

type createWorldlineSavedPathRequest struct {
	BodyTenantID      string   `json:"tenant_id"`
	Title             string   `json:"title"`
	Summary           string   `json:"summary"`
	SelectedEventIDs  []string `json:"selected_event_ids"`
	WriterInstruction string   `json:"writer_instruction"`
}

type adoptWorldlineEventRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Note         string `json:"note"`
}

type updateWorldlineEventRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Title        string `json:"title"`
	Summary      string `json:"summary"`
	Kind         string `json:"kind"`
}

type createUploadRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Filename     string `json:"filename"`
	MimeType     string `json:"mime_type"`
	SizeBytes    int64  `json:"size_bytes"`
	SHA256       string `json:"sha256"`
	Purpose      string `json:"purpose"`
}

type startSeedRunResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type workflowRunResponse struct {
	RunID        string `json:"run_id"`
	WorkflowType string `json:"workflow_type"`
	ProjectID    string `json:"project_id"`
	Status       string `json:"status"`
	Progress     int    `json:"progress"`
	Message      string `json:"message"`
	ErrorCode    string `json:"error_code"`
	ErrorMessage string `json:"error_message"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type llmResolutionResponse struct {
	ModuleKey     string         `json:"module_key"`
	ChannelID     string         `json:"channel_id"`
	ModelID       string         `json:"model_id"`
	Provider      string         `json:"provider"`
	BaseURL       string         `json:"base_url"`
	SupportsTools bool           `json:"supports_tools"`
	SupportsJSON  bool           `json:"supports_json"`
	Settings      map[string]any `json:"settings"`
}

type upsertLLMModuleBindingRequest struct {
	ChannelID string         `json:"channel_id"`
	ModelID   string         `json:"model_id"`
	Settings  map[string]any `json:"settings"`
}

type createLLMChannelRequest struct {
	Name           string `json:"name"`
	Provider       string `json:"provider"`
	BaseURL        string `json:"base_url"`
	APIKey         string `json:"api_key"`
	MaxConcurrency int    `json:"max_concurrency"`
	Enabled        *bool  `json:"enabled"`
}

type patchLLMChannelRequest struct {
	Name           string `json:"name"`
	BaseURL        string `json:"base_url"`
	APIKey         string `json:"api_key"`
	MaxConcurrency int    `json:"max_concurrency"`
	Enabled        *bool  `json:"enabled"`
}

type listResponse[T any] struct {
	Items []T `json:"items"`
}

type traceExportRequest struct {
	IncludeFull bool `json:"include_full"`
}

func traceExportIncludeFullRequested(body []byte) bool {
	decoder := json.NewDecoder(bytes.NewReader(body))
	token, err := decoder.Token()
	if err != nil {
		return false
	}
	delim, ok := token.(json.Delim)
	if !ok || delim != '{' {
		return false
	}
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return false
		}
		key, ok := token.(string)
		if !ok {
			return false
		}
		if key == "include_full" {
			var includeFull bool
			if err := decoder.Decode(&includeFull); err != nil {
				return false
			}
			if includeFull {
				return true
			}
			continue
		}
		var ignored any
		if err := decoder.Decode(&ignored); err != nil {
			return false
		}
	}
	return false
}

type traceExportResponse struct {
	TraceID     string               `json:"trace_id"`
	ProjectID   string               `json:"project_id"`
	IncludeFull bool                 `json:"include_full"`
	Items       []traces.EventRecord `json:"items"`
}

type assetSearchRequest struct {
	ProjectID string `json:"project_id"`
	Query     string `json:"query"`
}

type adoptAssetRequest struct {
	TargetLifecycle string `json:"target_lifecycle"`
}

type reviewArchiveMemoryRequest struct {
	ProjectID string `json:"project_id"`
}

type createAssetRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Scope        string         `json:"scope"`
	AssetType    string         `json:"asset_type"`
	Category     string         `json:"category"`
	Lifecycle    string         `json:"lifecycle"`
	Title        string         `json:"title"`
	Summary      string         `json:"summary"`
	ContentText  string         `json:"content_text"`
	Payload      map[string]any `json:"payload"`
	Tags         []string       `json:"tags"`
	SourceKind   string         `json:"source_kind"`
	SourceRef    string         `json:"source_ref"`
	Enabled      *bool          `json:"enabled"`
	Pinned       *bool          `json:"pinned"`
}

type patchAssetRequest struct {
	BodyTenantID string          `json:"tenant_id"`
	Scope        *string         `json:"scope"`
	AssetType    *string         `json:"asset_type"`
	Category     *string         `json:"category"`
	Lifecycle    *string         `json:"lifecycle"`
	Title        *string         `json:"title"`
	Summary      *string         `json:"summary"`
	ContentText  *string         `json:"content_text"`
	Payload      *map[string]any `json:"payload"`
	Tags         *[]string       `json:"tags"`
	SourceKind   *string         `json:"source_kind"`
	SourceRef    *string         `json:"source_ref"`
	Enabled      *bool           `json:"enabled"`
	Pinned       *bool           `json:"pinned"`
}

type bulkAssetActionRequest struct {
	BodyTenantID    string         `json:"tenant_id"`
	ProjectID       string         `json:"project_id"`
	Action          string         `json:"action"`
	AssetIDs        []string       `json:"asset_ids"`
	TargetLifecycle string         `json:"target_lifecycle"`
	Category        string         `json:"category"`
	Enabled         *bool          `json:"enabled"`
	Pinned          *bool          `json:"pinned"`
	Payload         map[string]any `json:"payload"`
}

type startAssetIngestionRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	MaterialText string         `json:"material_text"`
	HintType     string         `json:"hint_type"`
	Scope        string         `json:"scope"`
	Options      map[string]any `json:"options"`
}

type startAssetIngestionResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type startStyleExtractionRequest struct {
	BodyTenantID  string         `json:"tenant_id"`
	MaterialText  string         `json:"material_text"`
	SourceAssetID string         `json:"source_asset_id"`
	Scope         string         `json:"scope"`
	Options       map[string]any `json:"options"`
}

type startStyleExtractionResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type startAssetReindexRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Scope        string         `json:"scope"`
	Mode         string         `json:"mode"`
	Options      map[string]any `json:"options"`
}

type startAssetReindexResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type startStoryGraphBuildRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	Mode         string         `json:"mode"`
	Options      map[string]any `json:"options"`
}

type startStoryGraphBuildResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

type startStoryGraphBondGenerationRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	GraphID      string         `json:"graph_id"`
	NodeIDs      []string       `json:"node_ids"`
	Focus        string         `json:"focus"`
	Options      map[string]any `json:"options"`
}

type startStoryGraphBondGenerationResponse struct {
	RunID        string `json:"run_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	Status       string `json:"status"`
}

func NewServer(config Config) *Server {
	authReader := config.AuthReader
	if authReader == nil {
		authReader = auth.NewDisabledReader()
	}
	authorizer := config.Authorizer
	if authorizer == nil {
		authorizer = auth.NewReaderBackedAuthorizer(authReader)
	}
	starter := config.WriterStarter
	if starter == nil {
		starter = workflows.NewLocalWriterStarter()
	}
	reader, ok := starter.(workflows.WriterReader)
	if config.WriterReader != nil {
		reader = config.WriterReader
		ok = true
	}
	if !ok {
		reader = workflows.NewLocalWriterStarter()
	}
	writerEventReader := config.WriterEventReader
	if writerEventReader == nil {
		if eventReader, ok := starter.(workflows.WriterEventReader); ok {
			writerEventReader = eventReader
		} else {
			writerEventReader = workflows.NewDisabledWriterEventReader()
		}
	}
	writerCanceller := config.WriterCanceller
	if writerCanceller == nil {
		writerCanceller = workflows.NewDisabledWriterCanceller()
	}
	draftAdoptionStore := config.DraftAdoptionStore
	if draftAdoptionStore == nil {
		draftAdoptionStore = workflows.NewDisabledDraftAdoptionStore()
	}
	draftReviewStore := config.DraftReviewStore
	if draftReviewStore == nil {
		draftReviewStore = workflows.NewDisabledDraftReviewStore()
	}
	manuscriptReader := config.ManuscriptReader
	if manuscriptReader == nil {
		manuscriptReader = workflows.NewDisabledManuscriptReader()
	}
	workflowReader := config.WorkflowReader
	if workflowReader == nil {
		workflowReader = workflows.NewDisabledWorkflowReader()
	}
	workflowEventReader := config.WorkflowEventReader
	if workflowEventReader == nil {
		workflowEventReader = workflows.NewDisabledWorkflowEventReader()
	}
	workflowCanceller := config.WorkflowCanceller
	if workflowCanceller == nil {
		workflowCanceller = workflows.NewDisabledWorkflowCanceller()
	}
	workflowRetrier := config.WorkflowRetrier
	if workflowRetrier == nil {
		workflowRetrier = workflows.NewDisabledWorkflowRetrier()
	}
	seedStarter := config.SeedStarter
	if seedStarter == nil {
		seedStarter = workflows.NewDisabledSeedRunStarter()
	}
	seedRunReader := config.SeedRunReader
	if seedRunReader == nil {
		seedRunReader = workflows.NewDisabledSeedRunReader()
	}
	projectReadinessReader := config.ProjectReadinessReader
	if projectReadinessReader == nil {
		projectReadinessReader = projectreadiness.NewDisabledReader()
	}
	projectOverviewReader := config.ProjectOverviewReader
	if projectOverviewReader == nil {
		projectOverviewReader = projectoverview.NewDisabledReader()
	}
	helloStarter := config.AgentHelloStarter
	if helloStarter == nil {
		helloStarter = workflows.NewDisabledHelloAgentStarter()
	}
	llmResolver := config.LLMResolver
	if llmResolver == nil {
		llmResolver = llm.NewStaticResolver(nil)
	}
	llmModuleRegistry := config.LLMModuleRegistry
	if llmModuleRegistry == nil {
		llmModuleRegistry = llm.NewStaticModuleRegistry()
	}
	llmBindingStore := config.LLMBindingStore
	if llmBindingStore == nil {
		llmBindingStore = llm.NewDisabledBindingStore()
	}
	llmCatalogReader := config.LLMCatalogReader
	if llmCatalogReader == nil {
		llmCatalogReader = llm.NewDisabledCatalogReader()
	}
	llmChannelStore := config.LLMChannelStore
	if llmChannelStore == nil {
		llmChannelStore = llm.NewDisabledChannelStore()
	}
	llmModelSyncer := config.LLMModelSyncer
	if llmModelSyncer == nil {
		llmModelSyncer = llm.NewDisabledModelSyncer()
	}
	llmSettingsReader := config.LLMSettingsReader
	if llmSettingsReader == nil {
		llmSettingsReader = llm.NewDisabledSettingsReader()
	}
	llmTelemetryReader := config.LLMTelemetryReader
	if llmTelemetryReader == nil {
		llmTelemetryReader = llm.NewDisabledTelemetryReader()
	}
	traceReader := config.TraceReader
	if traceReader == nil {
		traceReader = traces.NewDisabledReader()
	}
	traceAccessChecker := config.TraceAccessChecker
	if traceAccessChecker == nil {
		traceAccessChecker = traces.NewDenyFullTraceAccessChecker()
	}
	traceExportAuditor := config.TraceExportAuditor
	if traceExportAuditor == nil {
		traceExportAuditor = traces.NewDisabledExportAuditor()
	}
	sourceFileStore := config.SourceFileStore
	if sourceFileStore == nil {
		sourceFileStore = sourcefiles.NewDisabledStore()
	}
	sourceFileObjectWriter := config.SourceFileObjectWriter
	if sourceFileObjectWriter == nil {
		sourceFileObjectWriter = sourcefiles.NewDisabledObjectWriter()
	}
	assetReader := config.AssetReader
	if assetReader == nil {
		assetReader = assets.NewDisabledReader()
	}
	archiveMemoryReader := config.ArchiveMemoryReader
	if archiveMemoryReader == nil {
		archiveMemoryReader = assets.NewDisabledArchiveMemoryReader()
	}
	archiveMemoryReviewStore := config.ArchiveMemoryReviewStore
	if archiveMemoryReviewStore == nil {
		archiveMemoryReviewStore = assets.NewDisabledArchiveMemoryReviewStore()
	}
	assetAdoptionStore := config.AssetAdoptionStore
	if assetAdoptionStore == nil {
		assetAdoptionStore = assets.NewDisabledAdoptionStore()
	}
	assetMutationStore := config.AssetMutationStore
	if assetMutationStore == nil {
		assetMutationStore = assets.NewDisabledMutationStore()
	}
	assetBulkActionStore := config.AssetBulkActionStore
	if assetBulkActionStore == nil {
		assetBulkActionStore = assets.NewDisabledBulkActionStore()
	}
	assetIngestionStarter := config.AssetIngestionStarter
	if assetIngestionStarter == nil {
		assetIngestionStarter = workflows.NewDisabledAssetIngestionStarter()
	}
	assetIngestionReader := config.AssetIngestionReader
	if assetIngestionReader == nil {
		assetIngestionReader = workflows.NewDisabledAssetIngestionReader()
	}
	assetReindexStarter := config.AssetReindexStarter
	if assetReindexStarter == nil {
		assetReindexStarter = workflows.NewDisabledAssetReindexStarter()
	}
	styleExtractionStarter := config.StyleExtractionStarter
	if styleExtractionStarter == nil {
		styleExtractionStarter = workflows.NewDisabledStyleExtractionStarter()
	}
	styleExtractionReader := config.StyleExtractionReader
	if styleExtractionReader == nil {
		styleExtractionReader = workflows.NewDisabledStyleExtractionReader()
	}
	storyGraphBuildStarter := config.StoryGraphBuildStarter
	if storyGraphBuildStarter == nil {
		storyGraphBuildStarter = workflows.NewDisabledStoryGraphBuildStarter()
	}
	storyGraphBondGenerationStarter := config.StoryGraphBondGenerationStarter
	if storyGraphBondGenerationStarter == nil {
		storyGraphBondGenerationStarter = workflows.NewDisabledStoryGraphBondGenerationStarter()
	}
	storyGraphReader := config.StoryGraphReader
	if storyGraphReader == nil {
		storyGraphReader = storygraph.NewDisabledReader()
	}
	storyGraphEvidenceAccess := config.StoryGraphEvidenceAccess
	if storyGraphEvidenceAccess == nil {
		storyGraphEvidenceAccess = storygraph.NewDenyEvidenceSnippetAccessChecker()
	}
	worldlineSavedPathReader := config.WorldlineSavedPathReader
	if worldlineSavedPathReader == nil {
		worldlineSavedPathReader = worldline.NewDisabledSavedPathReader()
	}
	worldlineSavedPathStore := config.WorldlineSavedPathStore
	if worldlineSavedPathStore == nil {
		worldlineSavedPathStore = worldline.NewDisabledSavedPathStore()
	}
	worldlineSessionStarter := config.WorldlineSessionStarter
	if worldlineSessionStarter == nil {
		worldlineSessionStarter = worldline.NewDisabledSessionStarter()
	}
	worldlineStepStarter := config.WorldlineStepStarter
	if worldlineStepStarter == nil {
		worldlineStepStarter = worldline.NewDisabledStepStarter()
	}
	worldlineSessionReader := config.WorldlineSessionReader
	if worldlineSessionReader == nil {
		worldlineSessionReader = worldline.NewDisabledSessionReader()
	}
	worldlineTimelineReader := config.WorldlineTimelineReader
	if worldlineTimelineReader == nil {
		worldlineTimelineReader = worldline.NewDisabledTimelineReader()
	}
	worldlineEventReader := config.WorldlineEventReader
	if worldlineEventReader == nil {
		worldlineEventReader = worldline.NewDisabledEventReader()
	}
	worldlineEventAdoptionStore := config.WorldlineEventAdoptionStore
	if worldlineEventAdoptionStore == nil {
		worldlineEventAdoptionStore = worldline.NewDisabledEventAdoptionStore()
	}
	worldlineEventMutationStore := config.WorldlineEventMutationStore
	if worldlineEventMutationStore == nil {
		worldlineEventMutationStore = worldline.NewDisabledEventMutationStore()
	}
	worldlineVariableStore := config.WorldlineVariableStore
	if worldlineVariableStore == nil {
		worldlineVariableStore = worldline.NewDisabledVariableStore()
	}
	worldlinePreparationStore := config.WorldlinePreparationStore
	if worldlinePreparationStore == nil {
		worldlinePreparationStore = worldline.NewDisabledPreparationStore()
	}
	characterConsoleStore := config.CharacterConsoleStore
	if characterConsoleStore == nil {
		characterConsoleStore = characterconsole.NewDisabledStore()
	}
	return &Server{
		sessionAuthSecret:               strings.TrimSpace(config.SessionAuthSecret),
		authReader:                      authReader,
		authorizer:                      authorizer,
		writerStarter:                   starter,
		writerReader:                    reader,
		writerEventReader:               writerEventReader,
		writerCanceller:                 writerCanceller,
		draftAdoptionStore:              draftAdoptionStore,
		draftReviewStore:                draftReviewStore,
		manuscriptReader:                manuscriptReader,
		workflowReader:                  workflowReader,
		workflowEventReader:             workflowEventReader,
		workflowCanceller:               workflowCanceller,
		workflowRetrier:                 workflowRetrier,
		seedStarter:                     seedStarter,
		seedRunReader:                   seedRunReader,
		projectOverviewReader:           projectOverviewReader,
		projectReadinessReader:          projectReadinessReader,
		agentHelloStarter:               helloStarter,
		llmResolver:                     llmResolver,
		llmModuleRegistry:               llmModuleRegistry,
		llmBindingStore:                 llmBindingStore,
		llmCatalogReader:                llmCatalogReader,
		llmChannelStore:                 llmChannelStore,
		llmModelSyncer:                  llmModelSyncer,
		llmSettingsReader:               llmSettingsReader,
		llmTelemetryReader:              llmTelemetryReader,
		traceReader:                     traceReader,
		traceAccessChecker:              traceAccessChecker,
		traceExportAuditor:              traceExportAuditor,
		sourceFileStore:                 sourceFileStore,
		sourceFileObjectWriter:          sourceFileObjectWriter,
		assetReader:                     assetReader,
		archiveMemoryReader:             archiveMemoryReader,
		archiveMemoryReviewStore:        archiveMemoryReviewStore,
		assetAdoptionStore:              assetAdoptionStore,
		assetMutationStore:              assetMutationStore,
		assetBulkActionStore:            assetBulkActionStore,
		assetIngestionStarter:           assetIngestionStarter,
		assetIngestionReader:            assetIngestionReader,
		assetReindexStarter:             assetReindexStarter,
		styleExtractionStarter:          styleExtractionStarter,
		styleExtractionReader:           styleExtractionReader,
		storyGraphBuildStarter:          storyGraphBuildStarter,
		storyGraphBondGenerationStarter: storyGraphBondGenerationStarter,
		storyGraphReader:                storyGraphReader,
		storyGraphEvidenceAccess:        storyGraphEvidenceAccess,
		worldlineSavedPathReader:        worldlineSavedPathReader,
		worldlineSavedPathStore:         worldlineSavedPathStore,
		worldlineSessionStarter:         worldlineSessionStarter,
		worldlineStepStarter:            worldlineStepStarter,
		worldlineSessionReader:          worldlineSessionReader,
		worldlineTimelineReader:         worldlineTimelineReader,
		worldlineEventReader:            worldlineEventReader,
		worldlineEventAdoptionStore:     worldlineEventAdoptionStore,
		worldlineEventMutationStore:     worldlineEventMutationStore,
		worldlineVariableStore:          worldlineVariableStore,
		worldlinePreparationStore:       worldlinePreparationStore,
		characterConsoleStore:           characterConsoleStore,
	}
}

func (s *Server) actorUserID(request *http.Request) string {
	if userID, ok := request.Context().Value(actorUserIDContextKey{}).(string); ok {
		return userID
	}
	userID, _ := s.resolveActorUserID(request)
	return userID
}

func (s *Server) withResolvedActorUserID(response http.ResponseWriter, request *http.Request) (*http.Request, bool) {
	userID, ok := s.resolveActorUserID(request)
	if !ok {
		if hasPresentedActorCredential(request) {
			writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, "user context is required", nil)
			return request, false
		}
		return request, true
	}
	return request.WithContext(context.WithValue(request.Context(), actorUserIDContextKey{}, userID)), true
}

func hasPresentedActorCredential(request *http.Request) bool {
	if len(request.Header.Values("Authorization")) > 0 {
		return true
	}
	if _, err := request.Cookie(sessionCookieName); err == nil {
		return true
	}
	return false
}

func (s *Server) resolveActorUserID(request *http.Request) (string, bool) {
	authorizationValues := request.Header.Values("Authorization")
	if len(authorizationValues) > 0 {
		if len(authorizationValues) != 1 {
			return "", false
		}
		token, ok := bearerToken(authorizationValues[0])
		if !ok {
			return "", false
		}
		return s.verifySessionToken(token)
	}
	if cookie, err := request.Cookie(sessionCookieName); err == nil {
		return s.verifySessionToken(cookie.Value)
	}
	userID := strings.TrimSpace(request.Header.Get("X-User-Id"))
	return userID, userID != ""
}

func bearerToken(authorization string) (string, bool) {
	parts := strings.Fields(authorization)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") {
		return "", false
	}
	token := strings.TrimSpace(parts[1])
	return token, token != ""
}

func (s *Server) verifySessionToken(token string) (string, bool) {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	if secret == "" {
		return "", false
	}
	parts := strings.Split(strings.TrimSpace(token), ":")
	if len(parts) != 3 || parts[0] != "v1" {
		return "", false
	}
	userID := strings.TrimSpace(parts[1])
	if userID == "" {
		return "", false
	}
	signature, err := hex.DecodeString(parts[2])
	if err != nil {
		return "", false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	if _, err := mac.Write([]byte("v1:" + userID)); err != nil {
		return "", false
	}
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return "", false
	}
	return userID, true
}

func isActorSensitiveRoute(request *http.Request) bool {
	path := request.URL.Path
	switch {
	case request.Method == http.MethodGet && path == "/v1/me":
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/workflow-runs/") && strings.HasSuffix(path, "/cancel"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/workflow-runs/") && strings.HasSuffix(path, "/retry"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/seed-runs/") && strings.HasSuffix(path, "/cancel"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/seed-runs/") && strings.HasSuffix(path, "/retry"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/worldline-sessions/") && strings.HasSuffix(path, "/steps"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/worldline-sessions/") && strings.HasSuffix(path, "/variables"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/worldline-sessions/") && strings.HasSuffix(path, "/saved-paths"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/worldline-events/") && strings.HasSuffix(path, "/adoptions"):
		return true
	case request.Method == http.MethodPatch && strings.HasPrefix(path, "/v1/worldline-events/"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/character-interactions/") && strings.HasSuffix(path, "/turns"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/character-interactions/") && strings.HasSuffix(path, "/chapter-drafts"):
		return true
	case request.Method == http.MethodPatch && strings.HasPrefix(path, "/v1/character-interactions/"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/writer-runs/") && strings.HasSuffix(path, "/cancel"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/drafts/") && strings.HasSuffix(path, "/adoptions"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/drafts/") && strings.HasSuffix(path, "/reviews"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/assets/") && strings.HasSuffix(path, "/adoptions"):
		return true
	case request.Method == http.MethodPatch && strings.HasPrefix(path, "/v1/assets/"):
		return true
	case request.Method == http.MethodDelete && strings.HasPrefix(path, "/v1/assets/"):
		return true
	case request.Method == http.MethodPost && path == "/v1/assets/bulk-actions":
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/archive-memories/") && strings.HasSuffix(path, "/adoptions"):
		return true
	case request.Method == http.MethodPost && strings.HasPrefix(path, "/v1/archive-memories/") && strings.HasSuffix(path, "/rejections"):
		return true
	case projectActorSensitiveRoute(request):
		return true
	default:
		return false
	}
}

func projectActorSensitiveRoute(request *http.Request) bool {
	path := request.URL.Path
	if !strings.HasPrefix(path, "/v1/projects/") {
		return false
	}
	switch {
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/overview"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/readiness"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/source-files"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/assets"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/assets/facets"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/worldline/saved-paths"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/worldline-sessions"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/character-interactions"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/story-graph/current"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/views/"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/nodes/") && !strings.HasSuffix(path, "/evidence"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/edges/") && !strings.HasSuffix(path, "/evidence"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/layouts/"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/story-graph/clusters"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/llm/modules"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/llm/module-bindings"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/llm/module-bindings/") && strings.HasSuffix(path, "/resolution"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/llm/channels"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/llm/channels/") && strings.HasSuffix(path, "/models"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/llm/activity"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/llm/usage"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/manuscript"):
		return true
	case request.Method == http.MethodGet && strings.HasSuffix(path, "/manuscript/export"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/seed-runs"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/uploads"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/worldline-sessions"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/worldlines/preparations"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/character-interactions"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/writer-runs"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/agent-runtime/hello-runs"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/assets"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/asset-ingestions"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/style-extractions"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/assets/reindex"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/story-graph/builds"):
		return true
	case request.Method == http.MethodPost && strings.HasSuffix(path, "/story-graph/bond-generations"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/nodes/") && strings.HasSuffix(path, "/evidence"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/story-graph/edges/") && strings.HasSuffix(path, "/evidence"):
		return true
	case request.Method == http.MethodPut && strings.Contains(path, "/llm/module-bindings/"):
		return true
	case request.Method == http.MethodDelete && strings.Contains(path, "/llm/module-bindings/"):
		return true
	case request.Method == http.MethodGet && strings.Contains(path, "/agent-traces/") && strings.HasSuffix(path, "/events"):
		return true
	case request.Method == http.MethodPost && strings.Contains(path, "/agent-traces/") && strings.HasSuffix(path, "/export"):
		return true
	default:
		return false
	}
}

func (s *Server) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if isActorSensitiveRoute(request) {
		var ok bool
		request, ok = s.withResolvedActorUserID(response, request)
		if !ok {
			return
		}
	}

	switch {
	case request.Method == http.MethodGet && request.URL.Path == "/healthz":
		writeJSON(response, http.StatusOK, map[string]string{
			"status":  "ok",
			"service": "mirofish-api",
		})
	case request.Method == http.MethodGet && request.URL.Path == "/v1/me":
		s.handleGetCurrentUser(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/workflow-runs/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListWorkflowRunEvents(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/workflow-runs/") && strings.HasSuffix(request.URL.Path, "/cancel"):
		s.handleCancelWorkflowRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/workflow-runs/") && strings.HasSuffix(request.URL.Path, "/retry"):
		s.handleRetryWorkflowRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/workflow-runs/"):
		s.handleGetWorkflowRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/seed-runs"):
		s.handleStartSeedRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/seed-runs"):
		s.handleListSeedRuns(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/readiness"):
		s.handleGetProjectReadiness(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/overview"):
		s.handleGetProjectOverview(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/manuscript/export"):
		s.handleGetManuscriptExport(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/manuscript"):
		s.handleGetManuscript(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/seed-runs/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListSeedRunEvents(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/seed-runs/") && strings.HasSuffix(request.URL.Path, "/cancel"):
		s.handleCancelSeedRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/seed-runs/") && strings.HasSuffix(request.URL.Path, "/retry"):
		s.handleRetrySeedRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/seed-runs/"):
		s.handleGetSeedRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/uploads"):
		s.handleCreateUpload(response, request)
	case request.Method == http.MethodPut && strings.HasPrefix(request.URL.Path, "/v1/uploads/") && strings.HasSuffix(request.URL.Path, "/object"):
		s.handleUploadSourceObject(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/uploads/") && strings.HasSuffix(request.URL.Path, "/complete"):
		s.handleCompleteUpload(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/source-files"):
		s.handleListSourceFiles(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets/facets"):
		s.handleListAssetFacets(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets"):
		s.handleCreateAsset(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets"):
		s.handleListAssets(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets/reindex"):
		s.handleStartAssetReindex(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/builds"):
		s.handleStartStoryGraphBuild(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/bond-generations"):
		s.handleStartStoryGraphBondGeneration(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/current"):
		s.handleGetStoryGraphCurrent(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/views/"):
		s.handleGetStoryGraphView(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/nodes/") && strings.HasSuffix(request.URL.Path, "/evidence"):
		s.handleGetStoryGraphEvidence(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/edges/") && strings.HasSuffix(request.URL.Path, "/evidence"):
		s.handleGetStoryGraphEvidence(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/layouts/"):
		s.handleGetStoryGraphLayout(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/clusters"):
		s.handleListStoryGraphClusters(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/nodes/"):
		s.handleGetStoryGraphNode(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/story-graph/edges/"):
		s.handleGetStoryGraphEdge(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/asset-ingestions"):
		s.handleStartAssetIngestion(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/asset-ingestions/"):
		s.handleGetAssetIngestion(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/style-extractions"):
		s.handleStartStyleExtraction(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/style-extractions/"):
		s.handleGetStyleExtraction(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/assets/search":
		s.handleSearchAssets(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/assets/bulk-actions":
		s.handleBulkAssetAction(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/archive-assets/") && strings.HasSuffix(request.URL.Path, "/memories"):
		s.handleListArchiveMemories(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/archive-assets/") && strings.HasSuffix(request.URL.Path, "/memory-events"):
		s.handleListArchiveMemoryEvents(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/archive-memories/") && strings.HasSuffix(request.URL.Path, "/adoptions"):
		s.handleAdoptArchiveMemory(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/archive-memories/") && strings.HasSuffix(request.URL.Path, "/rejections"):
		s.handleRejectArchiveMemory(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/assets/") && strings.HasSuffix(request.URL.Path, "/adoptions"):
		s.handleAdoptAsset(response, request)
	case request.Method == http.MethodPatch && strings.HasPrefix(request.URL.Path, "/v1/assets/"):
		s.handlePatchAsset(response, request)
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/v1/assets/"):
		s.handleDeleteAsset(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/assets/"):
		s.handleGetAsset(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline-sessions"):
		s.handleStartWorldlineSession(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline-sessions"):
		s.handleListWorldlineSessions(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldlines/preparations"):
		s.handleCreateWorldlinePreparation(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/worldline-preparations/") && strings.HasSuffix(request.URL.Path, "/agents"):
		s.handleListWorldlinePreparedAgents(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/worldline-preparations/"):
		s.handleGetWorldlinePreparation(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/") && strings.HasSuffix(request.URL.Path, "/timeline"):
		s.handleListWorldlineTimeline(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListWorldlineEvents(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/") && strings.HasSuffix(request.URL.Path, "/steps"):
		s.handleStartWorldlineStep(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/worldline-events/") && strings.HasSuffix(request.URL.Path, "/adoptions"):
		s.handleAdoptWorldlineEvent(response, request)
	case request.Method == http.MethodPatch && strings.HasPrefix(request.URL.Path, "/v1/worldline-events/"):
		s.handleUpdateWorldlineEvent(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/") && strings.HasSuffix(request.URL.Path, "/variables"):
		s.handleInjectWorldlineVariable(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/") && strings.HasSuffix(request.URL.Path, "/saved-paths"):
		s.handleCreateWorldlineSavedPath(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/worldline-sessions/"):
		s.handleGetWorldlineSession(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline/saved-paths"):
		s.handleListWorldlineSavedPaths(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/character-interactions"):
		s.handleCreateCharacterInteraction(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/character-interactions"):
		s.handleListCharacterInteractions(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/turns"):
		s.handleAppendCharacterInteractionTurn(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/turns"):
		s.handleListCharacterInteractionTurns(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleCharacterConsoleRuntimePending(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/chapter-drafts"):
		s.handleConvertCharacterInteractionToChapterDraft(response, request)
	case request.Method == http.MethodPatch && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/"):
		s.handleUpdateCharacterInteractionStatus(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/"):
		s.handleGetCharacterInteraction(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/writer-runs"):
		s.handleStartWriterRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/writer-runs/") && strings.HasSuffix(request.URL.Path, "/cancel"):
		s.handleCancelWriterRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/drafts/") && strings.HasSuffix(request.URL.Path, "/adoptions"):
		s.handleAdoptDraft(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/drafts/") && strings.HasSuffix(request.URL.Path, "/reviews"):
		s.handleStartDraftReview(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/drafts/") && strings.HasSuffix(request.URL.Path, "/reviews"):
		s.handleListDraftReviews(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/writer-runs/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListWriterRunEvents(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/writer-runs/"):
		s.handleGetWriterRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/agent-runtime/hello-runs"):
		s.handleStartHelloAgent(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/llm/module-bindings/") && strings.HasSuffix(request.URL.Path, "/resolution"):
		s.handleResolveLLMModuleBinding(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/modules"):
		s.handleListLLMModules(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/module-bindings"):
		s.handleListLLMModuleBindings(response, request)
	case request.Method == http.MethodPut && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/llm/module-bindings/"):
		s.handleUpsertLLMModuleBinding(response, request)
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/llm/module-bindings/"):
		s.handleDeleteLLMModuleBinding(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/llm/channels/") && strings.HasSuffix(request.URL.Path, "/models"):
		s.handleListLLMModels(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/channels"):
		s.handleListLLMChannels(response, request)
	case request.Method == http.MethodGet && request.URL.Path == "/v1/llm/settings":
		s.handleGetLLMSettings(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/llm/channels":
		s.handleCreateLLMChannel(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/llm/channels/") && strings.HasSuffix(request.URL.Path, "/sync-models"):
		s.handleSyncLLMChannelModels(response, request)
	case request.Method == http.MethodPatch && strings.HasPrefix(request.URL.Path, "/v1/llm/channels/"):
		s.handlePatchLLMChannel(response, request)
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/v1/llm/channels/"):
		s.handleDeleteLLMChannel(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/activity"):
		s.handleListLLMActivity(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/usage"):
		s.handleListLLMUsage(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/agent-traces/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListAgentTraceEvents(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.Contains(request.URL.Path, "/agent-traces/") && strings.HasSuffix(request.URL.Path, "/export"):
		s.handleExportAgentTrace(response, request)
	default:
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "route not found", nil)
	}
}

func (s *Server) handleGetCurrentUser(response http.ResponseWriter, request *http.Request) {
	userID := s.actorUserID(request)
	if userID == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, "user context is required", nil)
		return
	}
	currentUser, err := s.authReader.GetCurrentUser(request.Context(), auth.GetCurrentUserInput{
		UserID:    userID,
		RequestID: requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, currentUser)
}

func (s *Server) authorizeProject(response http.ResponseWriter, request *http.Request, tenantID string, projectID string, permission auth.Permission) bool {
	authorizer := s.authorizer
	if authorizer == nil {
		authorizer = auth.NewReaderBackedAuthorizer(s.authReader)
	}
	err := authorizer.Authorize(request.Context(), auth.AuthorizeInput{
		UserID:     s.actorUserID(request),
		TenantID:   tenantID,
		ProjectID:  projectID,
		Permission: permission,
		RequestID:  requestID(request),
	})
	if err == nil {
		return true
	}
	code := publicAuthCode(auth.ErrorCode(err))
	writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
	return false
}

func (s *Server) authorizeProjectRead(response http.ResponseWriter, request *http.Request, tenantID string, projectID string) bool {
	return s.authorizeProject(response, request, tenantID, projectID, auth.PermissionProjectRead)
}

func (s *Server) handleStartWriterRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPath(request.URL.Path)
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}

	var payload startWriterRunRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid writer run payload", nil)
		return
	}
	moduleKey := moduleKeyFromOptions(payload.Options)
	resolution, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: moduleKey,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	options := sanitizeWorkflowOptions(payload.Options)
	options["module_key"] = moduleKey
	options["llm_resolution"] = workflowLLMResolution(resolution)
	run, err := s.writerStarter.StartWriterRun(request.Context(), workflows.StartWriterRunInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Mode:         strings.TrimSpace(payload.Mode),
		Instruction:  strings.TrimSpace(payload.Instruction),
		Options:      options,
		WorkflowType: workflows.WriterWorkflowType,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startWriterRunResponse{
		RunID:     run.RunID,
		TraceID:   run.TraceID,
		ProjectID: run.ProjectID,
		Status:    run.Status,
	})
}

func (s *Server) handleStartSeedRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "seed-runs")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project seed route not found", nil)
		return
	}
	var payload startSeedRunRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid seed run payload", nil)
		return
	}
	if !sourcefiles.IsConfigured(s.sourceFileStore) {
		writeSourceFileError(response, request, sourcefiles.NewAppError("SOURCE_FILE_BACKEND_UNCONFIGURED", "source file backend is not configured"))
		return
	}
	var sourceFile sourcefiles.ValidatedSourceFile
	validated, err := s.sourceFileStore.ValidateSourceFile(request.Context(), sourcefiles.ValidateInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		UploadID:  strings.TrimSpace(payload.UploadID),
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	sourceFile = validated
	run, err := s.seedStarter.StartSeedRun(request.Context(), workflows.StartSeedRunInput{
		TenantID:        tenantID,
		ProjectID:       projectID,
		UploadID:        strings.TrimSpace(payload.UploadID),
		ActorUserID:     s.actorUserID(request),
		RequestID:       requestID(request),
		SourceFileID:    sourceFile.FileID,
		SourceObjectKey: sourceFile.ObjectKey,
		SourceFilename:  sourceFile.Filename,
		SourceMimeType:  sourceFile.MimeType,
		SourceSizeBytes: sourceFile.SizeBytes,
		SourceSHA256:    sourceFile.SHA256,
		Options:         sanitizeWorkflowOptions(payload.Options),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startSeedRunResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleListSeedRuns(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "seed-runs")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project seed route not found", nil)
		return
	}
	runs, err := s.seedRunReader.ListSeedRuns(request.Context(), workflows.ListSeedRunsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	items := make([]workflowRunResponse, 0, len(runs))
	for _, run := range runs {
		items = append(items, workflowRunToResponse(run))
	}
	writeJSON(response, http.StatusOK, listResponse[workflowRunResponse]{Items: items})
}

func (s *Server) handleGetProjectReadiness(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "readiness")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project readiness route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	snapshot, err := s.projectReadinessReader.GetLatestSnapshot(request.Context(), projectreadiness.GetLatestSnapshotInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeProjectReadinessError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, snapshot)
}

func (s *Server) handleGetProjectOverview(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "overview")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project overview route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionProjectRead) {
		return
	}
	overview, err := s.projectOverviewReader.GetProjectOverview(request.Context(), projectoverview.GetProjectOverviewInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeProjectOverviewError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, overview)
}

func (s *Server) handleGetSeedRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/v1/seed-runs/"))
	if runID == "" || strings.Contains(runID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed run route not found", nil)
		return
	}
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, workflowRunToResponse(run))
}

func (s *Server) handleListSeedRunEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := seedRunEventsPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed run events route not found", nil)
		return
	}
	if _, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	}); err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	events, err := s.workflowEventReader.ListWorkflowEvents(request.Context(), workflows.ListWorkflowEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: afterEventIDFromRequest(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	events = sanitizeWorkflowEvents(events)
	if strings.Contains(request.Header.Get("Accept"), "text/event-stream") {
		writeWorkflowEventsSSE(response, events)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[workflows.WorkflowEvent]{Items: events})
}

func (s *Server) handleCancelSeedRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := seedRunCancelPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed run cancel route not found", nil)
		return
	}
	if _, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	}); err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	cancelled, err := s.workflowCanceller.CancelWorkflowRun(request.Context(), workflows.CancelWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": cancelled.RunID,
		"status": cancelled.Status,
	})
}

func (s *Server) handleRetrySeedRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := seedRunRetryPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed run retry route not found", nil)
		return
	}
	if _, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	}); err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	retried, err := s.workflowRetrier.RetryWorkflowRun(request.Context(), workflows.RetryWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": retried.RunID,
		"status": retried.Status,
	})
}

func (s *Server) handleCreateUpload(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "uploads")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project upload route not found", nil)
		return
	}
	var payload createUploadRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid upload payload", nil)
		return
	}
	if !sourcefiles.IsSupportedSourceMime(payload.MimeType) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid source MIME type", nil)
		return
	}
	record, err := s.sourceFileStore.CreateSourceFile(request.Context(), sourcefiles.CreateInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: s.actorUserID(request),
		Filename:    strings.TrimSpace(payload.Filename),
		MimeType:    strings.TrimSpace(payload.MimeType),
		SizeBytes:   payload.SizeBytes,
		SHA256:      strings.TrimSpace(payload.SHA256),
		Purpose:     strings.TrimSpace(payload.Purpose),
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	writeJSON(response, http.StatusCreated, record)
}

func (s *Server) handleCompleteUpload(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	uploadID := uploadIDFromCompletePath(request.URL.Path)
	if uploadID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "upload complete route not found", nil)
		return
	}
	record, err := s.sourceFileStore.CompleteUpload(request.Context(), sourcefiles.CompleteInput{
		TenantID: tenantID,
		UploadID: uploadID,
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleUploadSourceObject(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	if !sourcefiles.IsObjectWriterConfigured(s.sourceFileObjectWriter) {
		writeSourceFileError(response, request, sourcefiles.NewAppError("SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", "object storage backend is not configured"))
		return
	}
	uploadID := uploadIDFromObjectPath(request.URL.Path)
	if uploadID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "upload object route not found", nil)
		return
	}
	metadata, err := s.sourceFileStore.GetUploadObject(request.Context(), sourcefiles.GetUploadObjectInput{
		TenantID: tenantID,
		UploadID: uploadID,
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	if err := s.sourceFileObjectWriter.WriteObject(request.Context(), metadata, request.Body); err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, map[string]string{
		"upload_id": uploadID,
		"status":    "stored",
	})
}

func (s *Server) handleListSourceFiles(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "source-files")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project source files route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.sourceFileStore.ListSourceFiles(request.Context(), sourcefiles.ListInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[sourcefiles.Record]{Items: items})
}

func (s *Server) handleListAssets(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "assets")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project assets route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.assetReader.ListAssets(request.Context(), assets.ListAssetsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[assets.Record]{Items: items})
}

func (s *Server) handleListAssetFacets(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "assets/facets")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project asset facets route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	facets, err := s.assetReader.ListFacets(request.Context(), assets.ListFacetsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, facets)
}

func (s *Server) handleListWorldlineSavedPaths(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldline/saved-paths")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline saved paths route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.worldlineSavedPathReader.ListSavedPaths(request.Context(), worldline.ListSavedPathsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.SavedPathRecord]{Items: items})
}

func (s *Server) handleStartWorldlineSession(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldline-sessions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline sessions route not found", nil)
		return
	}
	var payload startWorldlineSessionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline session payload", nil)
		return
	}
	run, err := s.worldlineSessionStarter.StartSession(request.Context(), worldline.StartSessionInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Goal:         strings.TrimSpace(payload.Goal),
		AnchorPathID: strings.TrimSpace(payload.AnchorPathID),
		Options:      cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startWorldlineSessionResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleCreateCharacterInteraction(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "character-interactions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project character interactions route not found", nil)
		return
	}
	var payload createCharacterInteractionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction payload", nil)
		return
	}
	record, err := s.characterConsoleStore.CreateInteraction(request.Context(), characterconsole.CreateInteractionInput{
		TenantID:           tenantID,
		ProjectID:          projectID,
		ActorUserID:        s.actorUserID(request),
		RequestID:          requestID(request),
		WorldlineSessionID: strings.TrimSpace(payload.WorldlineSessionID),
		AnchorType:         strings.TrimSpace(payload.AnchorType),
		AnchorID:           strings.TrimSpace(payload.AnchorID),
		POVAgentID:         strings.TrimSpace(payload.POVAgentID),
		Mode:               strings.TrimSpace(payload.Mode),
		Title:              strings.TrimSpace(payload.Title),
		Summary:            strings.TrimSpace(payload.Summary),
		Metadata:           sanitizeAssetPayload(payload.Metadata),
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusCreated, sanitizeCharacterInteractionRecord(record))
}

func (s *Server) handleListCharacterInteractions(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "character-interactions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project character interactions route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.characterConsoleStore.ListInteractions(request.Context(), characterconsole.ListInteractionsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		Status:    strings.TrimSpace(request.URL.Query().Get("status")),
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[characterconsole.InteractionRecord]{Items: sanitizeCharacterInteractionRecords(items)})
}

func (s *Server) handleGetCharacterInteraction(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := strings.TrimPrefix(request.URL.Path, "/v1/character-interactions/")
	interactionID = strings.TrimSpace(strings.Trim(interactionID, "/"))
	if interactionID == "" || strings.Contains(interactionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction route not found", nil)
		return
	}
	record, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	turns, err := s.characterConsoleStore.ListTurns(request.Context(), characterconsole.ListTurnsInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, characterInteractionDetailResponse{
		InteractionRecord: sanitizeCharacterInteractionRecord(record),
		Turns:             sanitizeCharacterInteractionTurns(turns),
	})
}

func (s *Server) handleUpdateCharacterInteractionStatus(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := strings.TrimPrefix(request.URL.Path, "/v1/character-interactions/")
	interactionID = strings.TrimSpace(strings.Trim(interactionID, "/"))
	if interactionID == "" || strings.Contains(interactionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction route not found", nil)
		return
	}
	var payload updateCharacterInteractionStatusRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction status payload", nil)
		return
	}
	record, err := s.characterConsoleStore.UpdateInteractionStatus(request.Context(), characterconsole.UpdateInteractionStatusInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
		ActorUserID:   s.actorUserID(request),
		RequestID:     requestID(request),
		Status:        strings.TrimSpace(payload.Status),
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, sanitizeCharacterInteractionRecord(record))
}

func (s *Server) handleAppendCharacterInteractionTurn(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "turns")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction turn route not found", nil)
		return
	}
	var payload appendCharacterInteractionTurnRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction turn payload", nil)
		return
	}
	if _, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	}); err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	record, err := s.characterConsoleStore.AppendTurn(request.Context(), characterconsole.AppendTurnInput{
		TenantID:        tenantID,
		InteractionID:   interactionID,
		ActorUserID:     s.actorUserID(request),
		RequestID:       requestID(request),
		ActorType:       strings.TrimSpace(payload.ActorType),
		ActorID:         strings.TrimSpace(payload.ActorID),
		TurnKind:        strings.TrimSpace(payload.TurnKind),
		Summary:         strings.TrimSpace(payload.Summary),
		Action:          sanitizeAssetPayload(payload.Action),
		WorldStateDelta: sanitizeAssetPayload(payload.WorldStateDelta),
		TraceID:         strings.TrimSpace(payload.TraceID),
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusCreated, sanitizeCharacterInteractionTurn(record))
}

func (s *Server) handleListCharacterInteractionTurns(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "turns")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction turn route not found", nil)
		return
	}
	if _, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	}); err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	items, err := s.characterConsoleStore.ListTurns(request.Context(), characterconsole.ListTurnsInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[characterconsole.TurnRecord]{Items: sanitizeCharacterInteractionTurns(items)})
}

func (s *Server) handleCharacterConsoleRuntimePending(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "events")
	if interactionID == "" {
		interactionID = characterInteractionNestedPathPart(request.URL.Path, "chapter-drafts")
	}
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction runtime route not found", nil)
		return
	}
	if _, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	}); err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeError(response, request, http.StatusServiceUnavailable, "CHARACTER_CONSOLE_RUNTIME_PENDING", "character console runtime is pending", nil)
}

func (s *Server) handleConvertCharacterInteractionToChapterDraft(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "chapter-drafts")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction chapter draft route not found", nil)
		return
	}
	var payload convertCharacterInteractionToChapterDraftRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction chapter draft payload", nil)
		return
	}
	interaction, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	turns, err := s.characterConsoleStore.ListTurns(request.Context(), characterconsole.ListTurnsInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	interaction = sanitizeCharacterInteractionRecord(interaction)
	turns = sanitizeCharacterInteractionTurns(turns)
	turns = characterInteractionTurnsWithSummaryMaterial(turns)
	if len(turns) == 0 {
		writeError(response, request, http.StatusConflict, "CHARACTER_INTERACTION_TURNS_REQUIRED", "character interaction needs at least one public turn summary before writer handoff", nil)
		return
	}
	moduleKey := "writer_composer"
	resolution, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: interaction.ProjectID,
		ModuleKey: moduleKey,
	})
	if err != nil {
		writeCharacterConsoleLLMError(response, request, err)
		return
	}
	options := characterInteractionChapterDraftOptions(interaction, turns, payload, moduleKey, resolution)
	run, err := s.writerStarter.StartWriterRun(request.Context(), workflows.StartWriterRunInput{
		TenantID:     tenantID,
		ProjectID:    interaction.ProjectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Mode:         "draft",
		Instruction:  characterInteractionChapterDraftInstruction(interaction, turns, payload),
		Options:      options,
		WorkflowType: workflows.WriterWorkflowType,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, characterConsoleWriterPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, characterInteractionChapterDraftAdmissionResponse{
		InteractionID: interaction.InteractionID,
		RunID:         run.RunID,
		TraceID:       run.TraceID,
		ProjectID:     run.ProjectID,
		WorkflowType:  workflows.WriterWorkflowType,
		Status:        run.Status,
	})
}

func (s *Server) handleStartWorldlineStep(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSuffix(sessionID, "/steps")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline step route not found", nil)
		return
	}
	var payload startWorldlineStepRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline step payload", nil)
		return
	}
	run, err := s.worldlineStepStarter.StartStep(request.Context(), worldline.StartStepInput{
		TenantID:    tenantID,
		SessionID:   sessionID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Mode:        strings.TrimSpace(payload.Mode),
		Options:     cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, run)
}

func (s *Server) handleCreateWorldlinePreparation(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldlines/preparations")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline preparations route not found", nil)
		return
	}
	var payload createWorldlinePreparationRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline preparation payload", nil)
		return
	}
	record, err := s.worldlinePreparationStore.CreatePreparation(request.Context(), worldline.CreatePreparationInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Goal:         strings.TrimSpace(payload.Goal),
		AnchorPathID: strings.TrimSpace(payload.AnchorPathID),
		Options:      cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleListWorldlineSessions(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "worldline-sessions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project worldline sessions route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.worldlineSessionReader.ListSessions(request.Context(), worldline.ListSessionsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.SessionRecord]{Items: items})
}

func (s *Server) handleGetWorldlineSession(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline session route not found", nil)
		return
	}
	record, err := s.worldlineSessionReader.GetSession(request.Context(), worldline.GetSessionInput{
		TenantID:  tenantID,
		SessionID: sessionID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleListWorldlineTimeline(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSuffix(sessionID, "/timeline")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline timeline route not found", nil)
		return
	}
	items, err := s.worldlineTimelineReader.ListTimeline(request.Context(), worldline.ListTimelineInput{
		TenantID:  tenantID,
		SessionID: sessionID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.TimelineEventRecord]{Items: items})
}

func (s *Server) handleListWorldlineEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSuffix(sessionID, "/events")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event route not found", nil)
		return
	}
	items, err := s.worldlineEventReader.ListEvents(request.Context(), worldline.ListEventsInput{
		TenantID:  tenantID,
		SessionID: sessionID,
		Status:    strings.TrimSpace(request.URL.Query().Get("status")),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.EventRecord]{Items: items})
}

func (s *Server) handleAdoptWorldlineEvent(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	eventID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-events/")
	eventID = strings.TrimSuffix(eventID, "/adoptions")
	eventID = strings.TrimSpace(strings.Trim(eventID, "/"))
	if eventID == "" || strings.Contains(eventID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event adoption route not found", nil)
		return
	}
	var payload adoptWorldlineEventRequest
	decoder := json.NewDecoder(request.Body)
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline event adoption payload", nil)
		return
	}
	record, err := s.worldlineEventAdoptionStore.AdoptEvent(request.Context(), worldline.AdoptEventInput{
		TenantID:    tenantID,
		EventID:     eventID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Note:        strings.TrimSpace(payload.Note),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleUpdateWorldlineEvent(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	eventID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-events/")
	eventID = strings.TrimSpace(strings.Trim(eventID, "/"))
	if eventID == "" || strings.Contains(eventID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event mutation route not found", nil)
		return
	}
	var payload updateWorldlineEventRequest
	decoder := json.NewDecoder(request.Body)
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline event mutation payload", nil)
		return
	}
	record, err := s.worldlineEventMutationStore.UpdateEvent(request.Context(), worldline.UpdateEventInput{
		TenantID:    tenantID,
		EventID:     eventID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Title:       strings.TrimSpace(payload.Title),
		Summary:     strings.TrimSpace(payload.Summary),
		Kind:        strings.TrimSpace(payload.Kind),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleInjectWorldlineVariable(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSuffix(sessionID, "/variables")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline variable route not found", nil)
		return
	}
	var payload injectWorldlineVariableRequest
	decoder := json.NewDecoder(request.Body)
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline variable payload", nil)
		return
	}
	record, err := s.worldlineVariableStore.InjectVariable(request.Context(), worldline.InjectVariableInput{
		TenantID:    tenantID,
		SessionID:   sessionID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Name:        strings.TrimSpace(payload.Name),
		Description: strings.TrimSpace(payload.Description),
		ImpactAxis:  strings.TrimSpace(payload.ImpactAxis),
		Locked:      payload.Locked,
		Source:      strings.TrimSpace(payload.Source),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleCreateWorldlineSavedPath(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-sessions/")
	sessionID = strings.TrimSuffix(sessionID, "/saved-paths")
	sessionID = strings.TrimSpace(strings.Trim(sessionID, "/"))
	if sessionID == "" || strings.Contains(sessionID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline saved path route not found", nil)
		return
	}
	var payload createWorldlineSavedPathRequest
	decoder := json.NewDecoder(request.Body)
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline saved path payload", nil)
		return
	}
	record, err := s.worldlineSavedPathStore.CreateSavedPath(request.Context(), worldline.CreateSavedPathInput{
		TenantID:          tenantID,
		SessionID:         sessionID,
		ActorUserID:       s.actorUserID(request),
		RequestID:         requestID(request),
		Title:             strings.TrimSpace(payload.Title),
		Summary:           strings.TrimSpace(payload.Summary),
		SelectedEventIDs:  trimStringSlice(payload.SelectedEventIDs),
		WriterInstruction: strings.TrimSpace(payload.WriterInstruction),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, record)
}

func (s *Server) handleGetWorldlinePreparation(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	prepareID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-preparations/")
	prepareID = strings.TrimSpace(strings.Trim(prepareID, "/"))
	if prepareID == "" || strings.Contains(prepareID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline preparation route not found", nil)
		return
	}
	record, err := s.worldlinePreparationStore.GetPreparation(request.Context(), worldline.GetPreparationInput{
		TenantID:  tenantID,
		PrepareID: prepareID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleListWorldlinePreparedAgents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	prepareID := strings.TrimPrefix(request.URL.Path, "/v1/worldline-preparations/")
	prepareID = strings.TrimSuffix(prepareID, "/agents")
	prepareID = strings.TrimSpace(strings.Trim(prepareID, "/"))
	if prepareID == "" || strings.Contains(prepareID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline prepared agents route not found", nil)
		return
	}
	items, err := s.worldlinePreparationStore.ListPreparedAgents(request.Context(), worldline.ListPreparedAgentsInput{
		TenantID:  tenantID,
		PrepareID: prepareID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(worldline.ErrorCode(err)), worldline.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.PreparedAgentRecord]{Items: items})
}

func (s *Server) handleCreateAsset(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "assets")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project asset route not found", nil)
		return
	}
	var payload createAssetRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset create payload", nil)
		return
	}
	record, err := s.assetMutationStore.CreateAsset(request.Context(), assets.CreateAssetInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		BodyTenantID: strings.TrimSpace(payload.BodyTenantID),
		ActorID:      s.actorUserID(request),
		RequestID:    requestID(request),
		Scope:        strings.TrimSpace(payload.Scope),
		AssetType:    strings.TrimSpace(payload.AssetType),
		Category:     strings.TrimSpace(payload.Category),
		Lifecycle:    strings.TrimSpace(payload.Lifecycle),
		Title:        strings.TrimSpace(payload.Title),
		Summary:      strings.TrimSpace(payload.Summary),
		ContentText:  payload.ContentText,
		Payload:      sanitizeAssetPayload(payload.Payload),
		Tags:         sanitizeAssetTags(payload.Tags),
		SourceKind:   strings.TrimSpace(payload.SourceKind),
		SourceRef:    strings.TrimSpace(payload.SourceRef),
		Enabled:      payload.Enabled,
		Pinned:       payload.Pinned,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusCreated, record)
}

func (s *Server) handleSearchAssets(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	var payload assetSearchRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset search payload", nil)
		return
	}
	items, err := s.assetReader.SearchAssets(request.Context(), assets.SearchAssetsInput{
		TenantID:  tenantID,
		ProjectID: strings.TrimSpace(payload.ProjectID),
		Query:     strings.TrimSpace(payload.Query),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[assets.SearchRecord]{Items: items})
}

func (s *Server) handleListArchiveMemories(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := archiveAssetPathPart(request.URL.Path, "memories")
	if assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "archive asset memories route not found", nil)
		return
	}
	items, err := s.archiveMemoryReader.ListMemories(request.Context(), assets.ListArchiveMemoriesInput{
		TenantID:  tenantID,
		ProjectID: strings.TrimSpace(request.URL.Query().Get("project_id")),
		AssetID:   assetID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[assets.ArchiveMemoryRecord]{Items: items})
}

func (s *Server) handleListArchiveMemoryEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := archiveAssetPathPart(request.URL.Path, "memory-events")
	if assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "archive asset memory events route not found", nil)
		return
	}
	items, err := s.archiveMemoryReader.ListMemoryEvents(request.Context(), assets.ListArchiveMemoryEventsInput{
		TenantID:  tenantID,
		ProjectID: strings.TrimSpace(request.URL.Query().Get("project_id")),
		AssetID:   assetID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[assets.ArchiveMemoryEventRecord]{Items: items})
}

func (s *Server) handleAdoptArchiveMemory(response http.ResponseWriter, request *http.Request) {
	s.handleReviewArchiveMemory(response, request, "adoptions")
}

func (s *Server) handleRejectArchiveMemory(response http.ResponseWriter, request *http.Request) {
	s.handleReviewArchiveMemory(response, request, "rejections")
}

func (s *Server) handleReviewArchiveMemory(response http.ResponseWriter, request *http.Request, action string) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	memoryID := archiveMemoryReviewPathPart(request.URL.Path, action)
	if memoryID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "archive memory review route not found", nil)
		return
	}
	var payload reviewArchiveMemoryRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid archive memory review payload", nil)
		return
	}
	input := assets.ArchiveMemoryReviewInput{
		TenantID:  tenantID,
		ProjectID: strings.TrimSpace(payload.ProjectID),
		MemoryID:  memoryID,
		ActorID:   s.actorUserID(request),
		RequestID: requestID(request),
	}
	var (
		record assets.ArchiveMemoryRecord
		err    error
	)
	if action == "adoptions" {
		record, err = s.archiveMemoryReviewStore.AdoptMemory(request.Context(), input)
	} else {
		record, err = s.archiveMemoryReviewStore.RejectMemory(request.Context(), input)
	}
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleBulkAssetAction(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	var payload bulkAssetActionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset bulk action payload", nil)
		return
	}
	projectID := strings.TrimSpace(payload.ProjectID)
	action := strings.TrimSpace(payload.Action)
	assetIDs := sanitizedBulkAssetIDs(payload.AssetIDs)
	if projectID == "" || action == "" || len(assetIDs) == 0 {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "project_id, action, and asset_ids are required", nil)
		return
	}
	result, err := s.assetBulkActionStore.ApplyBulkAction(request.Context(), assets.BulkActionInput{
		TenantID:        tenantID,
		ProjectID:       projectID,
		BodyTenantID:    strings.TrimSpace(payload.BodyTenantID),
		ActorID:         s.actorUserID(request),
		RequestID:       requestID(request),
		Action:          action,
		AssetIDs:        assetIDs,
		TargetLifecycle: strings.TrimSpace(payload.TargetLifecycle),
		Category:        strings.TrimSpace(payload.Category),
		Enabled:         payload.Enabled,
		Pinned:          payload.Pinned,
		Payload:         sanitizeAssetPayload(payload.Payload),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, result)
}

func (s *Server) handleStartAssetIngestion(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "asset-ingestions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project asset ingestion route not found", nil)
		return
	}
	var payload startAssetIngestionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset ingestion payload", nil)
		return
	}
	run, err := s.assetIngestionStarter.StartAssetIngestion(request.Context(), workflows.StartAssetIngestionInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		MaterialText: strings.TrimSpace(payload.MaterialText),
		HintType:     strings.TrimSpace(payload.HintType),
		Scope:        strings.TrimSpace(payload.Scope),
		Options:      cloneOptions(payload.Options),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startAssetIngestionResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleGetAssetIngestion(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := assetIngestionRunPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "asset ingestion route not found", nil)
		return
	}
	run, err := s.assetIngestionReader.GetAssetIngestion(request.Context(), workflows.GetAssetIngestionInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, workflowRunToResponse(run))
}

func (s *Server) handleStartStyleExtraction(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "style-extractions")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project style extraction route not found", nil)
		return
	}
	var payload startStyleExtractionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid style extraction payload", nil)
		return
	}
	run, err := s.styleExtractionStarter.StartStyleExtraction(request.Context(), workflows.StartStyleExtractionInput{
		TenantID:      tenantID,
		ProjectID:     projectID,
		ActorUserID:   s.actorUserID(request),
		RequestID:     requestID(request),
		MaterialText:  strings.TrimSpace(payload.MaterialText),
		SourceAssetID: strings.TrimSpace(payload.SourceAssetID),
		Scope:         strings.TrimSpace(payload.Scope),
		Options:       cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startStyleExtractionResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleGetStyleExtraction(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := styleExtractionRunPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "style extraction route not found", nil)
		return
	}
	run, err := s.styleExtractionReader.GetStyleExtraction(request.Context(), workflows.GetStyleExtractionInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, workflowRunToResponse(run))
}

func (s *Server) handleStartAssetReindex(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "assets/reindex")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project asset reindex route not found", nil)
		return
	}
	var payload startAssetReindexRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset reindex payload", nil)
		return
	}
	run, err := s.assetReindexStarter.StartAssetReindex(request.Context(), workflows.StartAssetReindexInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Scope:       workflows.NormalizeAssetReindexScope(payload.Scope),
		Mode:        workflows.NormalizeAssetReindexMode(payload.Mode),
		Options:     cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startAssetReindexResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleStartStoryGraphBuild(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "story-graph/builds")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph build route not found", nil)
		return
	}
	var payload startStoryGraphBuildRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid story graph build payload", nil)
		return
	}
	run, err := s.storyGraphBuildStarter.StartStoryGraphBuild(request.Context(), workflows.StartStoryGraphBuildInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		Mode:        workflows.NormalizeStoryGraphBuildMode(payload.Mode),
		Options:     cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startStoryGraphBuildResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleStartStoryGraphBondGeneration(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "story-graph/bond-generations")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph bond generation route not found", nil)
		return
	}
	var payload startStoryGraphBondGenerationRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid story graph bond generation payload", nil)
		return
	}
	run, err := s.storyGraphBondGenerationStarter.StartStoryGraphBondGeneration(request.Context(), workflows.StartStoryGraphBondGenerationInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		GraphID:     strings.TrimSpace(payload.GraphID),
		NodeIDs:     workflows.NormalizeStoryGraphBondNodeIDs(payload.NodeIDs),
		Focus:       strings.TrimSpace(payload.Focus),
		Options:     cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startStoryGraphBondGenerationResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleGetStoryGraphCurrent(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "story-graph/current")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	current, err := s.storyGraphReader.GetCurrentSnapshot(request.Context(), storygraph.GetCurrentInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, current)
}

func (s *Server) handleGetStoryGraphView(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, viewID := storyGraphPathParts(request.URL.Path, "views")
	if projectID == "" || viewID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph view route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	limit := 0
	if rawLimit := strings.TrimSpace(request.URL.Query().Get("limit")); rawLimit != "" {
		parsedLimit, err := strconv.Atoi(rawLimit)
		if err != nil {
			writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "story graph limit must be an integer", nil)
			return
		}
		limit = parsedLimit
	}
	view, err := s.storyGraphReader.GetView(request.Context(), storygraph.GetViewInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ViewID:       viewID,
		Types:        commaList(request.URL.Query().Get("types")),
		Limit:        limit,
		IncludeEdges: queryBool(request.URL.Query().Get("include_edges")),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, view)
}

func (s *Server) handleGetStoryGraphEvidence(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, ownerType, ownerID := storyGraphEvidencePathParts(request.URL.Path)
	if projectID == "" || ownerType == "" || ownerID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph evidence route not found", nil)
		return
	}
	limit, ok := queryLimit(response, request, "story graph evidence limit must be an integer")
	if !ok {
		return
	}
	includeFull := strings.EqualFold(strings.TrimSpace(request.URL.Query().Get("include_full")), "true")
	if includeFull {
		err := s.storyGraphEvidenceAccess.CanViewEvidenceSnippets(request.Context(), storygraph.EvidenceAccessInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			OwnerType: ownerType,
			OwnerID:   ownerID,
			ActorID:   s.actorUserID(request),
		})
		if err != nil {
			writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
			return
		}
	}
	evidence, err := s.storyGraphReader.GetEvidence(request.Context(), storygraph.GetEvidenceInput{
		TenantID:       tenantID,
		ProjectID:      projectID,
		OwnerType:      ownerType,
		OwnerID:        ownerID,
		Limit:          limit,
		IncludeSnippet: includeFull,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, evidence)
}

func (s *Server) handleGetStoryGraphLayout(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, viewID := storyGraphPathParts(request.URL.Path, "layouts")
	if projectID == "" || viewID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph layout route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	layout, err := s.storyGraphReader.GetLayout(request.Context(), storygraph.GetLayoutInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ViewID:    viewID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, layout)
}

func (s *Server) handleListStoryGraphClusters(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "story-graph/clusters")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph clusters route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	limit, ok := queryLimit(response, request, "story graph cluster limit must be an integer")
	if !ok {
		return
	}
	clusters, err := s.storyGraphReader.ListClusters(request.Context(), storygraph.ListClustersInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		Limit:     limit,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, clusters)
}

func (s *Server) handleGetStoryGraphNode(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, nodeID := storyGraphPathParts(request.URL.Path, "nodes")
	if projectID == "" || nodeID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph node route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	node, err := s.storyGraphReader.GetNode(request.Context(), storygraph.GetNodeInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		NodeID:    nodeID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, node)
}

func (s *Server) handleGetStoryGraphEdge(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, edgeID := storyGraphPathParts(request.URL.Path, "edges")
	if projectID == "" || edgeID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph edge route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	edge, err := s.storyGraphReader.GetEdge(request.Context(), storygraph.GetEdgeInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		EdgeID:    edgeID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(storygraph.ErrorCode(err)), storygraph.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, edge)
}

func (s *Server) handleGetAsset(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/v1/assets/"))
	if assetID == "" || strings.Contains(assetID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "asset route not found", nil)
		return
	}
	record, err := s.assetReader.GetAsset(request.Context(), assets.GetAssetInput{
		TenantID: tenantID,
		AssetID:  assetID,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleAdoptAsset(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := assetAdoptionPathPart(request.URL.Path)
	if assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "asset adoption route not found", nil)
		return
	}
	var payload adoptAssetRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset adoption payload", nil)
		return
	}
	record, err := s.assetAdoptionStore.AdoptAsset(request.Context(), assets.AdoptAssetInput{
		TenantID:        tenantID,
		AssetID:         assetID,
		ActorID:         s.actorUserID(request),
		RequestID:       requestID(request),
		TargetLifecycle: strings.TrimSpace(payload.TargetLifecycle),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handlePatchAsset(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := assetPathPart(request.URL.Path)
	if assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "asset route not found", nil)
		return
	}
	var payload patchAssetRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset patch payload", nil)
		return
	}
	var sanitizedPayload *map[string]any
	if payload.Payload != nil {
		value := sanitizeAssetPayload(*payload.Payload)
		sanitizedPayload = &value
	}
	var sanitizedTags *[]string
	if payload.Tags != nil {
		value := sanitizeAssetTags(*payload.Tags)
		sanitizedTags = &value
	}
	record, err := s.assetMutationStore.PatchAsset(request.Context(), assets.PatchAssetInput{
		TenantID:     tenantID,
		AssetID:      assetID,
		BodyTenantID: strings.TrimSpace(payload.BodyTenantID),
		ActorID:      s.actorUserID(request),
		RequestID:    requestID(request),
		Scope:        trimOptionalString(payload.Scope),
		AssetType:    trimOptionalString(payload.AssetType),
		Category:     trimOptionalString(payload.Category),
		Lifecycle:    trimOptionalString(payload.Lifecycle),
		Title:        trimOptionalString(payload.Title),
		Summary:      trimOptionalString(payload.Summary),
		ContentText:  payload.ContentText,
		Payload:      sanitizedPayload,
		Tags:         sanitizedTags,
		SourceKind:   trimOptionalString(payload.SourceKind),
		SourceRef:    trimOptionalString(payload.SourceRef),
		Enabled:      payload.Enabled,
		Pinned:       payload.Pinned,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func (s *Server) handleDeleteAsset(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	assetID := assetPathPart(request.URL.Path)
	if assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "asset route not found", nil)
		return
	}
	result, err := s.assetMutationStore.DeleteAsset(request.Context(), assets.DeleteAssetInput{
		TenantID:  tenantID,
		AssetID:   assetID,
		ActorID:   s.actorUserID(request),
		RequestID: requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForAppCode(assets.ErrorCode(err)), assets.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, result)
}

func (s *Server) handleResolveLLMModuleBinding(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, moduleKey := llmResolutionPathParts(request.URL.Path)
	if projectID == "" || moduleKey == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm module binding route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	resolution, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: moduleKey,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, sanitizedLLMResolution(resolution))
}

func (s *Server) handleListLLMModules(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/modules")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm modules route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmModuleRegistry.ListModules(request.Context(), llm.ModuleRegistryInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.ModuleRecord]{Items: items})
}

func (s *Server) handleListLLMModuleBindings(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/module-bindings")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm module bindings route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmBindingStore.ListModuleBindings(request.Context(), llm.ListModuleBindingsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.ModuleBindingRecord]{Items: items})
}

func (s *Server) handleUpsertLLMModuleBinding(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, moduleKey := llmModuleBindingPathParts(request.URL.Path)
	if projectID == "" || moduleKey == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm module binding route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionLLMModuleBindingManage) {
		return
	}
	var payload upsertLLMModuleBindingRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid llm module binding payload", nil)
		return
	}
	if payload.Settings == nil {
		payload.Settings = map[string]any{}
	}
	binding, err := s.llmBindingStore.UpsertProjectModuleBinding(request.Context(), llm.UpsertProjectModuleBindingInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ActorID:   s.actorUserID(request),
		ModuleKey: moduleKey,
		ChannelID: strings.TrimSpace(payload.ChannelID),
		ModelID:   strings.TrimSpace(payload.ModelID),
		Settings:  payload.Settings,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, binding)
}

func (s *Server) handleDeleteLLMModuleBinding(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, moduleKey := llmModuleBindingPathParts(request.URL.Path)
	if projectID == "" || moduleKey == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm module binding route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionLLMModuleBindingManage) {
		return
	}
	binding, err := s.llmBindingStore.DeleteProjectModuleBinding(request.Context(), llm.DeleteProjectModuleBindingInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: moduleKey,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, binding)
}

func (s *Server) handleListLLMChannels(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/channels")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channels route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmCatalogReader.ListChannels(request.Context(), llm.CatalogQueryInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.ChannelRecord]{Items: items})
}

func (s *Server) handleListLLMModels(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, channelID := llmChannelModelsPathParts(request.URL.Path)
	if projectID == "" || channelID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channel models route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmCatalogReader.ListModels(request.Context(), llm.ModelQueryInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ChannelID: channelID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.ModelRecord]{Items: items})
}

func (s *Server) handleGetLLMSettings(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	settings, err := s.llmSettingsReader.GetSettings(request.Context(), llm.SettingsInput{
		TenantID: tenantID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, settings)
}

func (s *Server) handleCreateLLMChannel(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	var payload createLLMChannelRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid llm channel payload", nil)
		return
	}
	enabled := true
	if payload.Enabled != nil {
		enabled = *payload.Enabled
	}
	channel, err := s.llmChannelStore.CreateChannel(request.Context(), llm.CreateChannelInput{
		TenantID:       tenantID,
		Name:           strings.TrimSpace(payload.Name),
		Provider:       strings.TrimSpace(payload.Provider),
		BaseURL:        strings.TrimSpace(payload.BaseURL),
		APIKey:         strings.TrimSpace(payload.APIKey),
		MaxConcurrency: payload.MaxConcurrency,
		Enabled:        enabled,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusCreated, channel)
}

func (s *Server) handlePatchLLMChannel(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	channelID := llmChannelIDFromPath(request.URL.Path)
	if channelID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channel route not found", nil)
		return
	}
	var payload patchLLMChannelRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid llm channel payload", nil)
		return
	}
	enabled := true
	if payload.Enabled != nil {
		enabled = *payload.Enabled
	}
	channel, err := s.llmChannelStore.UpdateChannel(request.Context(), llm.UpdateChannelInput{
		TenantID:       tenantID,
		ChannelID:      channelID,
		Name:           strings.TrimSpace(payload.Name),
		BaseURL:        strings.TrimSpace(payload.BaseURL),
		APIKey:         strings.TrimSpace(payload.APIKey),
		MaxConcurrency: payload.MaxConcurrency,
		Enabled:        enabled,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, channel)
}

func (s *Server) handleDeleteLLMChannel(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	channelID := llmChannelIDFromPath(request.URL.Path)
	if channelID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channel route not found", nil)
		return
	}
	channel, err := s.llmChannelStore.DeleteChannel(request.Context(), llm.DeleteChannelInput{
		TenantID:  tenantID,
		ChannelID: channelID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, channel)
}

func (s *Server) handleSyncLLMChannelModels(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	channelID := llmChannelSyncPathPart(request.URL.Path)
	if channelID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channel model sync route not found", nil)
		return
	}
	result, err := s.llmModelSyncer.SyncModels(request.Context(), llm.ModelSyncInput{
		TenantID:  tenantID,
		ChannelID: channelID,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, result)
}

func (s *Server) handleListLLMActivity(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/activity")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm activity route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmTelemetryReader.ListActivity(request.Context(), llm.ActivityQueryInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		RunID:     strings.TrimSpace(request.URL.Query().Get("run_id")),
		ModuleKey: strings.TrimSpace(request.URL.Query().Get("module_key")),
	})
	if err != nil {
		writeLLMTelemetryError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.ActivityRecord]{Items: llm.SanitizeActivityRecords(items)})
}

func (s *Server) handleListLLMUsage(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "llm/usage")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm usage route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.llmTelemetryReader.ListUsage(request.Context(), llm.UsageQueryInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		RunID:     strings.TrimSpace(request.URL.Query().Get("run_id")),
		ModuleKey: strings.TrimSpace(request.URL.Query().Get("module_key")),
	})
	if err != nil {
		writeLLMTelemetryError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[llm.UsageRecord]{Items: items})
}

func writeLLMTelemetryError(response http.ResponseWriter, request *http.Request, err error) {
	writeLLMError(response, request, err)
}

func writeProjectReadinessError(response http.ResponseWriter, request *http.Request, err error) {
	code := projectreadiness.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, projectReadinessPublicErrorMessage(code), nil)
}

func writeProjectOverviewError(response http.ResponseWriter, request *http.Request, err error) {
	code := projectoverview.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, projectOverviewPublicErrorMessage(code), nil)
}

func projectOverviewPublicErrorMessage(code string) string {
	switch code {
	case "PROJECT_OVERVIEW_BACKEND_UNCONFIGURED":
		return "project overview reader is not configured"
	case "PROJECT_OVERVIEW_QUERY_FAILED":
		return "project overview query failed"
	case "NOT_FOUND":
		return "project overview not found"
	case "VALIDATION_FAILED":
		return "tenant_id and project_id are required"
	default:
		return "project overview query failed"
	}
}

func projectReadinessPublicErrorMessage(code string) string {
	switch code {
	case "PROJECT_READINESS_BACKEND_UNCONFIGURED":
		return "project readiness reader is not configured"
	case "PROJECT_READINESS_QUERY_FAILED":
		return "project readiness query failed"
	case "NOT_FOUND":
		return "project readiness snapshot not found"
	case "VALIDATION_FAILED":
		return "tenant_id and project_id are required"
	default:
		return "project readiness query failed"
	}
}

func writeLLMError(response http.ResponseWriter, request *http.Request, err error) {
	code := llm.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, llmPublicErrorMessage(code), nil)
}

func llmPublicErrorMessage(code string) string {
	switch code {
	case "LLM_ACTIVITY_BACKEND_UNCONFIGURED":
		return "LLM activity backend is not configured"
	case "LLM_ACTIVITY_QUERY_FAILED":
		return "LLM activity query failed"
	case "LLM_BINDING_BACKEND_UNCONFIGURED":
		return "LLM binding backend is not configured"
	case "LLM_BINDING_QUERY_FAILED":
		return "LLM module binding query failed"
	case "LLM_BINDING_UPDATE_FAILED":
		return "LLM module binding update failed"
	case "LLM_BINDING_DELETE_FAILED":
		return "LLM module binding delete failed"
	case "LLM_BINDING_TARGET_NOT_FOUND":
		return "target channel/model is not available for this tenant"
	case "LLM_BINDING_NOT_FOUND":
		return "project module binding override was not found"
	case "LLM_CATALOG_BACKEND_UNCONFIGURED":
		return "LLM catalog backend is not configured"
	case "LLM_CATALOG_QUERY_FAILED":
		return "LLM catalog query failed"
	case "LLM_CHANNEL_BACKEND_UNCONFIGURED":
		return "LLM channel backend is not configured"
	case "LLM_CHANNEL_NOT_FOUND":
		return "LLM channel was not found"
	case "LLM_CHANNEL_UPDATE_FAILED":
		return "LLM channel update failed"
	case "LLM_CREDENTIAL_DECRYPTION_FAILED":
		return "LLM credential decrypt failed"
	case "LLM_CREDENTIAL_ENCRYPTION_FAILED":
		return "LLM credential encryption failed"
	case "LLM_CREDENTIAL_ENCRYPTION_UNCONFIGURED":
		return "LLM credential encryption key is not configured"
	case "LLM_MODEL_SYNC_BACKEND_UNCONFIGURED":
		return "LLM model sync backend is not configured"
	case "LLM_MODEL_SYNC_FAILED":
		return "LLM model sync failed"
	case "LLM_MODEL_SYNC_QUERY_FAILED":
		return "LLM model sync query failed"
	case "LLM_MODEL_SYNC_STATUS_FAILED":
		return "LLM model sync status update failed"
	case "LLM_MODULE_UNBOUND":
		return "LLM module is not bound"
	case "LLM_PROVIDER_ERROR":
		return "LLM provider error"
	case "LLM_SETTINGS_BACKEND_UNCONFIGURED":
		return "LLM settings backend is not configured"
	case "LLM_SETTINGS_QUERY_FAILED":
		return "LLM settings query failed"
	case "VALIDATION_FAILED":
		return "invalid LLM request"
	default:
		return "LLM request failed"
	}
}

func writeSourceFileError(response http.ResponseWriter, request *http.Request, err error) {
	code := sourcefiles.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, sourceFilePublicErrorMessage(code), nil)
}

func sourceFilePublicErrorMessage(code string) string {
	switch code {
	case "SOURCE_FILE_BACKEND_UNCONFIGURED":
		return "source file backend is not configured"
	case "SOURCE_FILE_CREATE_FAILED":
		return "source file create failed"
	case "SOURCE_FILE_COMPLETE_FAILED":
		return "source file complete failed"
	case "SOURCE_FILE_UPLOAD_NOT_COMPLETABLE":
		return "source file upload cannot be completed from its current status"
	case "SOURCE_FILE_UPLOAD_NOT_WRITABLE":
		return "source file object upload cannot be written from its current status"
	case "SOURCE_FILE_QUERY_FAILED":
		return "source file query failed"
	case "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED":
		return "object storage backend is not configured"
	case "SOURCE_FILE_STORAGE_WRITE_FAILED":
		return "source file object upload failed"
	case "SOURCE_FILE_OBJECT_PAYLOAD_MISMATCH":
		return "source file upload payload does not match admitted metadata"
	case "SOURCE_FILE_STORAGE_VERIFY_FAILED":
		return "source file storage verification failed"
	case "SOURCE_FILE_NOT_UPLOADED":
		return "source file upload must be completed before seed run"
	case "SOURCE_FILE_OBJECT_NOT_FOUND":
		return "source file object was not found in object storage"
	case "NOT_FOUND":
		return "source file upload not found"
	case "VALIDATION_FAILED":
		return "invalid source file request"
	default:
		return "source file request failed"
	}
}

func writeCharacterConsoleError(response http.ResponseWriter, request *http.Request, err error) {
	code := characterconsole.ErrorCode(err)
	message := characterConsolePublicErrorMessage(code, err.Error())
	writeError(response, request, statusForAppCode(code), code, message, nil)
}

func writeCharacterConsoleLLMError(response http.ResponseWriter, request *http.Request, err error) {
	code := llm.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, characterConsoleLLMPublicErrorMessage(code), nil)
}

func characterConsolePublicErrorMessage(code string, fallback string) string {
	switch code {
	case "CHARACTER_INTERACTION_QUERY_FAILED":
		return "character interaction query failed"
	case "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED":
		return "character interaction backend is not configured"
	case "NOT_FOUND":
		return "character interaction was not found"
	default:
		return fallback
	}
}

func characterConsoleLLMPublicErrorMessage(code string) string {
	switch code {
	case "LLM_MODULE_UNBOUND":
		return "LLM module binding is not configured"
	case "LLM_BINDING_NOT_FOUND":
		return "LLM module binding was not found"
	case "LLM_CHANNEL_NOT_FOUND":
		return "LLM channel was not found"
	default:
		return "LLM Facility request failed"
	}
}

func characterConsoleWriterPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "writer run validation failed"
	case "WORKFLOW_BACKEND_UNCONFIGURED":
		return "writer workflow backend is not configured"
	case "WORKFLOW_ADMISSION_FAILED":
		return "writer workflow admission failed"
	case "NOT_FOUND":
		return "writer workflow was not found"
	default:
		return "writer workflow failed"
	}
}

func (s *Server) handleListAgentTraceEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, traceID := traceEventsPathParts(request.URL.Path)
	if projectID == "" || traceID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "agent trace route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionProjectRead) {
		return
	}
	includeFull := strings.EqualFold(strings.TrimSpace(request.URL.Query().Get("include_full")), "true")
	if includeFull {
		if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionTraceFullAccess) {
			return
		}
		err := s.traceAccessChecker.CanViewFullTrace(request.Context(), traces.AccessInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			TraceID:   traceID,
			ActorID:   s.actorUserID(request),
		})
		if err != nil {
			writeError(response, request, statusForAppCode(traces.ErrorCode(err)), traces.ErrorCode(err), err.Error(), nil)
			return
		}
	}
	items, err := s.traceReader.ListEvents(request.Context(), traces.EventQueryInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		TraceID:     traceID,
		IncludeFull: includeFull,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(traces.ErrorCode(err)), traces.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[traces.EventRecord]{Items: items})
}

func (s *Server) handleExportAgentTrace(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, traceID := traceExportPathParts(request.URL.Path)
	if projectID == "" || traceID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "agent trace export route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionProjectRead) {
		return
	}
	bodyBytes, err := io.ReadAll(request.Body)
	if err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid trace export payload", nil)
		return
	}
	if traceExportIncludeFullRequested(bodyBytes) {
		if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionTraceFullAccess) {
			return
		}
		err := s.traceAccessChecker.CanViewFullTrace(request.Context(), traces.AccessInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			TraceID:   traceID,
			ActorID:   s.actorUserID(request),
		})
		if err != nil {
			writeError(response, request, statusForAppCode(traces.ErrorCode(err)), traces.ErrorCode(err), err.Error(), nil)
			return
		}
	}
	var payload traceExportRequest
	decoder := json.NewDecoder(bytes.NewReader(bodyBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid trace export payload", nil)
		return
	}
	items, err := s.traceReader.ListEvents(request.Context(), traces.EventQueryInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		TraceID:     traceID,
		IncludeFull: payload.IncludeFull,
	})
	if err != nil {
		writeError(response, request, statusForAppCode(traces.ErrorCode(err)), traces.ErrorCode(err), err.Error(), nil)
		return
	}
	if err := s.traceExportAuditor.RecordExport(request.Context(), traces.ExportAuditInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		TraceID:     traceID,
		ActorID:     s.actorUserID(request),
		RequestID:   requestID(request),
		IncludeFull: payload.IncludeFull,
		EventCount:  len(items),
	}); err != nil {
		writeError(response, request, statusForAppCode(traces.ErrorCode(err)), traces.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, traceExportResponse{
		TraceID:     traceID,
		ProjectID:   projectID,
		IncludeFull: payload.IncludeFull,
		Items:       items,
	})
}

func (s *Server) handleStartHelloAgent(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "agent-runtime/hello-runs")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project route not found", nil)
		return
	}
	run, err := s.agentHelloStarter.StartHelloAgent(request.Context(), workflows.StartHelloAgentInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startHelloAgentResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleGetWriterRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/v1/writer-runs/"))
	if runID == "" || strings.Contains(runID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer run route not found", nil)
		return
	}
	run, err := s.writerReader.GetWriterRun(request.Context(), workflows.GetWriterRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, startWriterRunResponse{
		RunID:     run.RunID,
		TraceID:   run.TraceID,
		ProjectID: run.ProjectID,
		Status:    run.Status,
	})
}

func (s *Server) handleGetWorkflowRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := strings.TrimSpace(strings.TrimPrefix(request.URL.Path, "/v1/workflow-runs/"))
	if runID == "" || strings.Contains(runID, "/") {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "workflow run route not found", nil)
		return
	}
	run, err := s.workflowReader.GetWorkflowRun(request.Context(), workflows.GetWorkflowRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusOK, workflowRunToResponse(run))
}

func (s *Server) handleListWriterRunEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := writerRunEventsPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer run events route not found", nil)
		return
	}
	events, err := s.writerEventReader.ListWriterEvents(request.Context(), workflows.ListWriterEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: afterEventIDFromRequest(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	if strings.Contains(request.Header.Get("Accept"), "text/event-stream") {
		writeWriterEventsSSE(response, events)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[workflows.WriterEvent]{Items: events})
}

func (s *Server) handleListWorkflowRunEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := workflowRunEventsPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "workflow run events route not found", nil)
		return
	}
	events, err := s.workflowEventReader.ListWorkflowEvents(request.Context(), workflows.ListWorkflowEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: afterEventIDFromRequest(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	events = sanitizeWorkflowEvents(events)
	if strings.Contains(request.Header.Get("Accept"), "text/event-stream") {
		writeWorkflowEventsSSE(response, events)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[workflows.WorkflowEvent]{Items: events})
}

func (s *Server) handleCancelWriterRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := writerRunCancelPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer run cancel route not found", nil)
		return
	}
	cancelled, err := s.writerCanceller.CancelWriterRun(request.Context(), workflows.CancelWriterRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": cancelled.RunID,
		"status": cancelled.Status,
	})
}

func (s *Server) handleAdoptDraft(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	draftID := draftAdoptionPathPart(request.URL.Path)
	if draftID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "draft adoption route not found", nil)
		return
	}
	var payload adoptDraftRequest
	decoder := json.NewDecoder(request.Body)
	if err := decoder.Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid draft adoption payload", nil)
		return
	}
	if strings.TrimSpace(payload.SceneID) != "" {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "draft adoption scene override is not supported", nil)
		return
	}
	adoption, err := s.draftAdoptionStore.AdoptDraft(request.Context(), workflows.DraftAdoptionInput{
		TenantID:    tenantID,
		DraftID:     draftID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		ChapterID:   strings.TrimSpace(payload.ChapterID),
		BlockOrder:  payload.BlockOrder,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicDraftAdoptionErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, adoption)
}

func (s *Server) handleStartDraftReview(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	draftID := draftReviewPathPart(request.URL.Path)
	if draftID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "draft review route not found", nil)
		return
	}
	var payload startDraftReviewRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid draft review payload", nil)
		return
	}
	projectID := strings.TrimSpace(payload.BodyProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "project_id is required for draft review", nil)
		return
	}
	moduleKey := "writer_reviewer"
	_, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ModuleKey: moduleKey,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	options := sanitizeWorkflowOptions(payload.Options)
	options["module_key"] = moduleKey
	admission, err := s.draftReviewStore.StartDraftReview(request.Context(), workflows.StartDraftReviewInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		DraftID:     draftID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		RunID:       strings.TrimSpace(payload.RunID),
		Note:        strings.TrimSpace(payload.Note),
		ModuleKey:   moduleKey,
		Options:     options,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicDraftReviewErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, admission)
}

func (s *Server) handleListDraftReviews(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	draftID := draftReviewPathPart(request.URL.Path)
	if draftID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "draft review route not found", nil)
		return
	}
	reviews, err := s.draftReviewStore.ListDraftReviews(request.Context(), workflows.ListDraftReviewsInput{
		TenantID: tenantID,
		DraftID:  draftID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicDraftReviewErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, sanitizeDraftReviewList(reviews))
}

func (s *Server) handleGetManuscript(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "manuscript")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project manuscript route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	manuscript, err := s.manuscriptReader.GetManuscript(request.Context(), workflows.GetManuscriptInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicManuscriptErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, sanitizeManuscript(manuscript, projectID))
}

func (s *Server) handleGetManuscriptExport(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "manuscript/export")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project manuscript export route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	manifest, err := s.manuscriptReader.GetManuscriptExport(request.Context(), workflows.GetManuscriptExportInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		Format:    sanitizeManuscriptExportFormat(request.URL.Query().Get("format")),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicManuscriptExportErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, sanitizeManuscriptExportManifest(manifest, projectID))
}

func (s *Server) handleCancelWorkflowRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := workflowRunCancelPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "workflow run cancel route not found", nil)
		return
	}
	cancelled, err := s.workflowCanceller.CancelWorkflowRun(request.Context(), workflows.CancelWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": cancelled.RunID,
		"status": cancelled.Status,
	})
}

func (s *Server) handleRetryWorkflowRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := workflowRunRetryPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "workflow run retry route not found", nil)
		return
	}
	retried, err := s.workflowRetrier.RetryWorkflowRun(request.Context(), workflows.RetryWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		writeError(response, request, statusForWorkflowError(err), workflows.ErrorCode(err), err.Error(), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": retried.RunID,
		"status": retried.Status,
	})
}

func projectIDFromPath(path string) string {
	return projectIDFromPathWithSuffix(path, "writer-runs")
}

func projectIDFromPathWithSuffix(path string, expectedSuffix string) string {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != expectedSuffix {
		return ""
	}
	return strings.TrimSpace(projectID)
}

func storyGraphPathParts(path string, kind string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/story-graph/"+kind+"/")
	if !ok || strings.Contains(suffix, "/") {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(suffix)
}

func storyGraphEvidencePathParts(path string) (string, string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/story-graph/")
	if !ok {
		return "", "", ""
	}
	kind, rest, ok := strings.Cut(suffix, "/")
	if !ok {
		return "", "", ""
	}
	ownerID, tail, ok := strings.Cut(rest, "/")
	if !ok || tail != "evidence" {
		return "", "", ""
	}
	switch kind {
	case "nodes":
		return strings.TrimSpace(projectID), "node", strings.TrimSpace(ownerID)
	case "edges":
		return strings.TrimSpace(projectID), "edge", strings.TrimSpace(ownerID)
	default:
		return "", "", ""
	}
}

func commaList(raw string) []string {
	items := strings.Split(raw, ",")
	cleaned := []string{}
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item != "" {
			cleaned = append(cleaned, item)
		}
	}
	return cleaned
}

func queryLimit(response http.ResponseWriter, request *http.Request, message string) (int, bool) {
	rawLimit := strings.TrimSpace(request.URL.Query().Get("limit"))
	if rawLimit == "" {
		return 0, true
	}
	parsedLimit, err := strconv.Atoi(rawLimit)
	if err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", message, nil)
		return 0, false
	}
	return parsedLimit, true
}

func queryBool(raw string) bool {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func llmResolutionPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/llm/module-bindings/")
	if !ok {
		return "", ""
	}
	moduleKey, rest, ok := strings.Cut(suffix, "/")
	if !ok || rest != "resolution" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(moduleKey)
}

func llmModuleBindingPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/llm/module-bindings/")
	if !ok {
		return "", ""
	}
	moduleKey := strings.TrimSpace(suffix)
	if moduleKey == "" || strings.Contains(moduleKey, "/") {
		return "", ""
	}
	return strings.TrimSpace(projectID), moduleKey
}

func llmChannelModelsPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/llm/channels/")
	if !ok {
		return "", ""
	}
	channelID, rest, ok := strings.Cut(suffix, "/")
	if !ok || rest != "models" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(channelID)
}

func llmChannelIDFromPath(path string) string {
	channelID := strings.TrimSpace(strings.TrimPrefix(path, "/v1/llm/channels/"))
	if channelID == "" || strings.Contains(channelID, "/") {
		return ""
	}
	return channelID
}

func llmChannelSyncPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/llm/channels/")
	channelID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "sync-models" {
		return ""
	}
	return strings.TrimSpace(channelID)
}

func uploadIDFromCompletePath(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/uploads/")
	uploadID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "complete" {
		return ""
	}
	return strings.TrimSpace(uploadID)
}

func uploadIDFromObjectPath(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/uploads/")
	uploadID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "object" {
		return ""
	}
	return strings.TrimSpace(uploadID)
}

func assetIngestionRunPathPart(path string) string {
	runID := strings.TrimSpace(strings.TrimPrefix(path, "/v1/asset-ingestions/"))
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func styleExtractionRunPathPart(path string) string {
	runID := strings.TrimSpace(strings.TrimPrefix(path, "/v1/style-extractions/"))
	if runID == "" || strings.Contains(runID, "/") {
		return ""
	}
	return runID
}

func assetAdoptionPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/assets/")
	assetID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "adoptions" {
		return ""
	}
	return strings.TrimSpace(assetID)
}

func assetPathPart(path string) string {
	assetID := strings.TrimSpace(strings.TrimPrefix(path, "/v1/assets/"))
	if assetID == "" || strings.Contains(assetID, "/") {
		return ""
	}
	return assetID
}

func archiveAssetPathPart(path string, suffix string) string {
	remainder := strings.TrimPrefix(path, "/v1/archive-assets/")
	assetID, rest, ok := strings.Cut(remainder, "/")
	if !ok || rest != suffix {
		return ""
	}
	return strings.TrimSpace(assetID)
}

func archiveMemoryReviewPathPart(path string, suffix string) string {
	remainder := strings.TrimPrefix(path, "/v1/archive-memories/")
	memoryID, rest, ok := strings.Cut(remainder, "/")
	if !ok || rest != suffix {
		return ""
	}
	return strings.TrimSpace(memoryID)
}

func trimOptionalString(value *string) *string {
	if value == nil {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	return &trimmed
}

func sanitizeAssetPayload(value map[string]any) map[string]any {
	clean := map[string]any{}
	for key, item := range value {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if isHighRiskAssetField(normalizedKey) {
			continue
		}
		clean[key] = sanitizeAssetValue(item)
	}
	return clean
}

func sanitizeCharacterInteractionRecord(record characterconsole.InteractionRecord) characterconsole.InteractionRecord {
	record.Metadata = sanitizeAssetPayload(record.Metadata)
	return record
}

func sanitizeCharacterInteractionRecords(records []characterconsole.InteractionRecord) []characterconsole.InteractionRecord {
	clean := make([]characterconsole.InteractionRecord, 0, len(records))
	for _, record := range records {
		clean = append(clean, sanitizeCharacterInteractionRecord(record))
	}
	return clean
}

func sanitizeCharacterInteractionTurn(record characterconsole.TurnRecord) characterconsole.TurnRecord {
	record.Action = sanitizeAssetPayload(record.Action)
	record.WorldStateDelta = sanitizeAssetPayload(record.WorldStateDelta)
	return record
}

func sanitizeCharacterInteractionTurns(records []characterconsole.TurnRecord) []characterconsole.TurnRecord {
	clean := make([]characterconsole.TurnRecord, 0, len(records))
	for _, record := range records {
		clean = append(clean, sanitizeCharacterInteractionTurn(record))
	}
	return clean
}

func sanitizeDraftReviewList(list workflows.DraftReviewList) workflows.DraftReviewList {
	clean := workflows.DraftReviewList{
		DraftID:   strings.TrimSpace(list.DraftID),
		ProjectID: strings.TrimSpace(list.ProjectID),
		Reviews:   make([]workflows.DraftReviewRecord, 0, len(list.Reviews)),
	}
	for _, review := range list.Reviews {
		cleanReview := workflows.DraftReviewRecord{
			ReviewID:  strings.TrimSpace(review.ReviewID),
			RunID:     strings.TrimSpace(review.RunID),
			DraftID:   strings.TrimSpace(review.DraftID),
			ProjectID: strings.TrimSpace(review.ProjectID),
			Status:    sanitizePublicMetadataText(review.Status),
			CreatedAt: strings.TrimSpace(review.CreatedAt),
			UpdatedAt: strings.TrimSpace(review.UpdatedAt),
			Issues:    make([]workflows.DraftReviewIssue, 0, len(review.Issues)),
		}
		for _, issue := range review.Issues {
			cleanReview.Issues = append(cleanReview.Issues, workflows.DraftReviewIssue{
				IssueID:    strings.TrimSpace(issue.IssueID),
				Severity:   sanitizePublicMetadataText(issue.Severity),
				Category:   sanitizePublicMetadataText(issue.Category),
				Summary:    sanitizePublicMetadataText(issue.Summary),
				Suggestion: sanitizePublicMetadataText(issue.Suggestion),
				Status:     sanitizePublicMetadataText(issue.Status),
				CreatedAt:  strings.TrimSpace(issue.CreatedAt),
				UpdatedAt:  strings.TrimSpace(issue.UpdatedAt),
			})
		}
		clean.Reviews = append(clean.Reviews, cleanReview)
	}
	return clean
}

func sanitizeManuscript(manuscript workflows.Manuscript, projectID string) workflows.Manuscript {
	clean := workflows.Manuscript{
		ProjectID: sanitizePublicIdentifier(firstNonEmpty(manuscript.ProjectID, projectID)),
		Blocks:    make([]workflows.ManuscriptBlock, 0, len(manuscript.Blocks)),
	}
	for _, block := range manuscript.Blocks {
		clean.Blocks = append(clean.Blocks, sanitizeManuscriptBlock(block))
	}
	if metadata := sanitizeManuscriptMetadata(manuscript.Metadata); len(metadata) > 0 {
		clean.Metadata = metadata
	}
	return clean
}

func sanitizeManuscriptBlock(block workflows.ManuscriptBlock) workflows.ManuscriptBlock {
	return workflows.ManuscriptBlock{
		BlockID:       sanitizePublicIdentifier(block.BlockID),
		ProjectID:     sanitizePublicIdentifier(block.ProjectID),
		ChapterID:     sanitizePublicIdentifier(block.ChapterID),
		SourceDraftID: sanitizePublicIdentifier(block.SourceDraftID),
		BlockOrder:    block.BlockOrder,
		Status:        sanitizePublicMetadataText(block.Status),
		WordCount:     block.WordCount,
		CreatedAt:     sanitizePublicMetadataText(block.CreatedAt),
		UpdatedAt:     sanitizePublicMetadataText(block.UpdatedAt),
	}
}

func sanitizeManuscriptExportManifest(manifest workflows.ManuscriptExportManifest, projectID string) workflows.ManuscriptExportManifest {
	clean := workflows.ManuscriptExportManifest{
		ProjectID:      sanitizePublicIdentifier(firstNonEmpty(manifest.ProjectID, projectID)),
		Format:         sanitizeManuscriptExportFormat(manifest.Format),
		Status:         sanitizePublicMetadataText(manifest.Status),
		BlockCount:     manifest.BlockCount,
		TotalWordCount: manifest.TotalWordCount,
		GeneratedAt:    sanitizePublicMetadataText(manifest.GeneratedAt),
		Blocks:         make([]workflows.ManuscriptExportBlock, 0, len(manifest.Blocks)),
	}
	for _, block := range manifest.Blocks {
		clean.Blocks = append(clean.Blocks, workflows.ManuscriptExportBlock{
			BlockID:    sanitizePublicIdentifier(block.BlockID),
			BlockOrder: block.BlockOrder,
			WordCount:  block.WordCount,
		})
	}
	return clean
}

func sanitizeManuscriptExportFormat(format string) string {
	if strings.EqualFold(strings.TrimSpace(format), "metadata_manifest") {
		return "metadata_manifest"
	}
	return "metadata_manifest"
}

func sanitizeManuscriptMetadata(metadata map[string]any) map[string]any {
	clean := map[string]any{}
	for key, value := range metadata {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if isHighRiskAssetField(normalizedKey) {
			continue
		}
		clean[key] = sanitizeManuscriptMetadataValue(value)
	}
	return clean
}

func sanitizeManuscriptMetadataValue(value any) any {
	switch typed := value.(type) {
	case string:
		return sanitizePublicMetadataText(typed)
	case map[string]any:
		return sanitizeManuscriptMetadata(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeManuscriptMetadataValue(item))
		}
		return values
	default:
		return typed
	}
}

func sanitizePublicIdentifier(value string) string {
	value = strings.TrimSpace(value)
	lowered := strings.ToLower(value)
	for _, marker := range []string{
		"api_key",
		"apikey",
		"encrypted_api_key",
		"credential_ref",
		"credential-ref",
		"credential",
		"sk-",
		"prompt",
		"response",
		"body_text",
		"content_text",
		"source_text",
		"source_material",
		"raw_text",
		"raw_body",
		"raw_content",
		"draft=",
		"manuscript",
		"private",
	} {
		if strings.Contains(lowered, marker) {
			return ""
		}
	}
	return value
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func sanitizePublicMetadataText(value string) string {
	value = strings.TrimSpace(value)
	lowered := strings.ToLower(value)
	for _, marker := range []string{
		"api_key",
		"apikey",
		"encrypted_api_key",
		"credential_ref",
		"credential-ref",
		"sk-",
		"prompt",
		"response",
		"body_text",
		"content_text",
		"source_text",
		"source_material",
		"raw_text",
		"raw_body",
		"raw_content",
		"draft",
		"manuscript",
	} {
		if strings.Contains(lowered, marker) {
			return ""
		}
	}
	return value
}

func characterInteractionTurnsWithSummaryMaterial(records []characterconsole.TurnRecord) []characterconsole.TurnRecord {
	clean := make([]characterconsole.TurnRecord, 0, len(records))
	for _, record := range records {
		if strings.TrimSpace(record.Summary) == "" {
			continue
		}
		clean = append(clean, record)
	}
	return clean
}

func characterInteractionChapterDraftInstruction(record characterconsole.InteractionRecord, turns []characterconsole.TurnRecord, payload convertCharacterInteractionToChapterDraftRequest) string {
	var builder strings.Builder
	builder.WriteString("Write a chapter draft scene from this Character Console interaction.\n")
	builder.WriteString("Use only the public interaction metadata and public turn summaries provided here.\n")
	if title := strings.TrimSpace(record.Title); title != "" {
		builder.WriteString("Interaction title: ")
		builder.WriteString(title)
		builder.WriteString("\n")
	}
	if summary := strings.TrimSpace(record.Summary); summary != "" {
		builder.WriteString("Interaction summary: ")
		builder.WriteString(summary)
		builder.WriteString("\n")
	}
	if record.WorldlineSessionID != "" || record.AnchorType != "" || record.AnchorID != "" {
		builder.WriteString("Story anchor: ")
		if record.WorldlineSessionID != "" {
			builder.WriteString("worldline_session=")
			builder.WriteString(record.WorldlineSessionID)
			builder.WriteString(" ")
		}
		if record.AnchorType != "" {
			builder.WriteString("anchor_type=")
			builder.WriteString(record.AnchorType)
			builder.WriteString(" ")
		}
		if record.AnchorID != "" {
			builder.WriteString("anchor_id=")
			builder.WriteString(record.AnchorID)
		}
		builder.WriteString("\n")
	}
	if chapterID := strings.TrimSpace(payload.TargetChapterID); chapterID != "" {
		builder.WriteString("Target chapter id: ")
		builder.WriteString(chapterID)
		builder.WriteString("\n")
	}
	if povMode := strings.TrimSpace(payload.POVMode); povMode != "" {
		builder.WriteString("POV mode: ")
		builder.WriteString(povMode)
		builder.WriteString("\n")
	}
	if authorInstruction := strings.TrimSpace(payload.AuthorInstruction); authorInstruction != "" {
		builder.WriteString("Author instruction: ")
		builder.WriteString(authorInstruction)
		builder.WriteString("\n")
	}
	if len(turns) == 0 {
		builder.WriteString("Public turn summaries: none recorded yet.\n")
		return builder.String()
	}
	builder.WriteString("Public turn summaries:\n")
	for _, turn := range turns {
		builder.WriteString("- ")
		if turn.TurnOrder > 0 {
			builder.WriteString(strconv.Itoa(turn.TurnOrder))
			builder.WriteString(". ")
		}
		builder.WriteString(strings.TrimSpace(turn.ActorType))
		if actorID := strings.TrimSpace(turn.ActorID); actorID != "" {
			builder.WriteString(":")
			builder.WriteString(actorID)
		}
		if turnKind := strings.TrimSpace(turn.TurnKind); turnKind != "" {
			builder.WriteString(" [")
			builder.WriteString(turnKind)
			builder.WriteString("]")
		}
		if summary := strings.TrimSpace(turn.Summary); summary != "" {
			builder.WriteString(" ")
			builder.WriteString(summary)
		}
		builder.WriteString("\n")
	}
	return builder.String()
}

func characterInteractionChapterDraftOptions(record characterconsole.InteractionRecord, turns []characterconsole.TurnRecord, payload convertCharacterInteractionToChapterDraftRequest, moduleKey string, resolution llm.ModuleResolution) map[string]any {
	options := map[string]any{
		"source":                   "character_console",
		"character_interaction_id": record.InteractionID,
		"worldline_session_id":     record.WorldlineSessionID,
		"anchor_type":              record.AnchorType,
		"anchor_id":                record.AnchorID,
		"pov_agent_id":             record.POVAgentID,
		"turn_count":               len(turns),
		"module_key":               moduleKey,
		"llm_resolution":           workflowLLMResolution(resolution),
	}
	if targetChapterID := strings.TrimSpace(payload.TargetChapterID); targetChapterID != "" {
		options["target_chapter_id"] = targetChapterID
	}
	if povMode := strings.TrimSpace(payload.POVMode); povMode != "" {
		options["pov_mode"] = povMode
	}
	if styleAssetIDs := trimmedStringList(payload.StyleAssetIDs); len(styleAssetIDs) > 0 {
		options["style_asset_ids"] = styleAssetIDs
	}
	if metadata := sanitizeAssetPayload(record.Metadata); len(metadata) > 0 {
		options["interaction_metadata"] = metadata
	}
	if turnSummaries := characterInteractionPublicTurnSummaries(turns); len(turnSummaries) > 0 {
		options["turn_summaries"] = turnSummaries
	}
	return options
}

func characterInteractionPublicTurnSummaries(turns []characterconsole.TurnRecord) []map[string]any {
	summaries := make([]map[string]any, 0, len(turns))
	for _, turn := range turns {
		item := map[string]any{
			"turn_id":    turn.TurnID,
			"turn_order": turn.TurnOrder,
			"actor_type": strings.TrimSpace(turn.ActorType),
			"actor_id":   strings.TrimSpace(turn.ActorID),
			"turn_kind":  strings.TrimSpace(turn.TurnKind),
			"summary":    strings.TrimSpace(turn.Summary),
		}
		if traceID := strings.TrimSpace(turn.TraceID); traceID != "" {
			item["trace_id"] = traceID
		}
		summaries = append(summaries, item)
	}
	return summaries
}

func trimmedStringList(values []string) []string {
	clean := make([]string, 0, len(values))
	seen := map[string]struct{}{}
	for _, value := range values {
		item := strings.TrimSpace(value)
		if item == "" {
			continue
		}
		if _, ok := seen[item]; ok {
			continue
		}
		seen[item] = struct{}{}
		clean = append(clean, item)
	}
	return clean
}

func sanitizeAssetValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeAssetPayload(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeAssetValue(item))
		}
		return values
	default:
		return value
	}
}

func sanitizeAssetTags(tags []string) []string {
	clean := make([]string, 0, len(tags))
	for _, tag := range tags {
		value := strings.TrimSpace(tag)
		if value == "" || isHighRiskAssetField(strings.ToLower(value)) {
			continue
		}
		clean = append(clean, value)
	}
	return clean
}

func sanitizedBulkAssetIDs(assetIDs []string) []string {
	clean := make([]string, 0, len(assetIDs))
	seen := map[string]struct{}{}
	for _, assetID := range assetIDs {
		value := strings.TrimSpace(assetID)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		clean = append(clean, value)
	}
	return clean
}

func isHighRiskAssetField(field string) bool {
	switch field {
	case "api_key", "apikey", "encrypted_api_key", "credential_ref", "material_text", "source_material", "source_text", "input_text", "output_text", "body_text", "content_text", "prompt", "response", "raw_body", "raw_content", "raw_text", "body", "content", "candidate_body", "candidate_event_body", "event_body", "draft", "manuscript":
		return true
	default:
		return false
	}
}

func traceEventsPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/agent-traces/")
	if !ok {
		return "", ""
	}
	traceID, rest, ok := strings.Cut(suffix, "/")
	if !ok || rest != "events" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(traceID)
}

func traceExportPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/agent-traces/")
	if !ok {
		return "", ""
	}
	traceID, rest, ok := strings.Cut(suffix, "/")
	if !ok || rest != "export" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(traceID)
}

func writerRunEventsPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/writer-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func workflowRunEventsPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/workflow-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunEventsPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/seed-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunCancelPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/seed-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunRetryPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/seed-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "retry" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func writerRunCancelPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/writer-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func draftAdoptionPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/drafts/")
	draftID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "adoptions" {
		return ""
	}
	return strings.TrimSpace(draftID)
}

func draftReviewPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/drafts/")
	draftID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "reviews" {
		return ""
	}
	return strings.TrimSpace(draftID)
}

func characterInteractionNestedPathPart(path string, expectedSuffix string) string {
	remainder := strings.TrimPrefix(path, "/v1/character-interactions/")
	interactionID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != expectedSuffix {
		return ""
	}
	return strings.TrimSpace(interactionID)
}

func workflowRunCancelPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/workflow-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func workflowRunRetryPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/workflow-runs/")
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "retry" {
		return ""
	}
	return strings.TrimSpace(runID)
}

func afterEventIDFromRequest(request *http.Request) string {
	if queryCursor := strings.TrimSpace(request.URL.Query().Get("after_event_id")); queryCursor != "" {
		return queryCursor
	}
	return strings.TrimSpace(request.Header.Get("Last-Event-ID"))
}

func moduleKeyFromOptions(options map[string]any) string {
	if options == nil {
		return "writer_composer"
	}
	moduleKey, _ := options["module_key"].(string)
	moduleKey = strings.TrimSpace(moduleKey)
	if moduleKey == "" {
		return "writer_composer"
	}
	return moduleKey
}

func cloneOptions(options map[string]any) map[string]any {
	clone := map[string]any{}
	for key, value := range options {
		clone[key] = value
	}
	return clone
}

func sanitizeWorkflowOptions(options map[string]any) map[string]any {
	clean := map[string]any{}
	for key, value := range options {
		normalizedKey := strings.ToLower(strings.TrimSpace(key))
		if isUntrustedWorkflowOptionField(normalizedKey) {
			continue
		}
		clean[key] = sanitizeWorkflowOptionValue(value)
	}
	return clean
}

func sanitizeWorkflowOptionValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeWorkflowOptions(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeWorkflowOptionValue(item))
		}
		return values
	default:
		return value
	}
}

func isUntrustedWorkflowOptionField(field string) bool {
	if isHighRiskAssetField(field) {
		return true
	}
	switch field {
	case "tenant_id", "tenantid", "project_id", "projectid", "credential", "credentials", "credentialref", "encryptedapikey":
		return true
	default:
		return false
	}
}

func sanitizedLLMResolution(resolution llm.ModuleResolution) llmResolutionResponse {
	return llmResolutionResponse{
		ModuleKey:     resolution.ModuleKey,
		ChannelID:     resolution.ChannelID,
		ModelID:       resolution.ModelID,
		Provider:      resolution.Provider,
		BaseURL:       resolution.BaseURL,
		SupportsTools: resolution.SupportsTools,
		SupportsJSON:  resolution.SupportsJSON,
		Settings:      resolution.Settings,
	}
}

func workflowLLMResolution(resolution llm.ModuleResolution) map[string]any {
	return map[string]any{
		"module_key":     resolution.ModuleKey,
		"channel_id":     resolution.ChannelID,
		"model_id":       resolution.ModelID,
		"provider":       resolution.Provider,
		"base_url":       resolution.BaseURL,
		"credential_ref": resolution.CredentialRef,
		"supports_tools": resolution.SupportsTools,
		"supports_json":  resolution.SupportsJSON,
		"settings":       resolution.Settings,
	}
}

func workflowRunToResponse(run workflows.WorkflowRun) workflowRunResponse {
	return workflowRunResponse{
		RunID:        run.RunID,
		WorkflowType: run.WorkflowType,
		ProjectID:    run.ProjectID,
		Status:       run.Status,
		Progress:     run.Progress,
		Message:      run.Message,
		ErrorCode:    run.ErrorCode,
		ErrorMessage: run.ErrorMessage,
		CreatedAt:    run.CreatedAt,
		UpdatedAt:    run.UpdatedAt,
	}
}

func statusForWorkflowError(err error) int {
	return statusForAppCode(workflows.ErrorCode(err))
}

func publicDraftAdoptionErrorMessage(code string) string {
	switch code {
	case "DRAFT_ADOPTION_BACKEND_UNCONFIGURED":
		return "draft adoption backend is not configured"
	case "DRAFT_ADOPTION_WRITE_FAILED":
		return "draft adoption write failed"
	case "NOT_FOUND":
		return "candidate draft not found"
	case "VALIDATION_FAILED":
		return "invalid draft adoption request"
	default:
		return "draft adoption failed"
	}
}

func publicDraftReviewErrorMessage(code string) string {
	switch code {
	case "WRITER_REVIEW_BACKEND_UNCONFIGURED":
		return "writer review backend is not configured"
	case "WRITER_REVIEW_ADMISSION_FAILED":
		return "writer review admission failed"
	case "WRITER_REVIEW_QUERY_FAILED":
		return "writer review query failed"
	case "NOT_FOUND":
		return "draft review not found"
	case "VALIDATION_FAILED":
		return "invalid draft review request"
	default:
		return "writer review failed"
	}
}

func publicManuscriptErrorMessage(code string) string {
	switch code {
	case "MANUSCRIPT_BACKEND_UNCONFIGURED":
		return "manuscript backend is not configured"
	case "MANUSCRIPT_QUERY_FAILED":
		return "manuscript query failed"
	case "VALIDATION_FAILED":
		return "invalid manuscript request"
	default:
		return "manuscript request failed"
	}
}

func publicManuscriptExportErrorMessage(code string) string {
	switch code {
	case "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED":
		return "manuscript export backend is not configured"
	case "MANUSCRIPT_EXPORT_QUERY_FAILED":
		return "manuscript export query failed"
	case "VALIDATION_FAILED":
		return "invalid manuscript export request"
	default:
		return "manuscript export request failed"
	}
}

func statusForAuthCode(code string) int {
	switch code {
	case auth.CodeUnauthenticated:
		return http.StatusUnauthorized
	case auth.CodeValidationFailed:
		return http.StatusBadRequest
	case auth.CodeUserNotFound:
		return http.StatusNotFound
	case auth.CodeAccessDenied:
		return http.StatusForbidden
	default:
		return http.StatusServiceUnavailable
	}
}

func publicAuthCode(code string) string {
	switch code {
	case auth.CodeUnauthenticated,
		auth.CodeBackendUnconfigured,
		auth.CodeUserNotFound,
		auth.CodeAccessDenied,
		auth.CodeLookupFailed,
		auth.CodeValidationFailed:
		return code
	default:
		return auth.CodeLookupFailed
	}
}

func authPublicErrorMessage(code string) string {
	switch code {
	case auth.CodeUnauthenticated:
		return "user context is required"
	case auth.CodeBackendUnconfigured:
		return "auth backend is not configured"
	case auth.CodeUserNotFound:
		return "current user was not found"
	case auth.CodeAccessDenied:
		return "current user access is denied"
	case auth.CodeValidationFailed:
		return "invalid auth request"
	case auth.CodeLookupFailed:
		return "auth lookup failed"
	default:
		return "auth request failed"
	}
}

func statusForAppCode(code string) int {
	switch code {
	case "VALIDATION_FAILED":
		return http.StatusBadRequest
	case "EVENT_CURSOR_NOT_FOUND":
		return http.StatusBadRequest
	case "NOT_FOUND":
		return http.StatusNotFound
	case "LLM_CHANNEL_NOT_FOUND":
		return http.StatusNotFound
	case "LLM_BINDING_NOT_FOUND":
		return http.StatusNotFound
	case "UNAUTHENTICATED":
		return http.StatusUnauthorized
	case "TRACE_ACCESS_DENIED":
		return http.StatusForbidden
	case "STORY_GRAPH_EVIDENCE_ACCESS_DENIED":
		return http.StatusForbidden
	case "SOURCE_FILE_NOT_UPLOADED":
		return http.StatusConflict
	case "SOURCE_FILE_UPLOAD_NOT_COMPLETABLE":
		return http.StatusConflict
	case "SOURCE_FILE_UPLOAD_NOT_WRITABLE":
		return http.StatusConflict
	case "SOURCE_FILE_OBJECT_NOT_FOUND":
		return http.StatusConflict
	case "SOURCE_FILE_OBJECT_PAYLOAD_MISMATCH":
		return http.StatusConflict
	default:
		return http.StatusServiceUnavailable
	}
}

func writeJSON(response http.ResponseWriter, status int, body any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	_ = json.NewEncoder(response).Encode(body)
}

func writeWriterEventsSSE(response http.ResponseWriter, events []workflows.WriterEvent) {
	response.Header().Set("Content-Type", "text/event-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	for _, event := range events {
		payload, err := json.Marshal(event)
		if err != nil {
			continue
		}
		_, _ = response.Write([]byte("id: " + event.EventID + "\n"))
		_, _ = response.Write([]byte("event: workflow.event\n"))
		_, _ = response.Write([]byte("data: " + string(payload) + "\n\n"))
	}
	if flusher, ok := response.(http.Flusher); ok {
		flusher.Flush()
	}
}

func writeWorkflowEventsSSE(response http.ResponseWriter, events []workflows.WorkflowEvent) {
	response.Header().Set("Content-Type", "text/event-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	for _, event := range events {
		payload, err := json.Marshal(event)
		if err != nil {
			continue
		}
		_, _ = response.Write([]byte("id: " + event.EventID + "\n"))
		_, _ = response.Write([]byte("event: workflow.event\n"))
		_, _ = response.Write([]byte("data: " + string(payload) + "\n\n"))
	}
	if flusher, ok := response.(http.Flusher); ok {
		flusher.Flush()
	}
}

func sanitizeWorkflowEvents(events []workflows.WorkflowEvent) []workflows.WorkflowEvent {
	sanitized := make([]workflows.WorkflowEvent, 0, len(events))
	for _, event := range events {
		event.Payload = workflows.SanitizeWorkflowEventPayload(event.Payload)
		sanitized = append(sanitized, event)
	}
	return sanitized
}

func trimStringSlice(values []string) []string {
	trimmed := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		trimmed = append(trimmed, value)
	}
	return trimmed
}

func writeError(response http.ResponseWriter, request *http.Request, status int, code string, message string, details map[string]any) {
	if details == nil {
		details = map[string]any{}
	}
	writeJSON(response, status, errorEnvelope{
		Error: apiError{
			Code:      code,
			Message:   message,
			Details:   details,
			RequestID: requestID(request),
		},
	})
}

func requestID(request *http.Request) string {
	if headerID := strings.TrimSpace(request.Header.Get("X-Request-Id")); headerID != "" {
		if safeRequestID(headerID) {
			return headerID
		}
	}
	return newRequestID()
}

func newRequestID() string {
	var bytes [8]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "req_unknown"
	}
	return "req_" + hex.EncodeToString(bytes[:])
}

func safeRequestID(value string) bool {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 128 || requestIDSensitive(value) {
		return false
	}
	for _, char := range value {
		switch {
		case char >= 'a' && char <= 'z':
		case char >= 'A' && char <= 'Z':
		case char >= '0' && char <= '9':
		case char == '-', char == '_', char == '.', char == ':':
		default:
			return false
		}
	}
	return true
}

func requestIDSensitive(value string) bool {
	normalized := strings.ToLower(strings.TrimSpace(value))
	normalized = strings.NewReplacer("-", "_", ".", "_", ":", "_").Replace(normalized)
	compact := strings.ReplaceAll(normalized, "_", "")
	for _, forbidden := range []string{
		"apikey",
		"bodytext",
		"candidatebody",
		"candidateeventbody",
		"contenttext",
		"credentialref",
		"draft",
		"encryptedapikey",
		"eventbody",
		"manuscript",
		"objectkey",
		"prompt",
		"rawcontent",
		"rawtext",
		"response",
		"sourceobjectkey",
		"sourcetext",
	} {
		if strings.Contains(compact, forbidden) {
			return true
		}
	}
	return false
}
