package httpapi

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/assetdistillation"
	"mirofish-novel/apps/api/internal/assets"
	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/authrecovery"
	"mirofish-novel/apps/api/internal/characterconsole"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/platformratelimit"
	"mirofish-novel/apps/api/internal/projectadmin"
	"mirofish-novel/apps/api/internal/projectoverview"
	"mirofish-novel/apps/api/internal/projectreadiness"
	"mirofish-novel/apps/api/internal/registration"
	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/storygraph"
	"mirofish-novel/apps/api/internal/traces"
	"mirofish-novel/apps/api/internal/workflows"
	"mirofish-novel/apps/api/internal/worldline"
)

type Config struct {
	SessionAuthSecret                string
	AllowDevelopmentAuth             bool
	ForceSecureSessionCookies        bool
	AuthReader                       auth.Reader
	PasswordAuthenticator            auth.PasswordAuthenticator
	PasswordChanger                  auth.PasswordChanger
	RegistrationService              RegistrationService
	AuthSessionStore                 auth.SessionStore
	Authorizer                       auth.Authorizer
	WriterStarter                    workflows.WriterStarter
	WriterReader                     workflows.WriterReader
	WriterEventReader                workflows.WriterEventReader
	WriterCanceller                  workflows.WriterCanceller
	WriterThreadStore                workflows.WriterThreadStore
	DraftAdoptionStore               workflows.DraftAdoptionStore
	DraftReviewStore                 workflows.DraftReviewStore
	DraftReviewOwnerLookup           workflows.DraftReviewOwnerLookup
	DraftReviewIssueStore            workflows.DraftReviewIssueStore
	ManuscriptReader                 workflows.ManuscriptReader
	ManuscriptArtifactExporter       workflows.ManuscriptArtifactExporter
	WorkflowReader                   workflows.WorkflowReader
	WorkflowEventReader              workflows.WorkflowEventReader
	WorkflowCanceller                workflows.WorkflowCanceller
	WorkflowRetrier                  workflows.WorkflowRetrier
	SeedSegmentRetrier               workflows.SeedSegmentRetrier
	SeedStarter                      workflows.SeedRunStarter
	SeedRunReader                    workflows.SeedRunReader
	AnalysisStarter                  workflows.AnalysisRunStarter
	AnalysisRunReader                workflows.AnalysisRunReader
	AnalysisEventReader              workflows.AnalysisEventReader
	AnalysisCanceller                workflows.AnalysisCanceller
	AnalysisWorkspaceReader          workflows.AnalysisWorkspaceReader
	AnalysisCandidateReader          workflows.AnalysisCandidateReader
	AnalysisAssetImporter            workflows.AnalysisAssetImporter
	ProjectOverviewReader            projectoverview.Reader
	ProjectReadinessReader           projectreadiness.Reader
	AgentHelloStarter                workflows.AgentHelloStarter
	LLMResolver                      llm.Resolver
	LLMModuleRegistry                llm.ModuleRegistry
	LLMBindingStore                  llm.BindingStore
	LLMCatalogReader                 llm.CatalogReader
	LLMChannelStore                  llm.ChannelStore
	LLMModelStore                    llm.ModelStore
	LLMModelSyncer                   llm.ModelSyncer
	LLMSettingsReader                llm.SettingsReader
	LLMTelemetryReader               llm.TelemetryReader
	LLMQuotaStore                    llm.QuotaPolicyStore
	AssetQueryEmbeddingResolver      assets.QueryEmbeddingResolver
	AssetSearchIndexChecker          assets.SearchIndexChecker
	TraceReader                      traces.Reader
	TraceAccessChecker               traces.AccessChecker
	TraceExportAuditor               traces.ExportAuditor
	SourceFileStore                  sourcefiles.Store
	SourceFileObjectWriter           sourcefiles.ObjectWriter
	AssetReader                      assets.Reader
	ArchiveMemoryReader              assets.ArchiveMemoryReader
	ArchiveMemoryReviewStore         assets.ArchiveMemoryReviewStore
	AssetAdoptionStore               assets.AdoptionStore
	AssetMutationStore               assets.MutationStore
	AssetBulkActionStore             assets.BulkActionStore
	AssetIngestionStarter            workflows.AssetIngestionStarter
	AssetIngestionReader             workflows.AssetIngestionReader
	AssetReindexStarter              workflows.AssetReindexStarter
	StyleExtractionStarter           workflows.StyleExtractionStarter
	StyleExtractionReader            workflows.StyleExtractionReader
	StoryGraphBuildStarter           workflows.StoryGraphBuildStarter
	StoryGraphBondGenerationStarter  workflows.StoryGraphBondGenerationStarter
	StoryGraphReader                 storygraph.Reader
	StoryGraphCandidateAdoptionStore storygraph.CandidateAdoptionStore
	StoryGraphEvidenceAccess         storygraph.EvidenceAccessChecker
	WorldlineSavedPathReader         worldline.SavedPathReader
	WorldlineSavedPathStore          worldline.SavedPathStore
	WorldlineSessionStarter          worldline.SessionStarter
	WorldlineStepStarter             worldline.StepStarter
	WorldlineAutoEvolutionStarter    worldline.AutoEvolutionStarter
	WorldlineSessionReader           worldline.SessionReader
	WorldlineTimelineReader          worldline.TimelineReader
	WorldlineEventReader             worldline.EventReader
	WorldlineEventAdoptionStore      worldline.EventAdoptionStore
	WorldlineEventMutationStore      worldline.EventMutationStore
	WorldlineVariableStore           worldline.VariableStore
	WorldlinePreparationStarter      worldline.PreparationStarter
	WorldlinePreparationStore        worldline.PreparationStore
	CharacterConsoleStore            characterconsole.Store
	CharacterProposalStore           characterconsole.ProposalStore
	CharacterDialogueStarter         workflows.CharacterDialogueStarter
	WriterWorkspaceHandler           http.Handler
	ManuscriptWorkspaceHandler       http.Handler
	ManuscriptExportHandler          http.Handler
	AssetCatalogHandler              http.Handler
	AssetDistillationHandler         http.Handler
	DistillationEnqueuer             DistillationEnqueuer
	AuthRecoveryHandler              http.Handler
	CollaborationHandler             http.Handler
	ProjectAdminHandler              http.Handler
	LLMAdminHandler                  http.Handler
	RateLimiter                      platformratelimit.Limiter
	TrustedClientProofVerifier       TrustedClientProofVerifier
	ReadinessChecker                 ReadinessChecker
}

type DistillationEnqueueInput struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
	BlockID     string
	ChapterID   string
	SceneID     string
}

type DistillationEnqueuer interface {
	EnqueueAfterAdoption(context.Context, DistillationEnqueueInput) error
}

type TrustedClientProofVerifier interface {
	Verify(string) (string, error)
}

type RegistrationService interface {
	Register(context.Context, registration.RegisterInput) (registration.Result, error)
}

type ReadinessDependency struct {
	Name      string `json:"name"`
	Status    string `json:"status"`
	ErrorCode string `json:"error_code,omitempty"`
}

type ReadinessReport struct {
	Status       string                `json:"status"`
	Dependencies []ReadinessDependency `json:"dependencies"`
	CheckedAt    time.Time             `json:"-"`
}

type ReadinessChecker interface {
	Check(context.Context) ReadinessReport
}

type Server struct {
	sessionAuthSecret                string
	allowDevelopmentAuth             bool
	forceSecureSessionCookies        bool
	authReader                       auth.Reader
	passwordAuthenticator            auth.PasswordAuthenticator
	passwordChanger                  auth.PasswordChanger
	registrationService              RegistrationService
	authSessionStore                 auth.SessionStore
	authorizer                       auth.Authorizer
	writerStarter                    workflows.WriterStarter
	writerReader                     workflows.WriterReader
	writerEventReader                workflows.WriterEventReader
	writerCanceller                  workflows.WriterCanceller
	writerThreadStore                workflows.WriterThreadStore
	draftAdoptionStore               workflows.DraftAdoptionStore
	draftReviewStore                 workflows.DraftReviewStore
	draftReviewOwnerLookup           workflows.DraftReviewOwnerLookup
	draftReviewIssueStore            workflows.DraftReviewIssueStore
	manuscriptReader                 workflows.ManuscriptReader
	manuscriptArtifactExporter       workflows.ManuscriptArtifactExporter
	workflowReader                   workflows.WorkflowReader
	workflowEventReader              workflows.WorkflowEventReader
	workflowCanceller                workflows.WorkflowCanceller
	workflowRetrier                  workflows.WorkflowRetrier
	seedSegmentRetrier               workflows.SeedSegmentRetrier
	seedStarter                      workflows.SeedRunStarter
	seedRunReader                    workflows.SeedRunReader
	analysisStarter                  workflows.AnalysisRunStarter
	analysisRunReader                workflows.AnalysisRunReader
	analysisEventReader              workflows.AnalysisEventReader
	analysisCanceller                workflows.AnalysisCanceller
	analysisWorkspaceReader          workflows.AnalysisWorkspaceReader
	analysisCandidateReader          workflows.AnalysisCandidateReader
	analysisAssetImporter            workflows.AnalysisAssetImporter
	projectOverviewReader            projectoverview.Reader
	projectReadinessReader           projectreadiness.Reader
	agentHelloStarter                workflows.AgentHelloStarter
	llmResolver                      llm.Resolver
	llmModuleRegistry                llm.ModuleRegistry
	llmBindingStore                  llm.BindingStore
	llmCatalogReader                 llm.CatalogReader
	llmChannelStore                  llm.ChannelStore
	llmModelStore                    llm.ModelStore
	llmModelSyncer                   llm.ModelSyncer
	llmSettingsReader                llm.SettingsReader
	llmTelemetryReader               llm.TelemetryReader
	llmQuotaStore                    llm.QuotaPolicyStore
	assetQueryEmbeddingResolver      assets.QueryEmbeddingResolver
	assetSearchIndexChecker          assets.SearchIndexChecker
	traceReader                      traces.Reader
	traceAccessChecker               traces.AccessChecker
	traceExportAuditor               traces.ExportAuditor
	sourceFileStore                  sourcefiles.Store
	sourceFileObjectWriter           sourcefiles.ObjectWriter
	assetReader                      assets.Reader
	archiveMemoryReader              assets.ArchiveMemoryReader
	archiveMemoryReviewStore         assets.ArchiveMemoryReviewStore
	assetAdoptionStore               assets.AdoptionStore
	assetMutationStore               assets.MutationStore
	assetBulkActionStore             assets.BulkActionStore
	assetIngestionStarter            workflows.AssetIngestionStarter
	assetIngestionReader             workflows.AssetIngestionReader
	assetReindexStarter              workflows.AssetReindexStarter
	styleExtractionStarter           workflows.StyleExtractionStarter
	styleExtractionReader            workflows.StyleExtractionReader
	storyGraphBuildStarter           workflows.StoryGraphBuildStarter
	storyGraphBondGenerationStarter  workflows.StoryGraphBondGenerationStarter
	storyGraphReader                 storygraph.Reader
	storyGraphCandidateAdoptionStore storygraph.CandidateAdoptionStore
	storyGraphEvidenceAccess         storygraph.EvidenceAccessChecker
	worldlineSavedPathReader         worldline.SavedPathReader
	worldlineSavedPathStore          worldline.SavedPathStore
	worldlineSessionStarter          worldline.SessionStarter
	worldlineStepStarter             worldline.StepStarter
	worldlineAutoEvolutionStarter    worldline.AutoEvolutionStarter
	worldlineSessionReader           worldline.SessionReader
	worldlineTimelineReader          worldline.TimelineReader
	worldlineEventReader             worldline.EventReader
	worldlineEventAdoptionStore      worldline.EventAdoptionStore
	worldlineEventMutationStore      worldline.EventMutationStore
	worldlineVariableStore           worldline.VariableStore
	worldlinePreparationStarter      worldline.PreparationStarter
	worldlinePreparationStore        worldline.PreparationStore
	characterConsoleStore            characterconsole.Store
	characterProposalStore           characterconsole.ProposalStore
	characterDialogueStarter         workflows.CharacterDialogueStarter
	writerWorkspaceHandler           http.Handler
	manuscriptWorkspaceHandler       http.Handler
	manuscriptExportHandler          http.Handler
	assetCatalogHandler              http.Handler
	assetDistillationHandler         http.Handler
	distillationEnqueuer             DistillationEnqueuer
	authRecoveryHandler              http.Handler
	collaborationHandler             http.Handler
	projectAdminHandler              http.Handler
	llmAdminHandler                  http.Handler
	rateLimiter                      platformratelimit.Limiter
	trustedClientProofVerifier       TrustedClientProofVerifier
	readinessChecker                 ReadinessChecker
}

type apiError struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	Details   map[string]any `json:"details"`
	RequestID string         `json:"request_id"`
}

const sessionCookieName = "mirofish_session"
const csrfHeaderName = "X-CSRF-Token"
const jwtSessionIssuer = "mirofish-auth"
const jwtSessionAudience = "mirofish-api"
const sessionTTL = 7 * 24 * time.Hour

type actorUserIDContextKey struct{}
type csrfVerifiedContextKey struct{}

type errorEnvelope struct {
	Error apiError `json:"error"`
}

type startWriterRunRequest struct {
	Mode        string         `json:"mode"`
	Instruction string         `json:"instruction"`
	ChapterID   string         `json:"chapter_id"`
	SceneID     string         `json:"scene_id"`
	Options     map[string]any `json:"options"`
}

type createDevSessionRequest struct {
	UserID string `json:"user_id"`
}

type passwordLoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type signupRequest struct {
	DisplayName  string `json:"display_name"`
	Email        string `json:"email"`
	Password     string `json:"password"`
	ProjectTitle string `json:"project_title"`
}

type changePasswordRequest struct {
	CurrentPassword string `json:"current_password"`
	NewPassword     string `json:"new_password"`
}

type sessionAccessTokenResponse struct {
	AccessToken string    `json:"access_token"`
	TokenType   string    `json:"token_type"`
	ExpiresAt   time.Time `json:"expires_at"`
}

type startWriterRunResponse struct {
	RunID       string `json:"run_id"`
	TraceID     string `json:"trace_id"`
	ProjectID   string `json:"project_id"`
	Mode        string `json:"mode"`
	Instruction string `json:"instruction"`
	Status      string `json:"status"`
}

type characterInteractionEventsResponse struct {
	InteractionID string                         `json:"interaction_id"`
	AfterEventID  string                         `json:"after_event_id"`
	Items         []characterconsole.EventRecord `json:"items"`
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

type updateDraftReviewIssueRequest struct {
	Status  string `json:"status"`
	Version string `json:"version"`
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

type retrySeedSegmentsRequest struct {
	SegmentIDs []string `json:"segment_ids"`
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

type startWorldlineAutoEvolutionRequest struct {
	BodyTenantID string         `json:"tenant_id"`
	MaxSteps     int            `json:"max_steps"`
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

type startCharacterDialogueRequest struct {
	UserTurnID string `json:"user_turn_id"`
}

type adoptCharacterProposalRequest struct {
	Note string `json:"note"`
}

type characterProposalsResponse struct {
	InteractionID string                            `json:"interaction_id"`
	Items         []characterconsole.ProposalRecord `json:"items"`
}

type updateCharacterInteractionStatusRequest struct {
	BodyTenantID string `json:"tenant_id"`
	Status       string `json:"status"`
}

type convertCharacterInteractionToChapterDraftRequest struct {
	BodyTenantID      string   `json:"tenant_id"`
	TargetChapterID   string   `json:"target_chapter_id"`
	TargetSceneID     string   `json:"target_scene_id"`
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
	BodyTenantID string                           `json:"tenant_id"`
	Goal         string                           `json:"goal"`
	AnchorPathID string                           `json:"anchor_path_id"`
	AgentRefs    []worldline.PreparationAgentRef  `json:"agent_refs"`
	SourceRefs   []worldline.PreparationSourceRef `json:"source_refs"`
	Options      map[string]any                   `json:"options"`
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
	Name                  string `json:"name"`
	Provider              string `json:"provider"`
	BaseURL               string `json:"base_url"`
	APIKey                string `json:"api_key"`
	MaxConcurrency        int    `json:"max_concurrency"`
	ExternalProviderOptIn bool   `json:"external_provider_opt_in"`
	Enabled               *bool  `json:"enabled"`
}

type patchLLMChannelRequest struct {
	Name                  string `json:"name"`
	BaseURL               string `json:"base_url"`
	APIKey                string `json:"api_key"`
	MaxConcurrency        int    `json:"max_concurrency"`
	ExternalProviderOptIn bool   `json:"external_provider_opt_in"`
	Enabled               *bool  `json:"enabled"`
}

type patchLLMChannelModelRequest struct {
	ContextWindow *int     `json:"context_window"`
	SupportsTools *bool    `json:"supports_tools"`
	SupportsJSON  *bool    `json:"supports_json"`
	InputCost     *float64 `json:"input_cost"`
	OutputCost    *float64 `json:"output_cost"`
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
	ProjectID string               `json:"project_id"`
	Query     string               `json:"query"`
	Mode      string               `json:"mode"`
	Filters   assets.SearchFilters `json:"filters"`
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

type adoptStoryGraphCandidateRequest struct {
	BodyTenantID  string `json:"tenant_id"`
	BodyProjectID string `json:"project_id"`
	TargetKind    string `json:"target_kind"`
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
	writerThreadStore := config.WriterThreadStore
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
	seedSegmentRetrier := config.SeedSegmentRetrier
	if seedSegmentRetrier == nil {
		seedSegmentRetrier = workflows.NewDisabledSeedSegmentRetrier()
	}
	seedStarter := config.SeedStarter
	if seedStarter == nil {
		seedStarter = workflows.NewDisabledSeedRunStarter()
	}
	seedRunReader := config.SeedRunReader
	if seedRunReader == nil {
		seedRunReader = workflows.NewDisabledSeedRunReader()
	}
	analysisStarter := config.AnalysisStarter
	if analysisStarter == nil {
		analysisStarter = workflows.NewFailClosedAnalysisStarter()
	}
	analysisRunReader := config.AnalysisRunReader
	if analysisRunReader == nil {
		if reader, ok := analysisStarter.(workflows.AnalysisRunReader); ok {
			analysisRunReader = reader
		} else {
			analysisRunReader = &disabledAnalysisRunReader{}
		}
	}
	analysisEventReader := config.AnalysisEventReader
	if analysisEventReader == nil {
		if reader, ok := analysisStarter.(workflows.AnalysisEventReader); ok {
			analysisEventReader = reader
		} else {
			analysisEventReader = workflows.NewDisabledAnalysisEventReader()
		}
	}
	analysisCanceller := config.AnalysisCanceller
	if analysisCanceller == nil {
		if canceller, ok := analysisStarter.(workflows.AnalysisCanceller); ok {
			analysisCanceller = canceller
		} else {
			analysisCanceller = workflows.NewDisabledAnalysisCanceller()
		}
	}
	analysisWorkspaceReader := config.AnalysisWorkspaceReader
	if analysisWorkspaceReader == nil {
		if reader, ok := analysisStarter.(workflows.AnalysisWorkspaceReader); ok {
			analysisWorkspaceReader = reader
		} else {
			analysisWorkspaceReader = workflows.NewDisabledAnalysisWorkspaceReader()
		}
	}
	analysisCandidateReader := config.AnalysisCandidateReader
	if analysisCandidateReader == nil {
		analysisCandidateReader = workflows.NewDisabledAnalysisCandidateReader()
	}
	analysisAssetImporter := config.AnalysisAssetImporter
	if analysisAssetImporter == nil {
		analysisAssetImporter = workflows.NewDisabledAnalysisAssetImporter()
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
	llmModelStore := config.LLMModelStore
	if llmModelStore == nil {
		if store, ok := llmChannelStore.(llm.ModelStore); ok {
			llmModelStore = store
		} else {
			llmModelStore = llm.NewDisabledModelStore()
		}
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
	storyGraphCandidateAdoptionStore := config.StoryGraphCandidateAdoptionStore
	if storyGraphCandidateAdoptionStore == nil {
		storyGraphCandidateAdoptionStore = storygraph.NewDisabledCandidateAdoptionStore()
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
	worldlineAutoEvolutionStarter := config.WorldlineAutoEvolutionStarter
	if worldlineAutoEvolutionStarter == nil {
		worldlineAutoEvolutionStarter = worldline.NewDisabledAutoEvolutionStarter()
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
	worldlinePreparationStarter := config.WorldlinePreparationStarter
	if worldlinePreparationStarter == nil {
		worldlinePreparationStarter = worldline.NewDisabledPreparationStarter()
	}
	worldlinePreparationStore := config.WorldlinePreparationStore
	if worldlinePreparationStore == nil {
		worldlinePreparationStore = worldline.NewDisabledPreparationStore()
	}
	characterConsoleStore := config.CharacterConsoleStore
	if characterConsoleStore == nil {
		characterConsoleStore = characterconsole.NewDisabledStore()
	}
	characterProposalStore := config.CharacterProposalStore
	if characterProposalStore == nil {
		characterProposalStore = characterconsole.NewDisabledProposalStore()
	}
	characterDialogueStarter := config.CharacterDialogueStarter
	if characterDialogueStarter == nil {
		characterDialogueStarter = workflows.NewDisabledCharacterDialogueStarter()
	}
	return &Server{
		sessionAuthSecret:                strings.TrimSpace(config.SessionAuthSecret),
		allowDevelopmentAuth:             config.AllowDevelopmentAuth,
		forceSecureSessionCookies:        config.ForceSecureSessionCookies,
		authReader:                       authReader,
		passwordAuthenticator:            config.PasswordAuthenticator,
		passwordChanger:                  config.PasswordChanger,
		registrationService:              config.RegistrationService,
		authSessionStore:                 config.AuthSessionStore,
		authorizer:                       authorizer,
		writerStarter:                    starter,
		writerReader:                     reader,
		writerEventReader:                writerEventReader,
		writerCanceller:                  writerCanceller,
		writerThreadStore:                writerThreadStore,
		draftAdoptionStore:               draftAdoptionStore,
		draftReviewStore:                 draftReviewStore,
		draftReviewOwnerLookup:           config.DraftReviewOwnerLookup,
		draftReviewIssueStore:            config.DraftReviewIssueStore,
		manuscriptReader:                 manuscriptReader,
		manuscriptArtifactExporter:       config.ManuscriptArtifactExporter,
		workflowReader:                   workflowReader,
		workflowEventReader:              workflowEventReader,
		workflowCanceller:                workflowCanceller,
		workflowRetrier:                  workflowRetrier,
		seedSegmentRetrier:               seedSegmentRetrier,
		seedStarter:                      seedStarter,
		seedRunReader:                    seedRunReader,
		analysisStarter:                  analysisStarter,
		analysisRunReader:                analysisRunReader,
		analysisEventReader:              analysisEventReader,
		analysisCanceller:                analysisCanceller,
		analysisWorkspaceReader:          analysisWorkspaceReader,
		analysisCandidateReader:          analysisCandidateReader,
		analysisAssetImporter:            analysisAssetImporter,
		projectOverviewReader:            projectOverviewReader,
		projectReadinessReader:           projectReadinessReader,
		agentHelloStarter:                helloStarter,
		llmResolver:                      llmResolver,
		llmModuleRegistry:                llmModuleRegistry,
		llmBindingStore:                  llmBindingStore,
		llmCatalogReader:                 llmCatalogReader,
		llmChannelStore:                  llmChannelStore,
		llmModelStore:                    llmModelStore,
		llmModelSyncer:                   llmModelSyncer,
		llmSettingsReader:                llmSettingsReader,
		llmTelemetryReader:               llmTelemetryReader,
		llmQuotaStore:                    config.LLMQuotaStore,
		assetQueryEmbeddingResolver:      config.AssetQueryEmbeddingResolver,
		assetSearchIndexChecker:          config.AssetSearchIndexChecker,
		traceReader:                      traceReader,
		traceAccessChecker:               traceAccessChecker,
		traceExportAuditor:               traceExportAuditor,
		sourceFileStore:                  sourceFileStore,
		sourceFileObjectWriter:           sourceFileObjectWriter,
		assetReader:                      assetReader,
		archiveMemoryReader:              archiveMemoryReader,
		archiveMemoryReviewStore:         archiveMemoryReviewStore,
		assetAdoptionStore:               assetAdoptionStore,
		assetMutationStore:               assetMutationStore,
		assetBulkActionStore:             assetBulkActionStore,
		assetIngestionStarter:            assetIngestionStarter,
		assetIngestionReader:             assetIngestionReader,
		assetReindexStarter:              assetReindexStarter,
		styleExtractionStarter:           styleExtractionStarter,
		styleExtractionReader:            styleExtractionReader,
		storyGraphBuildStarter:           storyGraphBuildStarter,
		storyGraphBondGenerationStarter:  storyGraphBondGenerationStarter,
		storyGraphReader:                 storyGraphReader,
		storyGraphCandidateAdoptionStore: storyGraphCandidateAdoptionStore,
		storyGraphEvidenceAccess:         storyGraphEvidenceAccess,
		worldlineSavedPathReader:         worldlineSavedPathReader,
		worldlineSavedPathStore:          worldlineSavedPathStore,
		worldlineSessionStarter:          worldlineSessionStarter,
		worldlineStepStarter:             worldlineStepStarter,
		worldlineAutoEvolutionStarter:    worldlineAutoEvolutionStarter,
		worldlineSessionReader:           worldlineSessionReader,
		worldlineTimelineReader:          worldlineTimelineReader,
		worldlineEventReader:             worldlineEventReader,
		worldlineEventAdoptionStore:      worldlineEventAdoptionStore,
		worldlineEventMutationStore:      worldlineEventMutationStore,
		worldlineVariableStore:           worldlineVariableStore,
		worldlinePreparationStarter:      worldlinePreparationStarter,
		worldlinePreparationStore:        worldlinePreparationStore,
		characterConsoleStore:            characterConsoleStore,
		characterProposalStore:           characterProposalStore,
		characterDialogueStarter:         characterDialogueStarter,
		writerWorkspaceHandler:           config.WriterWorkspaceHandler,
		manuscriptWorkspaceHandler:       config.ManuscriptWorkspaceHandler,
		manuscriptExportHandler:          config.ManuscriptExportHandler,
		assetCatalogHandler:              config.AssetCatalogHandler,
		assetDistillationHandler:         config.AssetDistillationHandler,
		distillationEnqueuer:             config.DistillationEnqueuer,
		authRecoveryHandler:              config.AuthRecoveryHandler,
		collaborationHandler:             config.CollaborationHandler,
		projectAdminHandler:              config.ProjectAdminHandler,
		llmAdminHandler:                  config.LLMAdminHandler,
		rateLimiter:                      config.RateLimiter,
		trustedClientProofVerifier:       config.TrustedClientProofVerifier,
		readinessChecker:                 config.ReadinessChecker,
	}
}

func ActorUserIDFromContext(ctx context.Context) (string, bool) {
	userID, ok := ctx.Value(actorUserIDContextKey{}).(string)
	userID = strings.TrimSpace(userID)
	return userID, ok && userID != ""
}

func RequestCSRFVerified(ctx context.Context) bool {
	verified, _ := ctx.Value(csrfVerifiedContextKey{}).(bool)
	return verified
}

func (s *Server) actorUserID(request *http.Request) string {
	if userID, ok := ActorUserIDFromContext(request.Context()); ok {
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
		return s.resolveSessionToken(request, token)
	}
	if cookie, err := request.Cookie(sessionCookieName); err == nil {
		return s.resolveSessionToken(request, cookie.Value)
	}
	if !s.allowDevelopmentAuth {
		return "", false
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
	userID, _, ok := s.verifySignedSessionToken(token)
	return userID, ok
}

func (s *Server) resolveSessionToken(request *http.Request, token string) (string, bool) {
	userID, tokenHash, ok := s.verifySignedSessionToken(token)
	if !ok {
		return "", false
	}
	if s.authSessionStore == nil {
		return userID, true
	}
	err := s.authSessionStore.ValidateSession(request.Context(), auth.ValidateSessionInput{
		UserID:    userID,
		TokenHash: tokenHash,
		Now:       time.Now().UTC(),
		RequestID: requestID(request),
	})
	if err != nil {
		return "", false
	}
	return userID, true
}

func (s *Server) verifySignedSessionToken(token string) (string, string, bool) {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	if secret == "" {
		return "", "", false
	}
	token = strings.TrimSpace(token)
	if strings.Count(token, ".") == 2 {
		return s.verifyJWTSessionToken(token)
	}
	parts := strings.Split(token, ":")
	if len(parts) == 3 && parts[0] == "v1" {
		userID := strings.TrimSpace(parts[1])
		if userID == "" {
			return "", "", false
		}
		signature, err := hex.DecodeString(parts[2])
		if err != nil {
			return "", "", false
		}
		if !hmac.Equal(signature, signSessionMessage(secret, "v1:"+userID)) {
			return "", "", false
		}
		return userID, hashSessionToken(token), true
	}
	if len(parts) != 4 || parts[0] != "v2" {
		return "", "", false
	}
	userID := strings.TrimSpace(parts[1])
	if userID == "" {
		return "", "", false
	}
	nonce := strings.TrimSpace(parts[2])
	if nonce == "" {
		return "", "", false
	}
	if _, err := hex.DecodeString(nonce); err != nil {
		return "", "", false
	}
	signature, err := hex.DecodeString(parts[3])
	if err != nil {
		return "", "", false
	}
	if !hmac.Equal(signature, signSessionMessage(secret, "v2:"+userID+":"+nonce)) {
		return "", "", false
	}
	return userID, hashSessionToken(token), true
}

type jwtSessionHeader struct {
	Algorithm string `json:"alg"`
	Type      string `json:"typ"`
}

type jwtSessionClaims struct {
	Issuer    string `json:"iss"`
	Audience  string `json:"aud"`
	Subject   string `json:"sub"`
	SessionID string `json:"sid"`
	IssuedAt  int64  `json:"iat"`
	ExpiresAt int64  `json:"exp"`
}

func (s *Server) signJWTSessionToken(userID string, sessionID string, issuedAt time.Time) (string, bool) {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	userID = strings.TrimSpace(userID)
	sessionID = strings.TrimSpace(sessionID)
	if secret == "" || userID == "" || sessionID == "" {
		return "", false
	}
	if issuedAt.IsZero() {
		issuedAt = time.Now().UTC()
	}
	header := jwtSessionHeader{Algorithm: "HS256", Type: "JWT"}
	claims := jwtSessionClaims{
		Issuer:    jwtSessionIssuer,
		Audience:  jwtSessionAudience,
		Subject:   userID,
		SessionID: sessionID,
		IssuedAt:  issuedAt.UTC().Unix(),
		ExpiresAt: issuedAt.UTC().Add(sessionTTL).Unix(),
	}
	headerPart, ok := encodeJWTPart(header)
	if !ok {
		return "", false
	}
	claimsPart, ok := encodeJWTPart(claims)
	if !ok {
		return "", false
	}
	signingInput := headerPart + "." + claimsPart
	signature := base64.RawURLEncoding.EncodeToString(signSessionMessage(secret, signingInput))
	return signingInput + "." + signature, true
}

func encodeJWTPart(value any) (string, bool) {
	payload, err := json.Marshal(value)
	if err != nil {
		return "", false
	}
	return base64.RawURLEncoding.EncodeToString(payload), true
}

func (s *Server) verifyJWTSessionToken(token string) (string, string, bool) {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	parts := strings.Split(token, ".")
	if secret == "" || len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
		return "", "", false
	}
	var header jwtSessionHeader
	if !decodeJWTPart(parts[0], &header) {
		return "", "", false
	}
	if header.Algorithm != "HS256" || header.Type != "JWT" {
		return "", "", false
	}
	var claims jwtSessionClaims
	if !decodeJWTPart(parts[1], &claims) {
		return "", "", false
	}
	userID := strings.TrimSpace(claims.Subject)
	sessionID := strings.TrimSpace(claims.SessionID)
	now := time.Now().UTC().Unix()
	if claims.Issuer != jwtSessionIssuer ||
		claims.Audience != jwtSessionAudience ||
		userID == "" ||
		sessionID == "" ||
		claims.IssuedAt <= 0 ||
		claims.IssuedAt > now+300 ||
		claims.ExpiresAt <= now {
		return "", "", false
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return "", "", false
	}
	signingInput := parts[0] + "." + parts[1]
	if !hmac.Equal(signature, signSessionMessage(secret, signingInput)) {
		return "", "", false
	}
	return userID, hashSessionToken(token), true
}

func decodeJWTPart(part string, value any) bool {
	payload, err := base64.RawURLEncoding.DecodeString(part)
	if err != nil {
		return false
	}
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value) == nil
}

func (s *Server) signSessionToken(userID string) (string, bool) {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	userID = strings.TrimSpace(userID)
	if secret == "" || userID == "" {
		return "", false
	}
	sessionID, ok := randomSessionID()
	if !ok {
		return "", false
	}
	message := "v2:" + userID + ":" + sessionID
	return message + ":" + hex.EncodeToString(signSessionMessage(secret, message)), true
}

func randomSessionID() (string, bool) {
	nonceBytes := make([]byte, 16)
	if _, err := rand.Read(nonceBytes); err != nil {
		return "", false
	}
	return hex.EncodeToString(nonceBytes), true
}

func signSessionMessage(secret string, message string) []byte {
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(message))
	return mac.Sum(nil)
}

func hashSessionToken(token string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(token)))
	return hex.EncodeToString(sum[:])
}

func (s *Server) sessionCSRFToken(tokenHash string) string {
	secret := strings.TrimSpace(s.sessionAuthSecret)
	tokenHash = strings.TrimSpace(tokenHash)
	if secret == "" || tokenHash == "" {
		return ""
	}
	return hex.EncodeToString(signSessionMessage(secret, "csrf:"+tokenHash))
}

func (s *Server) verifySessionCSRFToken(tokenHash string, presented string) bool {
	expected := s.sessionCSRFToken(tokenHash)
	presented = strings.TrimSpace(presented)
	if expected == "" || presented == "" {
		return false
	}
	expectedBytes, err := hex.DecodeString(expected)
	if err != nil {
		return false
	}
	presentedBytes, err := hex.DecodeString(presented)
	if err != nil {
		return false
	}
	return hmac.Equal(presentedBytes, expectedBytes)
}

type protectedRoute struct {
	name   string
	method string
	match  func(string) bool
}

var actorSensitiveRoutes = []protectedRoute{
	{name: "current user", method: http.MethodGet, match: pathEquals("/v1/me")},
	{name: "workflow run detail", method: http.MethodGet, match: isWorkflowRunDetailPath},
	{name: "workflow run events", method: http.MethodGet, match: isWorkflowRunEventsPath},
	{name: "seed run detail", method: http.MethodGet, match: isSeedRunDetailPath},
	{name: "seed run events", method: http.MethodGet, match: isSeedRunEventsPath},
	{name: "writer run detail", method: http.MethodGet, match: isWriterRunDetailPath},
	{name: "writer run events", method: http.MethodGet, match: isWriterRunEventsPath},
	{name: "workflow run cancel", method: http.MethodPost, match: isWorkflowRunCancelPath},
	{name: "workflow run retry", method: http.MethodPost, match: isWorkflowRunRetryPath},
	{name: "seed run cancel", method: http.MethodPost, match: isSeedRunCancelPath},
	{name: "seed run retry", method: http.MethodPost, match: isSeedRunRetryPath},
	{name: "seed segment retry", method: http.MethodPost, match: isSeedSegmentRetryPath},
	{name: "worldline session step", method: http.MethodPost, match: isWorldlineSessionStepPath},
	{name: "worldline session auto evolution", method: http.MethodPost, match: isWorldlineSessionAutoEvolutionPath},
	{name: "worldline session variables", method: http.MethodPost, match: isWorldlineSessionVariablesPath},
	{name: "worldline session saved paths", method: http.MethodPost, match: isWorldlineSessionSavedPathsPath},
	{name: "worldline session detail", method: http.MethodGet, match: isWorldlineSessionDetailPath},
	{name: "worldline session timeline", method: http.MethodGet, match: isWorldlineSessionTimelinePath},
	{name: "worldline session events", method: http.MethodGet, match: isWorldlineSessionEventsPath},
	{name: "worldline preparation detail", method: http.MethodGet, match: isWorldlinePreparationDetailPath},
	{name: "worldline preparation agents", method: http.MethodGet, match: isWorldlinePreparationAgentsPath},
	{name: "worldline event adoption", method: http.MethodPost, match: isWorldlineEventAdoptionPath},
	{name: "worldline event mutation", method: http.MethodPatch, match: isWorldlineEventMutationPath},
	{name: "character interaction turn", method: http.MethodPost, match: matchCharacterInteractionNestedPath("turns")},
	{name: "character interaction dialogue", method: http.MethodPost, match: matchCharacterInteractionNestedPath("dialogue")},
	{name: "character interaction chapter draft", method: http.MethodPost, match: matchCharacterInteractionNestedPath("chapter-drafts")},
	{name: "character interaction detail", method: http.MethodGet, match: isCharacterInteractionMutationPath},
	{name: "character interaction turns", method: http.MethodGet, match: matchCharacterInteractionNestedPath("turns")},
	{name: "character interaction events", method: http.MethodGet, match: matchCharacterInteractionNestedPath("events")},
	{name: "character interaction proposals", method: http.MethodGet, match: matchCharacterInteractionNestedPath("proposals")},
	{name: "character proposal adoption", method: http.MethodPost, match: isCharacterProposalAdoptionPath},
	{name: "source upload object", method: http.MethodPut, match: isUploadSourceObjectPath},
	{name: "source upload complete", method: http.MethodPost, match: isCompleteUploadPath},
	{name: "character interaction mutation", method: http.MethodPatch, match: isCharacterInteractionMutationPath},
	{name: "llm settings", method: http.MethodGet, match: pathEquals("/v1/llm/settings")},
	{name: "llm channel create", method: http.MethodPost, match: pathEquals("/v1/llm/channels")},
	{name: "llm channel model patch", method: http.MethodPatch, match: isLLMChannelModelMutationPath},
	{name: "llm channel patch", method: http.MethodPatch, match: isLLMChannelMutationPath},
	{name: "llm channel delete", method: http.MethodDelete, match: isLLMChannelMutationPath},
	{name: "llm channel sync", method: http.MethodPost, match: isLLMChannelSyncPath},
	{name: "tenant sessions revoke", method: http.MethodDelete, match: isTenantSessionsPath},
	{name: "writer run cancel", method: http.MethodPost, match: isWriterRunCancelPath},
	{name: "draft adoption", method: http.MethodPost, match: isDraftAdoptionPath},
	{name: "draft review", method: http.MethodPost, match: isDraftReviewPath},
	{name: "draft review list", method: http.MethodGet, match: isDraftReviewPath},
	{name: "draft review issue mutation", method: http.MethodPatch, match: isDraftReviewIssuePath},
	{name: "asset adoption", method: http.MethodPost, match: isAssetAdoptionPath},
	{name: "asset patch", method: http.MethodPatch, match: isAssetMutationPath},
	{name: "asset delete", method: http.MethodDelete, match: isAssetMutationPath},
	{name: "asset detail", method: http.MethodGet, match: isAssetDetailPath},
	{name: "asset bulk action", method: http.MethodPost, match: pathEquals("/v1/assets/bulk-actions")},
	{name: "asset search", method: http.MethodPost, match: pathEquals("/v1/assets/search")},
	{name: "archive memory adoption", method: http.MethodPost, match: isArchiveMemoryAdoptionPath},
	{name: "archive memory rejection", method: http.MethodPost, match: isArchiveMemoryRejectionPath},
}

var projectActorSensitiveRoutes = []protectedRoute{
	{name: "project overview", method: http.MethodGet, match: matchProjectSuffixPath("overview")},
	{name: "project readiness", method: http.MethodGet, match: matchProjectSuffixPath("readiness")},
	{name: "source file list", method: http.MethodGet, match: matchProjectSuffixPath("source-files")},
	{name: "asset list", method: http.MethodGet, match: matchProjectSuffixPath("assets")},
	{name: "asset facets", method: http.MethodGet, match: matchProjectSuffixPath("assets/facets")},
	{name: "worldline saved paths list", method: http.MethodGet, match: matchProjectSuffixPath("worldline/saved-paths")},
	{name: "worldline sessions list", method: http.MethodGet, match: matchProjectSuffixPath("worldline-sessions")},
	{name: "character interactions list", method: http.MethodGet, match: matchProjectSuffixPath("character-interactions")},
	{name: "story graph current", method: http.MethodGet, match: matchProjectSuffixPath("story-graph/current")},
	{name: "story graph view", method: http.MethodGet, match: matchStoryGraphPath("views")},
	{name: "story graph node", method: http.MethodGet, match: matchStoryGraphPath("nodes")},
	{name: "story graph edge", method: http.MethodGet, match: matchStoryGraphPath("edges")},
	{name: "story graph layout", method: http.MethodGet, match: matchStoryGraphPath("layouts")},
	{name: "story graph clusters", method: http.MethodGet, match: matchProjectSuffixPath("story-graph/clusters")},
	{name: "llm quota policies list", method: http.MethodGet, match: matchProjectSuffixPath("llm/quota-policies")},
	{name: "llm quota policies put", method: http.MethodPut, match: matchProjectSuffixPath("llm/quota-policies")},
	{name: "llm billing usage", method: http.MethodGet, match: matchProjectSuffixPath("llm/billing-usage")},
	{name: "llm modules", method: http.MethodGet, match: matchProjectSuffixPath("llm/modules")},
	{name: "llm module bindings", method: http.MethodGet, match: matchProjectSuffixPath("llm/module-bindings")},
	{name: "llm resolution", method: http.MethodGet, match: hasLLMResolutionPathShape},
	{name: "llm channels", method: http.MethodGet, match: matchProjectSuffixPath("llm/channels")},
	{name: "llm channel models", method: http.MethodGet, match: hasLLMChannelModelsPathShape},
	{name: "llm activity", method: http.MethodGet, match: matchProjectSuffixPath("llm/activity")},
	{name: "llm usage", method: http.MethodGet, match: matchProjectSuffixPath("llm/usage")},
	{name: "manuscript", method: http.MethodGet, match: matchProjectSuffixPath("manuscript")},
	{name: "manuscript export", method: http.MethodGet, match: matchProjectSuffixPath("manuscript/export")},
	{name: "seed run start", method: http.MethodPost, match: matchProjectSuffixPath("seed-runs")},
	{name: "upload create", method: http.MethodPost, match: matchProjectSuffixPath("uploads")},
	{name: "worldline session start", method: http.MethodPost, match: matchProjectSuffixPath("worldline-sessions")},
	{name: "worldline preparation list", method: http.MethodGet, match: matchProjectSuffixPath("worldlines/preparations")},
	{name: "worldline preparation create", method: http.MethodPost, match: matchProjectSuffixPath("worldlines/preparations")},
	{name: "character interaction create", method: http.MethodPost, match: matchProjectSuffixPath("character-interactions")},
	{name: "writer run start", method: http.MethodPost, match: matchProjectSuffixPath("writer-runs")},
	{name: "writer threads list", method: http.MethodGet, match: matchProjectSuffixPath("writer-threads")},
	{name: "writer thread ensure", method: http.MethodPost, match: matchProjectSuffixPath("writer-threads")},
	{name: "writer thread messages", method: http.MethodGet, match: hasWriterThreadMessagesPathShape},
	{name: "writer thread message append", method: http.MethodPost, match: hasWriterThreadMessagesPathShape},
	{name: "writer approval decide", method: http.MethodPost, match: hasWriterApprovalDecisionPathShape},
	{name: "hello agent start", method: http.MethodPost, match: matchProjectSuffixPath("agent-runtime/hello-runs")},
	{name: "asset create", method: http.MethodPost, match: matchProjectSuffixPath("assets")},
	{name: "asset ingestion start", method: http.MethodPost, match: matchProjectSuffixPath("asset-ingestions")},
	{name: "style extraction start", method: http.MethodPost, match: matchProjectSuffixPath("style-extractions")},
	{name: "asset search capabilities", method: http.MethodGet, match: matchProjectSuffixPath("assets/search-capabilities")},
	{name: "asset reindex start", method: http.MethodPost, match: matchProjectSuffixPath("assets/reindex")},
	{name: "story graph build start", method: http.MethodPost, match: matchProjectSuffixPath("story-graph/builds")},
	{name: "story graph bond generation start", method: http.MethodPost, match: matchProjectSuffixPath("story-graph/bond-generations")},
	{name: "story graph candidate adoption", method: http.MethodPost, match: hasStoryGraphCandidateAdoptionPathShape},
	{name: "story graph evidence", method: http.MethodGet, match: hasStoryGraphEvidencePathShape},
	{name: "llm module binding put", method: http.MethodPut, match: hasLLMModuleBindingPathShape},
	{name: "llm module binding delete", method: http.MethodDelete, match: hasLLMModuleBindingPathShape},
	{name: "trace events", method: http.MethodGet, match: hasTraceEventsPathShape},
	{name: "trace export", method: http.MethodPost, match: hasTraceExportPathShape},
}

func pathEquals(expected string) func(string) bool {
	return func(path string) bool {
		return path == expected
	}
}

func matchProjectSuffixPath(suffix string) func(string) bool {
	return func(path string) bool {
		return hasProjectSuffixPathShape(path, suffix)
	}
}

func matchStoryGraphPath(kind string) func(string) bool {
	return func(path string) bool {
		return hasStoryGraphPathShape(path, kind)
	}
}

func matchCharacterInteractionNestedPath(expectedSuffix string) func(string) bool {
	return func(path string) bool {
		return isCharacterInteractionNestedPath(path, expectedSuffix)
	}
}

func matchesProtectedRoute(routes []protectedRoute, method string, path string) bool {
	for _, route := range routes {
		if route.method == method && route.match(path) {
			return true
		}
	}
	return false
}

func unsafeActorSensitiveCookieRequest(request *http.Request) bool {
	if !isActorSensitiveRoute(request) {
		return false
	}
	switch request.Method {
	case http.MethodGet, http.MethodHead, http.MethodOptions:
		return false
	}
	if len(request.Header.Values("Authorization")) > 0 {
		return false
	}
	if _, err := request.Cookie(sessionCookieName); err == nil {
		return true
	}
	return false
}

func (s *Server) verifyUnsafeActorSensitiveCookieCSRF(response http.ResponseWriter, request *http.Request) bool {
	if !unsafeActorSensitiveCookieRequest(request) {
		return true
	}
	cookie, err := request.Cookie(sessionCookieName)
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		return true
	}
	_, tokenHash, ok := s.verifySignedSessionToken(cookie.Value)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return false
	}
	if !s.verifySessionCSRFToken(tokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return true
}

func isActorSensitiveRoute(request *http.Request) bool {
	return matchesProtectedRoute(actorSensitiveRoutes, request.Method, request.URL.Path) ||
		projectActorSensitiveRoute(request) ||
		isWriterWorkspaceRoute(request.Method, request.URL.Path) ||
		isManuscriptWorkspaceRoute(request.Method, request.URL.Path) ||
		isManuscriptExportDownloadRoute(request.Method, request.URL.Path) ||
		isAssetCatalogRoute(request.Method, request.URL.Path) ||
		isAssetDistillationRoute(request.Method, request.URL.Path) ||
		isCollaborationRoute(request.Method, request.URL.Path) ||
		isProjectAdminRoute(request.Method, request.URL.Path) ||
		isLLMAdminRoute(request.Method, request.URL.Path)
}

func isProjectAdminRoute(method string, path string) bool {
	return projectadmin.IsRoute(method, path)
}

func isAssetDistillationRoute(method string, path string) bool {
	return assetdistillation.IsRoute(method, path)
}

func isAuthRecoveryRoute(method string, path string) bool {
	return method == http.MethodPost &&
		(path == "/v1/auth/recovery/request" || path == "/v1/auth/recovery/reset")
}

func isCollaborationRoute(method string, path string) bool {
	parts := canonicalPathSegments(path)
	if len(parts) == 4 && parts[0] == "v1" && parts[1] == "collaboration" && parts[2] == "invitations" && parts[3] == "accept" {
		return method == http.MethodPost
	}
	if len(parts) < 4 || parts[0] != "v1" || parts[1] != "tenants" {
		return false
	}
	switch {
	case len(parts) == 4 && parts[3] == "invitations":
		return method == http.MethodGet || method == http.MethodPost
	case len(parts) == 5 && parts[3] == "invitations":
		return method == http.MethodDelete
	case len(parts) == 6 && parts[3] == "invitations" && parts[5] == "resend":
		return method == http.MethodPost
	case len(parts) == 4 && parts[3] == "members":
		return method == http.MethodGet
	case len(parts) == 5 && parts[3] == "members":
		return method == http.MethodPatch || method == http.MethodDelete
	case len(parts) == 6 && parts[3] == "projects" && parts[5] == "members":
		return method == http.MethodGet
	case len(parts) == 7 && parts[3] == "projects" && parts[5] == "members":
		return method == http.MethodPatch || method == http.MethodDelete
	default:
		return false
	}
}

func isLLMAdminRoute(method string, path string) bool {
	parts := canonicalPathSegments(path)
	if len(parts) < 3 || parts[0] != "v1" || parts[1] != "llm-admin" {
		return false
	}
	switch {
	case len(parts) == 3 && parts[2] == "policies":
		return method == http.MethodGet || method == http.MethodPost
	case len(parts) == 4 && parts[2] == "policies":
		return method == http.MethodPut || method == http.MethodDelete
	case len(parts) == 3 && (parts[2] == "resolution" || parts[2] == "reservations" || parts[2] == "reconciliation"):
		return method == http.MethodGet
	case len(parts) == 3 && parts[2] == "provider-health":
		return method == http.MethodPost
	default:
		return false
	}
}

func isWriterWorkspaceRoute(method string, path string) bool {
	parts := canonicalPathSegments(path)
	if len(parts) < 3 || parts[0] != "v1" {
		return false
	}
	if len(parts) >= 4 && parts[1] == "projects" {
		switch parts[3] {
		case "chapters":
			return (len(parts) == 4 && (method == http.MethodGet || method == http.MethodPost)) ||
				(len(parts) == 5 && parts[4] == "reorder" && method == http.MethodPost)
		case "book-plans":
			return (len(parts) == 4 && (method == http.MethodGet || method == http.MethodPost)) ||
				(len(parts) == 6 && parts[4] != "" && parts[5] == "generations" && method == http.MethodPost)
		case "outlines", "writer-presets", "forbidden-lexicon":
			return len(parts) == 4 && (method == http.MethodGet || method == http.MethodPost)
		}
	}
	if len(parts) == 4 && parts[1] == "tenants" && parts[3] == "writer-presets" {
		return method == http.MethodGet || method == http.MethodPost
	}
	switch parts[1] {
	case "chapters":
		return (len(parts) == 3 && (method == http.MethodGet || method == http.MethodPatch || method == http.MethodDelete)) ||
			(len(parts) == 4 && parts[3] == "versions" && method == http.MethodGet) ||
			(len(parts) == 4 && parts[3] == "scenes" && (method == http.MethodGet || method == http.MethodPost)) ||
			(len(parts) == 5 && parts[3] == "scenes" && parts[4] == "reorder" && method == http.MethodPost)
	case "scenes":
		return (len(parts) == 3 && (method == http.MethodGet || method == http.MethodPatch || method == http.MethodDelete)) ||
			(len(parts) == 4 && parts[3] == "versions" && method == http.MethodGet)
	case "outline-versions":
		return len(parts) == 4 && parts[3] == "restore" && method == http.MethodPost
	case "book-plans":
		return (len(parts) == 3 && (method == http.MethodGet || method == http.MethodPatch || method == http.MethodDelete)) ||
			(len(parts) == 4 && parts[3] == "events" && (method == http.MethodGet || method == http.MethodPost)) ||
			(len(parts) == 4 && parts[3] == "runs" && method == http.MethodPost)
	case "writer-presets", "forbidden-lexicon":
		return len(parts) == 3 && (method == http.MethodPatch || method == http.MethodDelete)
	default:
		return false
	}
}

func isManuscriptWorkspaceRoute(method string, path string) bool {
	parts := canonicalPathSegments(path)
	if len(parts) < 5 || parts[0] != "v1" || parts[1] != "projects" || parts[3] != "manuscript-workspace" {
		return false
	}
	switch parts[4] {
	case "blocks":
		return (len(parts) == 5 && (method == http.MethodGet || method == http.MethodPost)) ||
			(len(parts) == 6 && parts[5] == "reorder" && method == http.MethodPost) ||
			(len(parts) == 6 && (method == http.MethodGet || method == http.MethodPatch || method == http.MethodDelete)) ||
			(len(parts) == 7 && parts[6] == "move" && method == http.MethodPost) ||
			(len(parts) == 7 && parts[6] == "tags" && method == http.MethodPut) ||
			(len(parts) == 7 && parts[6] == "versions" && method == http.MethodGet) ||
			(len(parts) == 8 && parts[6] == "versions" && method == http.MethodGet) ||
			(len(parts) == 9 && parts[6] == "versions" && parts[8] == "restore" && method == http.MethodPost)
	case "commands":
		return (len(parts) == 5 && method == http.MethodPost) || (len(parts) == 6 && method == http.MethodGet)
	case "exports":
		return len(parts) == 5 && (method == http.MethodGet || method == http.MethodPost)
	case "dedup-extractions":
		return len(parts) == 5 && method == http.MethodPost
	case "dedup-patterns":
		return (len(parts) == 5 && method == http.MethodGet) ||
			(len(parts) == 7 && (parts[6] == "accept" || parts[6] == "reject") && method == http.MethodPost)
	default:
		return false
	}
}

func isAssetCatalogRoute(_ string, path string) bool {
	parts := canonicalPathSegments(path)
	return len(parts) >= 5 && parts[0] == "v1" && parts[1] == "projects" && parts[2] != "" && parts[3] == "asset-catalog"
}

func isManuscriptExportDownloadRoute(method string, path string) bool {
	parts := canonicalPathSegments(path)
	return method == http.MethodGet && len(parts) == 7 && parts[0] == "v1" && parts[1] == "projects" &&
		parts[2] != "" && parts[3] == "manuscript" && parts[4] == "exports" && parts[5] != "" && parts[6] == "download"
}

func canonicalPathSegments(path string) []string {
	if path == "" || path == "/" || strings.Contains(path, "//") || strings.HasSuffix(path, "/") {
		return nil
	}
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	for _, part := range parts {
		if strings.TrimSpace(part) == "" {
			return nil
		}
	}
	return parts
}

func isAssetDetailPath(path string) bool {
	return singleAssetPathPart(path) != ""
}

func isAssetMutationPath(path string) bool {
	return singleAssetPathPart(path) != ""
}

func isAssetAdoptionPath(path string) bool {
	return assetAdoptionPathPart(path) != ""
}

func singleAssetPathPart(path string) string {
	assetID := strings.TrimSpace(strings.TrimPrefix(path, "/v1/assets/"))
	if assetID == "" || assetID == path || strings.Contains(assetID, "/") || isReservedAssetPathPart(assetID) {
		return ""
	}
	return assetID
}

func isReservedAssetPathPart(assetID string) bool {
	switch assetID {
	case "search", "bulk-actions":
		return true
	default:
		return false
	}
}

func isTenantSessionsPath(path string) bool {
	return tenantSessionsPathPart(path) != ""
}

func tenantSessionsPathPart(path string) string {
	const prefix = "/v1/tenants/"
	const suffix = "/sessions"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	tenantID := strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix)
	tenantID = strings.TrimSpace(tenantID)
	if tenantID == "" || strings.Contains(tenantID, "/") {
		return ""
	}
	return tenantID
}

func isWorldlineSessionDetailPath(path string) bool {
	return worldlineSessionPathPart(path, "") != ""
}

func isWorldlineSessionTimelinePath(path string) bool {
	return worldlineSessionPathPart(path, "timeline") != ""
}

func isWorldlineSessionEventsPath(path string) bool {
	return worldlineSessionPathPart(path, "events") != ""
}

func isWorldlineSessionStepPath(path string) bool {
	return worldlineSessionPathPart(path, "steps") != ""
}

func isWorldlineSessionAutoEvolutionPath(path string) bool {
	return worldlineSessionPathPart(path, "auto-evolutions") != ""
}

func isWorldlineSessionVariablesPath(path string) bool {
	return worldlineSessionPathPart(path, "variables") != ""
}

func isWorldlineSessionSavedPathsPath(path string) bool {
	return worldlineSessionPathPart(path, "saved-paths") != ""
}

func isWorldlineEventAdoptionPath(path string) bool {
	return worldlineEventAdoptionPathPart(path) != ""
}

func isWorldlineEventMutationPath(path string) bool {
	return worldlineEventPathPart(path) != ""
}

func isWorldlinePreparationDetailPath(path string) bool {
	return worldlinePreparationPathPart(path, "") != ""
}

func isWorldlinePreparationAgentsPath(path string) bool {
	return worldlinePreparationPathPart(path, "agents") != ""
}

func worldlineSessionPathPart(path string, suffix string) string {
	const prefix = "/v1/worldline-sessions/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	sessionID := strings.TrimPrefix(path, prefix)
	if sessionID == "" {
		return ""
	}
	if suffix != "" {
		expectedSuffix := "/" + suffix
		if !strings.HasSuffix(sessionID, expectedSuffix) {
			return ""
		}
		sessionID = strings.TrimSuffix(sessionID, expectedSuffix)
	}
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" || strings.Contains(sessionID, "/") {
		return ""
	}
	return sessionID
}

func worldlinePreparationPathPart(path string, suffix string) string {
	const prefix = "/v1/worldline-preparations/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	prepareID := strings.TrimPrefix(path, prefix)
	if prepareID == "" {
		return ""
	}
	if suffix != "" {
		expectedSuffix := "/" + suffix
		if !strings.HasSuffix(prepareID, expectedSuffix) {
			return ""
		}
		prepareID = strings.TrimSuffix(prepareID, expectedSuffix)
	}
	prepareID = strings.TrimSpace(prepareID)
	if prepareID == "" || strings.Contains(prepareID, "/") {
		return ""
	}
	return prepareID
}

func worldlineEventAdoptionPathPart(path string) string {
	const prefix = "/v1/worldline-events/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	remainder := strings.TrimPrefix(path, prefix)
	eventID, suffix, ok := strings.Cut(remainder, "/")
	eventID = strings.TrimSpace(eventID)
	if !ok || suffix != "adoptions" || eventID == "" || strings.Contains(eventID, "/") {
		return ""
	}
	return eventID
}

func worldlineEventPathPart(path string) string {
	const prefix = "/v1/worldline-events/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	eventID := strings.TrimSpace(strings.TrimPrefix(path, prefix))
	if eventID == "" || strings.Contains(eventID, "/") {
		return ""
	}
	return eventID
}

func isCharacterInteractionNestedPath(path string, expectedSuffix string) bool {
	return characterInteractionNestedPathPart(path, expectedSuffix) != ""
}

func isCharacterInteractionMutationPath(path string) bool {
	return characterInteractionPathPart(path) != ""
}

func projectActorSensitiveRoute(request *http.Request) bool {
	path := request.URL.Path
	if !strings.HasPrefix(path, "/v1/projects/") {
		return false
	}
	return matchesProtectedRoute(projectActorSensitiveRoutes, request.Method, path)
}

func hasStoryGraphPathShape(path string, kind string) bool {
	projectID, itemID := storyGraphPathParts(path, kind)
	return isSinglePathSegment(projectID) && isSinglePathSegment(itemID)
}

func hasStoryGraphEvidencePathShape(path string) bool {
	projectID, ownerType, ownerID := storyGraphEvidencePathParts(path)
	return isSinglePathSegment(projectID) && (ownerType == "node" || ownerType == "edge") && isSinglePathSegment(ownerID)
}

func hasStoryGraphEvidencePathShapeFor(path string, expectedOwnerType string) bool {
	projectID, ownerType, ownerID := storyGraphEvidencePathParts(path)
	return isSinglePathSegment(projectID) && ownerType == expectedOwnerType && isSinglePathSegment(ownerID)
}

func hasStoryGraphCandidateAdoptionPathShape(path string) bool {
	projectID, assetID := storyGraphCandidateAdoptionPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(assetID)
}

func hasLLMResolutionPathShape(path string) bool {
	projectID, moduleKey := llmResolutionPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(moduleKey)
}

func hasLLMModuleBindingPathShape(path string) bool {
	projectID, moduleKey := llmModuleBindingPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(moduleKey)
}

func hasLLMChannelModelsPathShape(path string) bool {
	projectID, channelID := llmChannelModelsPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(channelID)
}

func hasTraceEventsPathShape(path string) bool {
	projectID, traceID := traceEventsPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(traceID)
}

func hasTraceExportPathShape(path string) bool {
	projectID, traceID := traceExportPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(traceID)
}

func hasProjectSuffixPathShape(path string, suffix string) bool {
	return isSinglePathSegment(projectIDFromPathWithSuffix(path, suffix))
}

func isWorkflowRunDetailPath(path string) bool {
	return workflowRunPathPart(path) != ""
}

func isWorkflowRunEventsPath(path string) bool {
	return workflowRunEventsPathPart(path) != ""
}

func isSeedRunDetailPath(path string) bool {
	return seedRunPathPart(path) != ""
}

func isSeedRunEventsPath(path string) bool {
	return seedRunEventsPathPart(path) != ""
}

func isSeedRunCancelPath(path string) bool {
	return seedRunCancelPathPart(path) != ""
}

func isSeedRunRetryPath(path string) bool {
	return seedRunRetryPathPart(path) != ""
}

func isSeedSegmentRetryPath(path string) bool {
	return seedSegmentRetryPathPart(path) != ""
}

func isWriterRunDetailPath(path string) bool {
	return writerRunPathPart(path) != ""
}

func isWriterRunEventsPath(path string) bool {
	return writerRunEventsPathPart(path) != ""
}

func isWriterRunCancelPath(path string) bool {
	return writerRunCancelPathPart(path) != ""
}

func hasWriterThreadMessagesPathShape(path string) bool {
	projectID, threadID := writerThreadMessagesPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(threadID)
}

func hasWriterApprovalDecisionPathShape(path string) bool {
	projectID, approvalID := writerApprovalDecisionPathParts(path)
	return isSinglePathSegment(projectID) && isSinglePathSegment(approvalID)
}

func isWorkflowRunCancelPath(path string) bool {
	return workflowRunCancelPathPart(path) != ""
}

func isWorkflowRunRetryPath(path string) bool {
	return workflowRunRetryPathPart(path) != ""
}

func isSinglePathSegment(value string) bool {
	value = strings.TrimSpace(value)
	return value != "" && !strings.Contains(value, "/")
}

func (s *Server) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if !s.verifyUnsafeActorSensitiveCookieCSRF(response, request) {
		return
	}
	request = request.WithContext(context.WithValue(request.Context(), csrfVerifiedContextKey{}, true))
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
	case request.Method == http.MethodGet && request.URL.Path == "/readyz":
		s.handleReadiness(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/login":
		s.handlePasswordLogin(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/signup":
		s.handleSignup(response, request)
	case isAuthRecoveryRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.authRecoveryHandler, "AUTH_RECOVERY_BACKEND_UNCONFIGURED")
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/password/change":
		s.handleChangePassword(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/dev-sessions":
		s.handleCreateDevSession(response, request)
	case request.Method == http.MethodGet && request.URL.Path == "/v1/auth/csrf-token":
		s.handleGetSessionCSRFToken(response, request)
	case request.Method == http.MethodGet && request.URL.Path == "/v1/auth/sessions":
		s.handleListCurrentUserSessions(response, request)
	case request.Method == http.MethodDelete && request.URL.Path == "/v1/auth/session":
		s.handleRevokeCurrentSession(response, request)
	case request.Method == http.MethodDelete && request.URL.Path == "/v1/auth/sessions":
		s.handleRevokeAllCurrentUserSessions(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/session/jwt-refresh":
		s.handleRefreshJWTBearerSession(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/session/access-token":
		s.handleCreateCurrentSessionAccessToken(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/session/jwt-rotation":
		s.handleRotateCurrentSessionToJWT(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/auth/session/rotation":
		s.handleRotateCurrentSession(response, request)
	case request.Method == http.MethodDelete && isTenantSessionsPath(request.URL.Path):
		s.handleRevokeTenantSessions(response, request)
	case request.Method == http.MethodGet && request.URL.Path == "/v1/me":
		s.handleGetCurrentUser(response, request)
	case request.Method == http.MethodGet && isWorkflowRunEventsPath(request.URL.Path):
		s.handleListWorkflowRunEvents(response, request)
	case request.Method == http.MethodPost && isWorkflowRunCancelPath(request.URL.Path):
		s.handleCancelWorkflowRun(response, request)
	case request.Method == http.MethodPost && isWorkflowRunRetryPath(request.URL.Path):
		s.handleRetryWorkflowRun(response, request)
	case request.Method == http.MethodGet && isWorkflowRunDetailPath(request.URL.Path):
		s.handleGetWorkflowRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/seed-runs"):
		s.handleStartSeedRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/seed-runs"):
		s.handleListSeedRuns(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/analysis-runs"):
		s.handleStartAnalysisRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/analysis-runs"):
		s.handleListAnalysisRuns(response, request)
	case request.Method == http.MethodGet && isAnalysisRunEventsPath(request.URL.Path):
		s.handleListAnalysisRunEvents(response, request)
	case request.Method == http.MethodPost && isAnalysisRunCancelPath(request.URL.Path):
		s.handleCancelAnalysisRun(response, request)
	case request.Method == http.MethodGet && isAnalysisWorkspaceFilePath(request.URL.Path):
		s.handleGetAnalysisWorkspaceFile(response, request)
	case request.Method == http.MethodGet && isAnalysisWorkspaceFilesPath(request.URL.Path):
		s.handleListAnalysisWorkspaceFiles(response, request)
	case request.Method == http.MethodGet && isAnalysisCandidatesPath(request.URL.Path):
		s.handleListAnalysisCandidates(response, request)
	case request.Method == http.MethodPost && isAnalysisAssetsImportPath(request.URL.Path):
		s.handleImportAnalysisAssets(response, request)
	case request.Method == http.MethodGet && isAnalysisRunDetailPath(request.URL.Path):
		s.handleGetAnalysisRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/readiness"):
		s.handleGetProjectReadiness(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/overview"):
		s.handleGetProjectOverview(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/manuscript/export"):
		s.handleGetManuscriptExport(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/manuscript"):
		s.handleGetManuscript(response, request)
	case request.Method == http.MethodGet && isSeedRunEventsPath(request.URL.Path):
		s.handleListSeedRunEvents(response, request)
	case request.Method == http.MethodPost && isSeedRunCancelPath(request.URL.Path):
		s.handleCancelSeedRun(response, request)
	case request.Method == http.MethodPost && isSeedRunRetryPath(request.URL.Path):
		s.handleRetrySeedRun(response, request)
	case request.Method == http.MethodPost && isSeedSegmentRetryPath(request.URL.Path):
		s.handleRetrySeedSegments(response, request)
	case request.Method == http.MethodGet && isSeedRunDetailPath(request.URL.Path):
		s.handleGetSeedRun(response, request)
	case request.Method == http.MethodPost && hasProjectSuffixPathShape(request.URL.Path, "uploads"):
		s.handleCreateUpload(response, request)
	case request.Method == http.MethodPut && isUploadSourceObjectPath(request.URL.Path):
		s.handleUploadSourceObject(response, request)
	case request.Method == http.MethodPost && isCompleteUploadPath(request.URL.Path):
		s.handleCompleteUpload(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/source-files"):
		s.handleListSourceFiles(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets/facets"):
		s.handleListAssetFacets(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets"):
		s.handleCreateAsset(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets"):
		s.handleListAssets(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets/search-capabilities"):
		s.handleGetAssetSearchCapabilities(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/assets/reindex"):
		s.handleStartAssetReindex(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/builds"):
		s.handleStartStoryGraphBuild(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/bond-generations"):
		s.handleStartStoryGraphBondGeneration(response, request)
	case request.Method == http.MethodPost && hasStoryGraphCandidateAdoptionPathShape(request.URL.Path):
		s.handleAdoptStoryGraphCandidate(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/current"):
		s.handleGetStoryGraphCurrent(response, request)
	case request.Method == http.MethodGet && hasStoryGraphPathShape(request.URL.Path, "views"):
		s.handleGetStoryGraphView(response, request)
	case request.Method == http.MethodGet && hasStoryGraphEvidencePathShapeFor(request.URL.Path, "node"):
		s.handleGetStoryGraphEvidence(response, request)
	case request.Method == http.MethodGet && hasStoryGraphEvidencePathShapeFor(request.URL.Path, "edge"):
		s.handleGetStoryGraphEvidence(response, request)
	case request.Method == http.MethodGet && hasStoryGraphPathShape(request.URL.Path, "layouts"):
		s.handleGetStoryGraphLayout(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/story-graph/clusters"):
		s.handleListStoryGraphClusters(response, request)
	case request.Method == http.MethodGet && hasStoryGraphPathShape(request.URL.Path, "nodes"):
		s.handleGetStoryGraphNode(response, request)
	case request.Method == http.MethodGet && hasStoryGraphPathShape(request.URL.Path, "edges"):
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
	case request.Method == http.MethodPost && isArchiveMemoryAdoptionPath(request.URL.Path):
		s.handleAdoptArchiveMemory(response, request)
	case request.Method == http.MethodPost && isArchiveMemoryRejectionPath(request.URL.Path):
		s.handleRejectArchiveMemory(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/assets/") && strings.HasSuffix(request.URL.Path, "/adoptions"):
		s.handleAdoptAsset(response, request)
	case request.Method == http.MethodPatch && strings.HasPrefix(request.URL.Path, "/v1/assets/"):
		s.handlePatchAsset(response, request)
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/v1/assets/"):
		s.handleDeleteAsset(response, request)
	case request.Method == http.MethodGet && isAssetDetailPath(request.URL.Path):
		s.handleGetAsset(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline-sessions"):
		s.handleStartWorldlineSession(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline-sessions"):
		s.handleListWorldlineSessions(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldlines/preparations"):
		s.handleListWorldlinePreparations(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldlines/preparations"):
		s.handleCreateWorldlinePreparation(response, request)
	case request.Method == http.MethodGet && isWorldlinePreparationAgentsPath(request.URL.Path):
		s.handleListWorldlinePreparedAgents(response, request)
	case request.Method == http.MethodGet && isWorldlinePreparationDetailPath(request.URL.Path):
		s.handleGetWorldlinePreparation(response, request)
	case request.Method == http.MethodGet && isWorldlineSessionTimelinePath(request.URL.Path):
		s.handleListWorldlineTimeline(response, request)
	case request.Method == http.MethodGet && isWorldlineSessionEventsPath(request.URL.Path):
		s.handleListWorldlineEvents(response, request)
	case request.Method == http.MethodPost && isWorldlineSessionStepPath(request.URL.Path):
		s.handleStartWorldlineStep(response, request)
	case request.Method == http.MethodPost && isWorldlineSessionAutoEvolutionPath(request.URL.Path):
		s.handleStartWorldlineAutoEvolution(response, request)
	case request.Method == http.MethodPost && isWorldlineEventAdoptionPath(request.URL.Path):
		s.handleAdoptWorldlineEvent(response, request)
	case request.Method == http.MethodPatch && isWorldlineEventMutationPath(request.URL.Path):
		s.handleUpdateWorldlineEvent(response, request)
	case request.Method == http.MethodPost && isWorldlineSessionVariablesPath(request.URL.Path):
		s.handleInjectWorldlineVariable(response, request)
	case request.Method == http.MethodPost && isWorldlineSessionSavedPathsPath(request.URL.Path):
		s.handleCreateWorldlineSavedPath(response, request)
	case request.Method == http.MethodGet && isWorldlineSessionDetailPath(request.URL.Path):
		s.handleGetWorldlineSession(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/worldline/saved-paths"):
		s.handleListWorldlineSavedPaths(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/character-interactions"):
		s.handleCreateCharacterInteraction(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/character-interactions"):
		s.handleListCharacterInteractions(response, request)
	case request.Method == http.MethodPost && isCharacterInteractionNestedPath(request.URL.Path, "turns"):
		s.handleAppendCharacterInteractionTurn(response, request)
	case request.Method == http.MethodPost && isCharacterInteractionNestedPath(request.URL.Path, "dialogue"):
		s.handleStartCharacterDialogue(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/turns"):
		s.handleListCharacterInteractionTurns(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/") && strings.HasSuffix(request.URL.Path, "/events"):
		s.handleListCharacterInteractionEvents(response, request)
	case request.Method == http.MethodGet && isCharacterInteractionNestedPath(request.URL.Path, "proposals"):
		s.handleListCharacterProposals(response, request)
	case request.Method == http.MethodPost && isCharacterProposalAdoptionPath(request.URL.Path):
		s.handleAdoptCharacterProposal(response, request)
	case request.Method == http.MethodPost && isCharacterInteractionNestedPath(request.URL.Path, "chapter-drafts"):
		s.handleConvertCharacterInteractionToChapterDraft(response, request)
	case request.Method == http.MethodPatch && isCharacterInteractionMutationPath(request.URL.Path):
		s.handleUpdateCharacterInteractionStatus(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/character-interactions/"):
		s.handleGetCharacterInteraction(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/writer-runs"):
		s.handleStartWriterRun(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/writer-threads"):
		s.handleListWriterThreads(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/writer-threads"):
		s.handleEnsureWriterThread(response, request)
	case request.Method == http.MethodGet && hasWriterThreadMessagesPathShape(request.URL.Path):
		s.handleListWriterThreadMessages(response, request)
	case request.Method == http.MethodPost && hasWriterThreadMessagesPathShape(request.URL.Path):
		s.handleAppendWriterThreadMessage(response, request)
	case request.Method == http.MethodPost && hasWriterApprovalDecisionPathShape(request.URL.Path):
		s.handleDecideWriterApproval(response, request)
	case request.Method == http.MethodPost && isWriterRunCancelPath(request.URL.Path):
		s.handleCancelWriterRun(response, request)
	case request.Method == http.MethodPost && isDraftAdoptionPath(request.URL.Path):
		s.handleAdoptDraft(response, request)
	case request.Method == http.MethodPost && isDraftReviewPath(request.URL.Path):
		s.handleStartDraftReview(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/drafts/") && strings.HasSuffix(request.URL.Path, "/reviews"):
		s.handleListDraftReviews(response, request)
	case request.Method == http.MethodPatch && isDraftReviewIssuePath(request.URL.Path):
		s.handleUpdateDraftReviewIssue(response, request)
	case request.Method == http.MethodGet && isWriterRunEventsPath(request.URL.Path):
		s.handleListWriterRunEvents(response, request)
	case request.Method == http.MethodGet && isWriterRunDetailPath(request.URL.Path):
		s.handleGetWriterRun(response, request)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/agent-runtime/hello-runs"):
		s.handleStartHelloAgent(response, request)
	case request.Method == http.MethodGet && hasLLMResolutionPathShape(request.URL.Path):
		s.handleResolveLLMModuleBinding(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/quota-policies"):
		s.handleListLLMQuotaPolicies(response, request)
	case request.Method == http.MethodPut && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/quota-policies"):
		s.handleUpsertLLMQuotaPolicy(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/billing-usage"):
		s.handleListLLMBillingUsage(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/modules"):
		s.handleListLLMModules(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/module-bindings"):
		s.handleListLLMModuleBindings(response, request)
	case request.Method == http.MethodPut && hasLLMModuleBindingPathShape(request.URL.Path):
		s.handleUpsertLLMModuleBinding(response, request)
	case request.Method == http.MethodDelete && hasLLMModuleBindingPathShape(request.URL.Path):
		s.handleDeleteLLMModuleBinding(response, request)
	case request.Method == http.MethodGet && hasLLMChannelModelsPathShape(request.URL.Path):
		s.handleListLLMModels(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/channels"):
		s.handleListLLMChannels(response, request)
	case request.Method == http.MethodGet && request.URL.Path == "/v1/llm/settings":
		s.handleGetLLMSettings(response, request)
	case request.Method == http.MethodPost && request.URL.Path == "/v1/llm/channels":
		s.handleCreateLLMChannel(response, request)
	case request.Method == http.MethodPost && isLLMChannelSyncPath(request.URL.Path):
		s.handleSyncLLMChannelModels(response, request)
	case request.Method == http.MethodPatch && isLLMChannelModelMutationPath(request.URL.Path):
		s.handlePatchLLMChannelModel(response, request)
	case request.Method == http.MethodPatch && isLLMChannelMutationPath(request.URL.Path):
		s.handlePatchLLMChannel(response, request)
	case request.Method == http.MethodDelete && isLLMChannelMutationPath(request.URL.Path):
		s.handleDeleteLLMChannel(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/activity"):
		s.handleListLLMActivity(response, request)
	case request.Method == http.MethodGet && strings.HasPrefix(request.URL.Path, "/v1/projects/") && strings.HasSuffix(request.URL.Path, "/llm/usage"):
		s.handleListLLMUsage(response, request)
	case request.Method == http.MethodGet && hasTraceEventsPathShape(request.URL.Path):
		s.handleListAgentTraceEvents(response, request)
	case request.Method == http.MethodPost && hasTraceExportPathShape(request.URL.Path):
		s.handleExportAgentTrace(response, request)
	case isWriterWorkspaceRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.writerWorkspaceHandler, "WRITER_WORKSPACE_BACKEND_UNCONFIGURED")
	case isManuscriptWorkspaceRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.manuscriptWorkspaceHandler, "MANUSCRIPT_WORKSPACE_BACKEND_UNCONFIGURED")
	case isManuscriptExportDownloadRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.manuscriptExportHandler, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED")
	case isAssetCatalogRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.assetCatalogHandler, "ASSET_CATALOG_BACKEND_UNCONFIGURED")
	case isAssetDistillationRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.assetDistillationHandler, "ASSET_DISTILLATION_BACKEND_UNCONFIGURED")
	case isCollaborationRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.collaborationHandler, "COLLABORATION_BACKEND_UNCONFIGURED")
	case isProjectAdminRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.projectAdminHandler, "PROJECT_ADMIN_BACKEND_UNCONFIGURED")
	case isLLMAdminRoute(request.Method, request.URL.Path):
		s.serveMountedHandler(response, request, s.llmAdminHandler, "LLM_ADMIN_BACKEND_UNCONFIGURED")
	default:
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "route not found", nil)
	}
}

func (s *Server) handleReadiness(response http.ResponseWriter, request *http.Request) {
	report := ReadinessReport{
		Status: "unavailable",
		Dependencies: []ReadinessDependency{{
			Name: "readiness", Status: "unavailable", ErrorCode: "READINESS_UNCONFIGURED",
		}},
		CheckedAt: time.Now().UTC(),
	}
	if s.readinessChecker != nil {
		report = sanitizeReadinessReport(s.readinessChecker.Check(request.Context()))
	}
	checkedAt := report.CheckedAt.UTC()
	if checkedAt.IsZero() {
		checkedAt = time.Now().UTC()
	}
	status := http.StatusOK
	if report.Status != "ready" {
		status = http.StatusServiceUnavailable
	}
	response.Header().Set("Cache-Control", "no-store")
	writeJSON(response, status, map[string]any{
		"status": report.Status, "dependencies": report.Dependencies,
		"timestamp": checkedAt.Format(time.RFC3339Nano),
	})
}

func sanitizeReadinessReport(report ReadinessReport) ReadinessReport {
	if len(report.Dependencies) == 0 {
		report.Status = "unavailable"
		report.Dependencies = []ReadinessDependency{{
			Name: "readiness", Status: "unavailable", ErrorCode: "READINESS_EMPTY",
		}}
		return report
	}
	report.Status = "ready"
	for index := range report.Dependencies {
		dependency := &report.Dependencies[index]
		dependency.Name = sanitizeReadinessToken(dependency.Name, "dependency")
		if dependency.Status != "ready" && dependency.Status != "disabled" {
			dependency.Status = "unavailable"
			dependency.ErrorCode = sanitizeReadinessToken(dependency.ErrorCode, "DEPENDENCY_UNAVAILABLE")
			report.Status = "unavailable"
		} else {
			dependency.ErrorCode = ""
		}
	}
	sort.Slice(report.Dependencies, func(left, right int) bool {
		return report.Dependencies[left].Name < report.Dependencies[right].Name
	})
	return report
}

func sanitizeReadinessToken(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	for _, character := range value {
		if (character < 'A' || character > 'Z') && (character < 'a' || character > 'z') &&
			(character < '0' || character > '9') && character != '_' && character != '-' {
			return fallback
		}
	}
	return value
}

func (s *Server) serveMountedHandler(response http.ResponseWriter, request *http.Request, handler http.Handler, code string) {
	if handler == nil {
		writeError(response, request, http.StatusServiceUnavailable, code, "requested backend is not configured", nil)
		return
	}
	handler.ServeHTTP(response, request)
}

func (s *Server) handleCreateDevSession(response http.ResponseWriter, request *http.Request) {
	if !s.allowDevelopmentAuth {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "route not found", nil)
		return
	}
	if strings.TrimSpace(s.sessionAuthSecret) == "" {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, "session auth secret is not configured", nil)
		return
	}
	var payload createDevSessionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, auth.CodeValidationFailed, "invalid dev session payload", nil)
		return
	}
	userID := strings.TrimSpace(payload.UserID)
	if userID == "" {
		writeError(response, request, http.StatusBadRequest, auth.CodeValidationFailed, "user_id is required", nil)
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
	s.issueSessionCookie(response, request, currentUser)
}

func (s *Server) handlePasswordLogin(response http.ResponseWriter, request *http.Request) {
	if s.passwordAuthenticator == nil || s.authSessionStore == nil || strings.TrimSpace(s.sessionAuthSecret) == "" {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, "auth password login backend is not configured", nil)
		return
	}
	clientHash := ""
	if s.rateLimiter != nil {
		if s.trustedClientProofVerifier == nil {
			writeError(response, request, http.StatusServiceUnavailable, "TRUSTED_CLIENT_PROOF_BACKEND_UNCONFIGURED", "trusted client verification is unavailable", nil)
			return
		}
		var err error
		clientHash, err = s.trustedClientProofVerifier.Verify(request.Header.Get(authrecovery.RecoveryClientProofHeader))
		if err != nil {
			writeError(response, request, http.StatusForbidden, "TRUSTED_CLIENT_PROOF_INVALID", "trusted client proof is invalid", nil)
			return
		}
	}
	var payload passwordLoginRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, auth.CodeValidationFailed, "invalid login payload", nil)
		return
	}
	email := strings.ToLower(strings.TrimSpace(payload.Email))
	if !s.allowPlatformRequest(response, request, platformratelimit.Input{
		Class: platformratelimit.ClassAuthLogin, KeyParts: []string{clientHash, email}, Cost: 1,
	}) {
		return
	}
	currentUser, err := s.passwordAuthenticator.AuthenticatePassword(request.Context(), auth.PasswordLoginInput{
		Email:     email,
		Password:  payload.Password,
		RequestID: requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	s.issueSessionCookie(response, request, currentUser)
}

func (s *Server) handleSignup(response http.ResponseWriter, request *http.Request) {
	if s.registrationService == nil || strings.TrimSpace(s.sessionAuthSecret) == "" {
		writeError(response, request, http.StatusServiceUnavailable, registration.CodeBackendUnconfigured, "registration backend is not configured", nil)
		return
	}
	clientHash := ""
	if s.rateLimiter != nil {
		if s.trustedClientProofVerifier == nil {
			writeError(response, request, http.StatusServiceUnavailable, "TRUSTED_CLIENT_PROOF_BACKEND_UNCONFIGURED", "trusted client verification is unavailable", nil)
			return
		}
		var err error
		clientHash, err = s.trustedClientProofVerifier.Verify(request.Header.Get(authrecovery.RecoveryClientProofHeader))
		if err != nil {
			writeError(response, request, http.StatusForbidden, "TRUSTED_CLIENT_PROOF_INVALID", "trusted client proof is invalid", nil)
			return
		}
	}
	var payload signupRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, registration.CodeValidationFailed, "invalid registration payload", nil)
		return
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, registration.CodeValidationFailed, "invalid registration payload", nil)
		return
	}
	email := strings.ToLower(strings.TrimSpace(payload.Email))
	if !s.allowPlatformRequest(response, request, platformratelimit.Input{
		Class: platformratelimit.ClassAuthSignup, KeyParts: []string{clientHash, email}, Cost: 1,
	}) {
		return
	}
	initialSessionToken := ""
	result, err := s.registrationService.Register(request.Context(), registration.RegisterInput{
		DisplayName:  payload.DisplayName,
		Email:        email,
		Password:     payload.Password,
		ProjectTitle: payload.ProjectTitle,
		InitialSessionFactory: func(userID string) (registration.InitialSession, error) {
			token, ok := s.signSessionToken(userID)
			if !ok {
				return registration.InitialSession{}, errors.New("initial session token generation failed")
			}
			initialSessionToken = token
			return registration.InitialSession{
				TokenHash: hashSessionToken(token),
				ExpiresAt: time.Now().UTC().Add(sessionTTL),
			}, nil
		},
	})
	if err != nil {
		code := registration.ErrorCode(err)
		status := http.StatusServiceUnavailable
		message := "registration failed"
		details := map[string]any(nil)
		switch code {
		case registration.CodeValidationFailed:
			status = http.StatusBadRequest
			message = "registration details are invalid"
			if field := registration.ErrorField(err); field != "" {
				details = map[string]any{"field": field}
			}
		case registration.CodeEmailConflict:
			status = http.StatusConflict
			message = "an account already exists for this email"
		case registration.CodeBackendUnconfigured:
			message = "registration backend is not configured"
		}
		writeError(response, request, status, code, message, details)
		return
	}
	if strings.TrimSpace(initialSessionToken) == "" {
		writeError(response, request, http.StatusServiceUnavailable, registration.CodeRegistrationFailed, "registration failed", nil)
		return
	}
	currentUser := auth.CurrentUser{
		User: auth.UserSummary{
			UserID:      result.User.UserID,
			Email:       result.User.Email,
			DisplayName: result.User.DisplayName,
		},
		ActiveTenants: []auth.TenantMembershipSummary{{
			TenantID: result.Workspace.TenantID,
			Name:     result.Workspace.Name,
			Role:     result.Workspace.Role,
			Status:   result.Workspace.Status,
		}},
		ActiveProjects: []auth.ProjectMembershipSummary{{
			TenantID:  result.Project.TenantID,
			ProjectID: result.Project.ProjectID,
			Name:      result.Project.Title,
			Role:      result.Project.Role,
			Status:    result.Project.Status,
		}},
	}
	s.writeCreatedSession(response, request, currentUser, initialSessionToken)
}

func (s *Server) handleChangePassword(response http.ResponseWriter, request *http.Request) {
	if s.passwordChanger == nil || s.authSessionStore == nil || strings.TrimSpace(s.sessionAuthSecret) == "" {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, "auth password change backend is not configured", nil)
		return
	}
	userID, tokenHash, fromCookie, ok := s.passwordChangeCredential(response, request)
	if !ok {
		return
	}
	if fromCookie && !s.verifySessionCSRFToken(tokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, tokenHash, "password_change") {
		return
	}
	if err := s.authSessionStore.ValidateSession(request.Context(), auth.ValidateSessionInput{
		UserID: userID, TokenHash: tokenHash, Now: time.Now().UTC(), RequestID: requestID(request),
	}); err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}

	var payload changePasswordRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, auth.CodeValidationFailed, authPublicErrorMessage(auth.CodeValidationFailed), nil)
		return
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, auth.CodeValidationFailed, authPublicErrorMessage(auth.CodeValidationFailed), nil)
		return
	}
	if err := s.passwordChanger.ChangePassword(request.Context(), auth.ChangePasswordInput{
		UserID: userID, CurrentPassword: payload.CurrentPassword, NewPassword: payload.NewPassword,
		Now: time.Now().UTC(), RequestID: requestID(request),
	}); err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	if fromCookie {
		s.clearSessionCookie(response, request)
	}
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) allowSessionMutation(response http.ResponseWriter, request *http.Request, userID string, tokenHash string, operation string) bool {
	return s.allowPlatformRequest(response, request, platformratelimit.Input{
		Class:    platformratelimit.ClassAuthSessionMutation,
		KeyParts: []string{strings.TrimSpace(userID), strings.TrimSpace(tokenHash), strings.TrimSpace(operation)}, Cost: 1,
	})
}

func (s *Server) allowPlatformRequest(response http.ResponseWriter, request *http.Request, input platformratelimit.Input) bool {
	if s.rateLimiter == nil {
		return true
	}
	decision, err := s.rateLimiter.Allow(request.Context(), input)
	if err != nil {
		code := platformratelimit.ErrorCode(err)
		if code != "RATE_LIMIT_POLICY_UNCONFIGURED" {
			code = "RATE_LIMIT_BACKEND_UNAVAILABLE"
		}
		writeError(response, request, http.StatusServiceUnavailable, code, "rate limit service is unavailable", nil)
		return false
	}
	if decision.Allowed {
		return true
	}
	retryAfter := int64((decision.RetryAfter + time.Second - 1) / time.Second)
	if retryAfter < 1 {
		retryAfter = 1
	}
	response.Header().Set("Retry-After", strconv.FormatInt(retryAfter, 10))
	writeError(response, request, http.StatusTooManyRequests, "RATE_LIMITED", "request rate limit exceeded", nil)
	return false
}

func (s *Server) passwordChangeCredential(response http.ResponseWriter, request *http.Request) (string, string, bool, bool) {
	var token string
	fromCookie := false
	authorizationValues := request.Header.Values("Authorization")
	if len(authorizationValues) > 0 {
		if len(authorizationValues) != 1 {
			writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
			return "", "", false, false
		}
		var ok bool
		token, ok = bearerToken(authorizationValues[0])
		if !ok {
			writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
			return "", "", false, false
		}
	} else if cookie, err := request.Cookie(sessionCookieName); err == nil {
		token = cookie.Value
		fromCookie = true
	}
	userID, tokenHash, ok := s.verifySignedSessionToken(token)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return "", "", false, false
	}
	return userID, tokenHash, fromCookie, true
}

func (s *Server) clearSessionCookie(response http.ResponseWriter, request *http.Request) {
	http.SetCookie(response, &http.Cookie{
		Name: sessionCookieName, Value: "", Path: "/", MaxAge: -1, Expires: time.Unix(0, 0).UTC(),
		HttpOnly: true, SameSite: http.SameSiteLaxMode, Secure: s.secureSessionCookie(request),
	})
}

func (s *Server) issueSessionCookie(response http.ResponseWriter, request *http.Request, currentUser auth.CurrentUser) {
	token, ok := s.signSessionToken(currentUser.User.UserID)
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, "session auth secret is not configured", nil)
		return
	}
	sessionTTL := 7 * 24 * time.Hour
	if s.authSessionStore != nil {
		err := s.authSessionStore.CreateSession(request.Context(), auth.CreateSessionInput{
			UserID:    currentUser.User.UserID,
			TokenHash: hashSessionToken(token),
			ExpiresAt: time.Now().UTC().Add(sessionTTL),
			RequestID: requestID(request),
		})
		if err != nil {
			code := publicAuthCode(auth.ErrorCode(err))
			writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
			return
		}
	}
	s.writeCreatedSession(response, request, currentUser, token)
}

func (s *Server) writeCreatedSession(response http.ResponseWriter, request *http.Request, currentUser auth.CurrentUser, token string) {
	http.SetCookie(response, &http.Cookie{
		Name:     sessionCookieName,
		Value:    token,
		Path:     "/",
		MaxAge:   int(sessionTTL.Seconds()),
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   s.secureSessionCookie(request),
	})
	writeJSON(response, http.StatusCreated, currentUser)
}

func (s *Server) secureSessionCookie(request *http.Request) bool {
	return s.forceSecureSessionCookies || request.TLS != nil
}

func (s *Server) handleGetSessionCSRFToken(response http.ResponseWriter, request *http.Request) {
	cookie, err := request.Cookie(sessionCookieName)
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	userID, tokenHash, ok := s.verifySignedSessionToken(cookie.Value)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if s.authSessionStore != nil {
		err := s.authSessionStore.ValidateSession(request.Context(), auth.ValidateSessionInput{
			UserID:    userID,
			TokenHash: tokenHash,
			Now:       time.Now().UTC(),
			RequestID: requestID(request),
		})
		if err != nil {
			code := publicAuthCode(auth.ErrorCode(err))
			writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
			return
		}
	}
	writeJSON(response, http.StatusOK, map[string]string{
		"csrf_token": s.sessionCSRFToken(tokenHash),
	})
}

func (s *Server) handleListCurrentUserSessions(response http.ResponseWriter, request *http.Request) {
	token := ""
	authorizationValues := request.Header.Values("Authorization")
	if len(authorizationValues) > 0 {
		if len(authorizationValues) != 1 {
			writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
			return
		}
		bearer, ok := bearerToken(authorizationValues[0])
		if !ok {
			writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
			return
		}
		token = bearer
	} else if cookie, err := request.Cookie(sessionCookieName); err == nil {
		token = cookie.Value
	}
	if s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	userID, tokenHash, ok := s.verifySignedSessionToken(token)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	sessions, err := s.authSessionStore.ListUserSessions(request.Context(), auth.ListUserSessionsInput{
		UserID:    userID,
		TokenHash: tokenHash,
		Now:       time.Now().UTC(),
		RequestID: requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	if sessions == nil {
		sessions = []auth.SessionSummary{}
	}
	writeJSON(response, http.StatusOK, map[string][]auth.SessionSummary{
		"sessions": sessions,
	})
}

func (s *Server) handleRevokeCurrentSession(response http.ResponseWriter, request *http.Request) {
	token := ""
	fromCookie := false
	if bearer, ok := bearerToken(request.Header.Get("Authorization")); ok {
		token = bearer
	} else if cookie, err := request.Cookie(sessionCookieName); err == nil {
		token = cookie.Value
		fromCookie = true
	}
	userID, tokenHash, ok := s.verifySignedSessionToken(token)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if fromCookie && !s.verifySessionCSRFToken(tokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, tokenHash, "revoke_current") {
		return
	}
	if s.authSessionStore != nil {
		err := s.authSessionStore.RevokeSession(request.Context(), auth.RevokeSessionInput{
			UserID:    userID,
			TokenHash: tokenHash,
			Now:       time.Now().UTC(),
			RequestID: requestID(request),
		})
		if err != nil {
			code := publicAuthCode(auth.ErrorCode(err))
			writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
			return
		}
	}
	http.SetCookie(response, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		MaxAge:   -1,
		Expires:  time.Unix(0, 0).UTC(),
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   request.TLS != nil,
	})
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleRevokeAllCurrentUserSessions(response http.ResponseWriter, request *http.Request) {
	token := ""
	fromCookie := false
	if bearer, ok := bearerToken(request.Header.Get("Authorization")); ok {
		token = bearer
	} else if cookie, err := request.Cookie(sessionCookieName); err == nil {
		token = cookie.Value
		fromCookie = true
	}
	if s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	userID, tokenHash, ok := s.verifySignedSessionToken(token)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if fromCookie && !s.verifySessionCSRFToken(tokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, tokenHash, "revoke_all") {
		return
	}
	err := s.authSessionStore.RevokeUserSessions(request.Context(), auth.RevokeUserSessionsInput{
		UserID:    userID,
		TokenHash: tokenHash,
		Now:       time.Now().UTC(),
		RequestID: requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	if fromCookie {
		http.SetCookie(response, &http.Cookie{
			Name:     sessionCookieName,
			Value:    "",
			Path:     "/",
			MaxAge:   -1,
			Expires:  time.Unix(0, 0).UTC(),
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
			Secure:   request.TLS != nil,
		})
	}
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleRevokeTenantSessions(response http.ResponseWriter, request *http.Request) {
	tenantID := tenantSessionsPathPart(request.URL.Path)
	if tenantID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "tenant sessions route not found", nil)
		return
	}
	if !s.authorizeTenantSessionManage(response, request, tenantID) {
		return
	}
	actorID := s.actorUserID(request)
	if !s.allowSessionMutation(response, request, actorID, tenantID, "revoke_tenant") {
		return
	}
	if s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	err := s.authSessionStore.RevokeTenantSessions(request.Context(), auth.RevokeTenantSessionsInput{
		TenantID:  tenantID,
		ActorID:   actorID,
		Now:       time.Now().UTC(),
		RequestID: requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleRotateCurrentSession(response http.ResponseWriter, request *http.Request) {
	cookie, err := request.Cookie(sessionCookieName)
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	userID, oldTokenHash, ok := s.verifySignedSessionToken(cookie.Value)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if !s.verifySessionCSRFToken(oldTokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, oldTokenHash, "rotate") {
		return
	}
	newToken, ok := s.signSessionToken(userID)
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	sessionTTL := 7 * 24 * time.Hour
	now := time.Now().UTC()
	newTokenHash := hashSessionToken(newToken)
	err = s.authSessionStore.RotateSession(request.Context(), auth.RotateSessionInput{
		UserID:       userID,
		OldTokenHash: oldTokenHash,
		NewTokenHash: newTokenHash,
		ExpiresAt:    now.Add(sessionTTL),
		Now:          now,
		RequestID:    requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	http.SetCookie(response, &http.Cookie{
		Name:     sessionCookieName,
		Value:    newToken,
		Path:     "/",
		MaxAge:   int(sessionTTL.Seconds()),
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   request.TLS != nil,
	})
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleRotateCurrentSessionToJWT(response http.ResponseWriter, request *http.Request) {
	cookie, err := request.Cookie(sessionCookieName)
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	userID, oldTokenHash, ok := s.verifySignedSessionToken(cookie.Value)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if !s.verifySessionCSRFToken(oldTokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, oldTokenHash, "rotate_jwt") {
		return
	}
	sessionID, ok := randomSessionID()
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	now := time.Now().UTC()
	newToken, ok := s.signJWTSessionToken(userID, sessionID, now)
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	newTokenHash := hashSessionToken(newToken)
	err = s.authSessionStore.RotateSession(request.Context(), auth.RotateSessionInput{
		UserID:       userID,
		OldTokenHash: oldTokenHash,
		NewTokenHash: newTokenHash,
		ExpiresAt:    now.Add(sessionTTL),
		Now:          now,
		RequestID:    requestID(request),
	})
	if err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	http.SetCookie(response, &http.Cookie{
		Name:     sessionCookieName,
		Value:    newToken,
		Path:     "/",
		MaxAge:   int(sessionTTL.Seconds()),
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   request.TLS != nil,
	})
	response.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleCreateCurrentSessionAccessToken(response http.ResponseWriter, request *http.Request) {
	cookie, err := request.Cookie(sessionCookieName)
	if err != nil || strings.TrimSpace(cookie.Value) == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if strings.TrimSpace(s.sessionAuthSecret) == "" || s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	userID, oldTokenHash, ok := s.verifySignedSessionToken(cookie.Value)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if !s.verifySessionCSRFToken(oldTokenHash, request.Header.Get(csrfHeaderName)) {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, oldTokenHash, "access_token") {
		return
	}
	now := time.Now().UTC()
	if err := s.authSessionStore.ValidateSession(request.Context(), auth.ValidateSessionInput{
		UserID:    userID,
		TokenHash: oldTokenHash,
		Now:       now,
		RequestID: requestID(request),
	}); err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	sessionID, ok := randomSessionID()
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	accessToken, ok := s.signJWTSessionToken(userID, sessionID, now)
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	expiresAt := now.Add(sessionTTL)
	if err := s.authSessionStore.CreateSession(request.Context(), auth.CreateSessionInput{
		UserID:    userID,
		TokenHash: hashSessionToken(accessToken),
		ExpiresAt: expiresAt,
		RequestID: requestID(request),
	}); err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, sessionAccessTokenResponse{
		AccessToken: accessToken,
		TokenType:   "Bearer",
		ExpiresAt:   expiresAt,
	})
}

func (s *Server) handleRefreshJWTBearerSession(response http.ResponseWriter, request *http.Request) {
	if strings.TrimSpace(s.sessionAuthSecret) == "" || s.authSessionStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	authorizationValues := request.Header.Values("Authorization")
	if len(authorizationValues) != 1 {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	token, ok := bearerToken(authorizationValues[0])
	if !ok || strings.Count(token, ".") != 2 {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	userID, oldTokenHash, ok := s.verifyJWTSessionToken(token)
	if !ok {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, authPublicErrorMessage(auth.CodeUnauthenticated), nil)
		return
	}
	if !s.allowSessionMutation(response, request, userID, oldTokenHash, "jwt_refresh") {
		return
	}
	now := time.Now().UTC()
	sessionID, ok := randomSessionID()
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	accessToken, ok := s.signJWTSessionToken(userID, sessionID, now)
	if !ok {
		writeError(response, request, http.StatusServiceUnavailable, auth.CodeBackendUnconfigured, authPublicErrorMessage(auth.CodeBackendUnconfigured), nil)
		return
	}
	newTokenHash := hashSessionToken(accessToken)
	expiresAt := now.Add(sessionTTL)
	if err := s.authSessionStore.RotateSession(request.Context(), auth.RotateSessionInput{
		UserID:       userID,
		OldTokenHash: oldTokenHash,
		NewTokenHash: newTokenHash,
		ExpiresAt:    expiresAt,
		Now:          now,
		RequestID:    requestID(request),
	}); err != nil {
		code := publicAuthCode(auth.ErrorCode(err))
		writeError(response, request, statusForAuthCode(code), code, authPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, sessionAccessTokenResponse{
		AccessToken: accessToken,
		TokenType:   "Bearer",
		ExpiresAt:   expiresAt,
	})
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

func (s *Server) authorizeGlobalRunOwnerProjectRead(response http.ResponseWriter, request *http.Request, tenantID string, projectID string) bool {
	if strings.TrimSpace(projectID) == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return s.authorizeProjectRead(response, request, tenantID, projectID)
}

func (s *Server) authorizeGlobalRunOwnerCreativeWrite(response http.ResponseWriter, request *http.Request, tenantID string, projectID string) bool {
	projectID = strings.TrimSpace(projectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite)
}

func (s *Server) authorizeGlobalWorkflowRunControl(response http.ResponseWriter, request *http.Request, tenantID string, run workflows.WorkflowRun) bool {
	projectID := strings.TrimSpace(run.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	permission, ok := permissionForWorkflowRunControl(run.WorkflowType)
	if !ok {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return s.authorizeProject(response, request, tenantID, projectID, permission)
}

const (
	worldlineSessionWorkflowType       = "worldline_session"
	worldlineStepWorkflowType          = "worldline_step"
	worldlinePreparationWorkflowType   = "worldline_preparation"
	worldlineAutoEvolutionWorkflowType = "worldline_auto_evolution"
)

func permissionForWorkflowRunControl(workflowType string) (auth.Permission, bool) {
	switch strings.TrimSpace(workflowType) {
	case workflows.AssetIngestionWorkflowType, workflows.StyleExtractionWorkflowType, workflows.AssetReindexWorkflowType:
		return auth.PermissionAssetManage, true
	case workflows.WriterWorkflowType, workflows.WriterReviewWorkflowType, workflows.SeedWorkflowType,
		workflows.StoryGraphBuildWorkflowType, workflows.StoryGraphBondGenerationWorkflowType,
		workflows.HelloAgentWorkflowType, worldlineSessionWorkflowType, worldlineStepWorkflowType,
		worldlinePreparationWorkflowType, worldlineAutoEvolutionWorkflowType:
		return auth.PermissionCreativeWrite, true
	default:
		return "", false
	}
}

func (s *Server) authorizeAssetManage(response http.ResponseWriter, request *http.Request, tenantID string, projectID string) bool {
	return s.authorizeProject(response, request, tenantID, projectID, auth.PermissionAssetManage)
}

func (s *Server) authorizeLLMTenantManage(response http.ResponseWriter, request *http.Request, tenantID string) bool {
	return s.authorizeProject(response, request, tenantID, "", auth.PermissionLLMModuleBindingManage)
}

func (s *Server) authorizeTenantSessionManage(response http.ResponseWriter, request *http.Request, tenantID string) bool {
	return s.authorizeProject(response, request, tenantID, "", auth.PermissionTenantSessionManage)
}

func (s *Server) authorizeSingleAssetManage(response http.ResponseWriter, request *http.Request, tenantID string, assetID string) bool {
	record, err := s.assetReader.GetAsset(request.Context(), assets.GetAssetInput{
		TenantID: tenantID,
		AssetID:  assetID,
	})
	if err != nil {
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetOwnerPreflightPublicErrorMessage(code), nil)
		return false
	}
	if strings.TrimSpace(record.ProjectID) == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return s.authorizeAssetManage(response, request, tenantID, record.ProjectID)
}

func (s *Server) authorizeWorldlineSessionCreativeWrite(response http.ResponseWriter, request *http.Request, tenantID string, sessionID string) (worldline.SessionRecord, bool) {
	record, err := s.worldlineSessionReader.GetSession(request.Context(), worldline.GetSessionInput{
		TenantID:  tenantID,
		SessionID: sessionID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineSessionOwnerPreflightPublicErrorMessage(code), nil)
		return worldline.SessionRecord{}, false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return worldline.SessionRecord{}, false
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return worldline.SessionRecord{}, false
	}
	return record, true
}

func (s *Server) authorizeWorldlineSessionProjectRead(response http.ResponseWriter, request *http.Request, tenantID string, sessionID string) (worldline.SessionRecord, bool) {
	record, err := s.worldlineSessionReader.GetSession(request.Context(), worldline.GetSessionInput{
		TenantID:  tenantID,
		SessionID: sessionID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineSessionOwnerPreflightPublicErrorMessage(code), nil)
		return worldline.SessionRecord{}, false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return worldline.SessionRecord{}, false
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return worldline.SessionRecord{}, false
	}
	return record, true
}

func (s *Server) authorizeWorldlinePreparationProjectRead(response http.ResponseWriter, request *http.Request, tenantID string, prepareID string) (worldline.PreparationRecord, bool) {
	record, err := s.worldlinePreparationStore.GetPreparation(request.Context(), worldline.GetPreparationInput{
		TenantID:  tenantID,
		PrepareID: prepareID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlinePreparationOwnerPreflightPublicErrorMessage(code), nil)
		return worldline.PreparationRecord{}, false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return worldline.PreparationRecord{}, false
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return worldline.PreparationRecord{}, false
	}
	return record, true
}

func (s *Server) authorizeWorldlineEventCreativeWrite(response http.ResponseWriter, request *http.Request, tenantID string, eventID string) bool {
	record, err := s.worldlineEventReader.GetEvent(request.Context(), worldline.GetEventInput{
		TenantID: tenantID,
		EventID:  eventID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineEventOwnerPreflightPublicErrorMessage(code), nil)
		return false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return false
	}
	return s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite)
}

func (s *Server) authorizeCharacterInteractionCreativeWrite(response http.ResponseWriter, request *http.Request, tenantID string, interactionID string) (characterconsole.InteractionRecord, bool) {
	record, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		code := characterconsole.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, characterInteractionOwnerPreflightPublicErrorMessage(code), nil)
		return characterconsole.InteractionRecord{}, false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return characterconsole.InteractionRecord{}, false
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return characterconsole.InteractionRecord{}, false
	}
	record.ProjectID = projectID
	return record, true
}

func (s *Server) authorizeCharacterInteractionProjectRead(response http.ResponseWriter, request *http.Request, tenantID string, interactionID string) (characterconsole.InteractionRecord, bool) {
	record, err := s.characterConsoleStore.GetInteraction(request.Context(), characterconsole.GetInteractionInput{
		TenantID:      tenantID,
		InteractionID: interactionID,
	})
	if err != nil {
		code := characterconsole.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, characterInteractionOwnerPreflightPublicErrorMessage(code), nil)
		return characterconsole.InteractionRecord{}, false
	}
	projectID := strings.TrimSpace(record.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return characterconsole.InteractionRecord{}, false
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return characterconsole.InteractionRecord{}, false
	}
	record.ProjectID = projectID
	return record, true
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
	// CONN-016: Pi dual-stage always needs writer_orchestrator + writer_composer.
	// Prefer explicit module_key as the primary resolution stored on the run, but
	// fail closed if any required module binding is missing before Temporal admit.
	// Also reject orchestrator bindings that still lack effective tool support so
	// authors do not queue a run that fails immediately in the Pi worker.
	moduleKey := moduleKeyFromOptions(payload.Options)
	requiredModules := requiredWriterRunModules(payload.Options)
	var primaryResolution llm.ModuleResolution
	for _, required := range requiredModules {
		resolution, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ModuleKey: required,
		})
		if err != nil {
			writeLLMError(response, request, err)
			return
		}
		if required == "writer_orchestrator" && !resolution.SupportsTools {
			writeError(
				response,
				request,
				http.StatusUnprocessableEntity,
				"LLM_MODEL_TOOLS_UNSUPPORTED",
				"writer_orchestrator binding must support tools",
				nil,
			)
			return
		}
		if required == moduleKey || primaryResolution.ModuleKey == "" {
			primaryResolution = resolution
		}
	}
	options := sanitizeWorkflowOptions(payload.Options)
	// Reject unknown review_after_write=true without a bound reviewer; when true, keep the flag
	// so workers may start an independent writer_reviewer pass after prose is ready.
	if reviewAfterWriteEnabled(options) {
		if _, err := s.llmResolver.ResolveModuleBinding(request.Context(), llm.ResolveModuleInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ModuleKey: "writer_reviewer",
		}); err != nil {
			writeLLMError(response, request, err)
			return
		}
		options["review_after_write"] = true
	} else {
		delete(options, "review_after_write")
	}
	options["module_key"] = moduleKey
	options["llm_resolution"] = workflowLLMResolution(primaryResolution)
	options["required_module_keys"] = requiredModules
	run, err := s.writerStarter.StartWriterRun(request.Context(), workflows.StartWriterRunInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Mode:         strings.TrimSpace(payload.Mode),
		Instruction:  strings.TrimSpace(payload.Instruction),
		ChapterID:    strings.TrimSpace(payload.ChapterID),
		SceneID:      strings.TrimSpace(payload.SceneID),
		Options:      options,
		WorkflowType: workflows.WriterWorkflowType,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	// Best-effort persistent thread append for the user instruction (CONN-009).
	if s.writerThreadStore != nil && strings.TrimSpace(payload.Instruction) != "" {
		if thread, ensureErr := s.writerThreadStore.EnsureThread(request.Context(), workflows.EnsureWriterThreadInput{
			TenantID:  tenantID,
			ProjectID: projectID,
			ActorID:   s.actorUserID(request),
			Title:     "Writer thread",
		}); ensureErr == nil {
			_, _ = s.writerThreadStore.AppendMessage(request.Context(), workflows.AppendWriterThreadMessageInput{
				TenantID:  tenantID,
				ProjectID: projectID,
				ThreadID:  thread.ThreadID,
				Role:      "user",
				Body:      strings.TrimSpace(payload.Instruction),
				RunID:     run.RunID,
				ActorID:   s.actorUserID(request),
				Metadata:  map[string]any{"mode": run.Mode},
			})
		}
	}
	writeJSON(response, http.StatusAccepted, startWriterRunResponse{
		RunID:       run.RunID,
		TraceID:     run.TraceID,
		ProjectID:   run.ProjectID,
		Mode:        run.Mode,
		Instruction: run.Instruction,
		Status:      run.Status,
	})
}

func (s *Server) handleListWriterThreads(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "writer-threads")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}
	if s.writerThreadStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WORKFLOW_BACKEND_UNCONFIGURED", "writer thread store is not configured", nil)
		return
	}
	threads, err := s.writerThreadStore.ListThreads(request.Context(), workflows.ListWriterThreadsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, writerThreadPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, map[string]any{"threads": threads})
}

func (s *Server) handleEnsureWriterThread(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "writer-threads")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}
	if s.writerThreadStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WORKFLOW_BACKEND_UNCONFIGURED", "writer thread store is not configured", nil)
		return
	}
	var payload struct {
		Title string `json:"title"`
	}
	if request.Body != nil && request.ContentLength != 0 {
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
			writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid writer thread payload", nil)
			return
		}
	}
	thread, err := s.writerThreadStore.EnsureThread(request.Context(), workflows.EnsureWriterThreadInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ActorID:   s.actorUserID(request),
		Title:     strings.TrimSpace(payload.Title),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, writerThreadPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, thread)
}

func (s *Server) handleListWriterThreadMessages(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, threadID := writerThreadMessagesPathParts(request.URL.Path)
	if projectID == "" || threadID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer thread messages route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}
	if s.writerThreadStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WORKFLOW_BACKEND_UNCONFIGURED", "writer thread store is not configured", nil)
		return
	}
	messages, err := s.writerThreadStore.ListMessages(request.Context(), workflows.ListWriterThreadMessagesInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ThreadID:  threadID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, writerThreadPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, map[string]any{"messages": messages})
}

func (s *Server) handleAppendWriterThreadMessage(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, threadID := writerThreadMessagesPathParts(request.URL.Path)
	if projectID == "" || threadID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer thread messages route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}
	if s.writerThreadStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WORKFLOW_BACKEND_UNCONFIGURED", "writer thread store is not configured", nil)
		return
	}
	var payload struct {
		Role     string         `json:"role"`
		Body     string         `json:"body"`
		RunID    string         `json:"run_id"`
		Metadata map[string]any `json:"metadata"`
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid writer thread message payload", nil)
		return
	}
	message, err := s.writerThreadStore.AppendMessage(request.Context(), workflows.AppendWriterThreadMessageInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		ThreadID:  threadID,
		Role:      strings.TrimSpace(payload.Role),
		Body:      strings.TrimSpace(payload.Body),
		RunID:     strings.TrimSpace(payload.RunID),
		ActorID:   s.actorUserID(request),
		Metadata:  sanitizeWorkflowOptions(payload.Metadata),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, writerThreadPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusCreated, message)
}

func (s *Server) handleDecideWriterApproval(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, approvalID := writerApprovalDecisionPathParts(request.URL.Path)
	if projectID == "" || approvalID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer approval route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionWriterRun) {
		return
	}
	if s.writerThreadStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WORKFLOW_BACKEND_UNCONFIGURED", "writer thread store is not configured", nil)
		return
	}
	var payload struct {
		Decision string `json:"decision"`
	}
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid writer approval payload", nil)
		return
	}
	approval, err := s.writerThreadStore.DecideApproval(request.Context(), workflows.DecideWriterApprovalInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		ApprovalID:  approvalID,
		Decision:    strings.TrimSpace(payload.Decision),
		ActorUserID: s.actorUserID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, writerThreadPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, approval)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	runID := seedRunPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed run route not found", nil)
		return
	}
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
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
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	events, err := s.workflowEventReader.ListWorkflowEvents(request.Context(), workflows.ListWorkflowEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: afterEventIDFromRequest(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerCreativeWrite(response, request, tenantID, run.ProjectID) {
		return
	}
	cancelled, err := s.workflowCanceller.CancelWorkflowRun(request.Context(), workflows.CancelWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerCreativeWrite(response, request, tenantID, run.ProjectID) {
		return
	}
	retried, err := s.workflowRetrier.RetryWorkflowRun(request.Context(), workflows.RetryWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{
		"run_id": retried.RunID,
		"status": retried.Status,
	})
}

func (s *Server) handleRetrySeedSegments(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := seedSegmentRetryPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "seed segment retry route not found", nil)
		return
	}
	run, err := s.seedRunReader.GetSeedRun(request.Context(), workflows.GetSeedRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	projectID := strings.TrimSpace(run.ProjectID)
	if !s.authorizeGlobalRunOwnerCreativeWrite(response, request, tenantID, projectID) {
		return
	}
	var payload retrySeedSegmentsRequest
	if err := json.NewDecoder(request.Body).Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid seed segment retry payload", nil)
		return
	}
	segmentIDs := normalizeNonEmptyStrings(payload.SegmentIDs)
	if len(segmentIDs) == 0 {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "segment_ids are required", nil)
		return
	}
	retried, err := s.seedSegmentRetrier.RetrySeedSegments(request.Context(), workflows.RetrySeedSegmentsInput{
		TenantID:    tenantID,
		ProjectID:   projectID,
		RunID:       runID,
		SegmentIDs:  segmentIDs,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]any{
		"run_id":          retried.RunID,
		"status":          retried.Status,
		"requested_count": retried.RequestedCount,
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
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
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
	if !s.authorizeUploadOwnerCreativeWrite(response, request, tenantID, uploadID) {
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
	uploadID := uploadIDFromObjectPath(request.URL.Path)
	if uploadID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "upload object route not found", nil)
		return
	}
	if !s.authorizeUploadOwnerCreativeWrite(response, request, tenantID, uploadID) {
		return
	}
	if !sourcefiles.IsObjectWriterConfigured(s.sourceFileObjectWriter) {
		writeSourceFileError(response, request, sourcefiles.NewAppError("SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", "object storage backend is not configured"))
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

func (s *Server) authorizeUploadOwnerCreativeWrite(response http.ResponseWriter, request *http.Request, tenantID string, uploadID string) bool {
	owner, err := s.sourceFileStore.GetUploadOwner(request.Context(), sourcefiles.GetUploadOwnerInput{
		TenantID: tenantID,
		UploadID: uploadID,
	})
	if err != nil {
		writeSourceFileError(response, request, err)
		return false
	}
	return s.authorizeGlobalRunOwnerCreativeWrite(response, request, tenantID, owner.ProjectID)
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
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetOwnerPreflightPublicErrorMessage(code), nil)
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
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetOwnerPreflightPublicErrorMessage(code), nil)
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
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
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
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
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
	record, ok := s.authorizeCharacterInteractionProjectRead(response, request, tenantID, interactionID)
	if !ok {
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
	interactionID := characterInteractionPathPart(request.URL.Path)
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction route not found", nil)
		return
	}
	if _, ok := s.authorizeCharacterInteractionCreativeWrite(response, request, tenantID, interactionID); !ok {
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
	if _, ok := s.authorizeCharacterInteractionCreativeWrite(response, request, tenantID, interactionID); !ok {
		return
	}
	var payload appendCharacterInteractionTurnRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction turn payload", nil)
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
	if _, ok := s.authorizeCharacterInteractionProjectRead(response, request, tenantID, interactionID); !ok {
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

func (s *Server) handleStartCharacterDialogue(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "dialogue")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character dialogue route not found", nil)
		return
	}
	interaction, ok := s.authorizeCharacterInteractionCreativeWrite(response, request, tenantID, interactionID)
	if !ok {
		return
	}
	var payload startCharacterDialogueRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character dialogue payload", nil)
		return
	}
	run, err := s.characterDialogueStarter.StartCharacterDialogue(request.Context(), workflows.StartCharacterDialogueInput{
		TenantID:      tenantID,
		ProjectID:     interaction.ProjectID,
		InteractionID: interactionID,
		UserTurnID:    strings.TrimSpace(payload.UserTurnID),
		ActorUserID:   s.actorUserID(request),
		RequestID:     requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, characterDialoguePublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, run)
}

func (s *Server) handleListCharacterInteractionEvents(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "events")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character interaction event route not found", nil)
		return
	}
	if _, ok := s.authorizeCharacterInteractionProjectRead(response, request, tenantID, interactionID); !ok {
		return
	}
	afterEventID := afterEventIDFromRequest(request)
	items, err := s.characterConsoleStore.ListEvents(request.Context(), characterconsole.ListEventsInput{
		TenantID: tenantID, InteractionID: interactionID, AfterEventID: afterEventID,
	})
	if err != nil {
		writeCharacterConsoleError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, characterInteractionEventsResponse{
		InteractionID: interactionID,
		AfterEventID:  afterEventID,
		Items:         items,
	})
}

func (s *Server) handleListCharacterProposals(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID := characterInteractionNestedPathPart(request.URL.Path, "proposals")
	if interactionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character proposal route not found", nil)
		return
	}
	interaction, ok := s.authorizeCharacterInteractionProjectRead(response, request, tenantID, interactionID)
	if !ok {
		return
	}
	items, err := s.characterProposalStore.ListProposals(request.Context(), characterconsole.ListProposalsInput{
		TenantID: tenantID, ProjectID: interaction.ProjectID, InteractionID: interactionID,
		ActorUserID: s.actorUserID(request),
	})
	if err != nil {
		writeCharacterProposalError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, characterProposalsResponse{InteractionID: interactionID, Items: items})
}

func (s *Server) handleAdoptCharacterProposal(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	interactionID, assetID := characterProposalAdoptionPathParts(request.URL.Path)
	if interactionID == "" || assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "character proposal adoption route not found", nil)
		return
	}
	interaction, ok := s.authorizeCharacterInteractionCreativeWrite(response, request, tenantID, interactionID)
	if !ok {
		return
	}
	var payload adoptCharacterProposalRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character proposal adoption payload", nil)
		return
	}
	result, err := s.characterProposalStore.AdoptProposal(request.Context(), characterconsole.AdoptProposalInput{
		TenantID: tenantID, ProjectID: interaction.ProjectID, InteractionID: interactionID,
		AssetID: assetID, ActorUserID: s.actorUserID(request), RequestID: requestID(request),
		Note: strings.TrimSpace(payload.Note),
	})
	if err != nil {
		writeCharacterProposalError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, result)
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
	interaction, ok := s.authorizeCharacterInteractionCreativeWrite(response, request, tenantID, interactionID)
	if !ok {
		return
	}
	var payload convertCharacterInteractionToChapterDraftRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid character interaction chapter draft payload", nil)
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
	session, authorized := s.authorizeWorldlineSessionCreativeWrite(response, request, tenantID, sessionID)
	if !authorized {
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
		ProjectID:   strings.TrimSpace(session.ProjectID),
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

func (s *Server) handleStartWorldlineAutoEvolution(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	sessionID := worldlineSessionPathPart(request.URL.Path, "auto-evolutions")
	if sessionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline auto-evolution route not found", nil)
		return
	}
	session, authorized := s.authorizeWorldlineSessionCreativeWrite(response, request, tenantID, sessionID)
	if !authorized {
		return
	}
	var payload startWorldlineAutoEvolutionRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline auto-evolution payload", nil)
		return
	}
	run, err := s.worldlineAutoEvolutionStarter.StartAutoEvolution(request.Context(), worldline.StartAutoEvolutionInput{
		TenantID:    tenantID,
		ProjectID:   strings.TrimSpace(session.ProjectID),
		SessionID:   sessionID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
		MaxSteps:    payload.MaxSteps,
		Options:     cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineAutoEvolutionPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, run)
}

func (s *Server) handleListWorldlinePreparations(response http.ResponseWriter, request *http.Request) {
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
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.worldlinePreparationStore.ListPreparations(request.Context(), worldline.ListPreparationsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlinePreparationListPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, listResponse[worldline.PreparationRecord]{Items: items})
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
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	var payload createWorldlinePreparationRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid worldline preparation payload", nil)
		return
	}
	record, err := s.worldlinePreparationStarter.StartPreparation(request.Context(), worldline.CreatePreparationInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ActorUserID:  s.actorUserID(request),
		RequestID:    requestID(request),
		Goal:         strings.TrimSpace(payload.Goal),
		AnchorPathID: strings.TrimSpace(payload.AnchorPathID),
		AgentRefs:    append([]worldline.PreparationAgentRef(nil), payload.AgentRefs...),
		SourceRefs:   append([]worldline.PreparationSourceRef(nil), payload.SourceRefs...),
		Options:      cloneOptions(sanitizeAssetPayload(payload.Options)),
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlinePreparationStartPublicErrorMessage(code), nil)
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
	sessionID := worldlineSessionPathPart(request.URL.Path, "")
	if sessionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline session route not found", nil)
		return
	}
	record, ok := s.authorizeWorldlineSessionProjectRead(response, request, tenantID, sessionID)
	if !ok {
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
	sessionID := worldlineSessionPathPart(request.URL.Path, "timeline")
	if sessionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline timeline route not found", nil)
		return
	}
	if _, ok := s.authorizeWorldlineSessionProjectRead(response, request, tenantID, sessionID); !ok {
		return
	}
	items, err := s.worldlineTimelineReader.ListTimeline(request.Context(), worldline.ListTimelineInput{
		TenantID:  tenantID,
		SessionID: sessionID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineSessionOwnerPreflightPublicErrorMessage(code), nil)
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
	sessionID := worldlineSessionPathPart(request.URL.Path, "events")
	if sessionID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event route not found", nil)
		return
	}
	if _, ok := s.authorizeWorldlineSessionProjectRead(response, request, tenantID, sessionID); !ok {
		return
	}
	items, err := s.worldlineEventReader.ListEvents(request.Context(), worldline.ListEventsInput{
		TenantID:  tenantID,
		SessionID: sessionID,
		Status:    strings.TrimSpace(request.URL.Query().Get("status")),
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineSessionOwnerPreflightPublicErrorMessage(code), nil)
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
	eventID := worldlineEventAdoptionPathPart(request.URL.Path)
	if eventID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event adoption route not found", nil)
		return
	}
	if !s.authorizeWorldlineEventCreativeWrite(response, request, tenantID, eventID) {
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
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineEventAdoptionPublicErrorMessage(code), nil)
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
	eventID := worldlineEventPathPart(request.URL.Path)
	if eventID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline event mutation route not found", nil)
		return
	}
	if !s.authorizeWorldlineEventCreativeWrite(response, request, tenantID, eventID) {
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
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlineEventMutationPublicErrorMessage(code), nil)
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
	if _, authorized := s.authorizeWorldlineSessionCreativeWrite(response, request, tenantID, sessionID); !authorized {
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
	if _, authorized := s.authorizeWorldlineSessionCreativeWrite(response, request, tenantID, sessionID); !authorized {
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
	prepareID := worldlinePreparationPathPart(request.URL.Path, "")
	if prepareID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline preparation route not found", nil)
		return
	}
	record, ok := s.authorizeWorldlinePreparationProjectRead(response, request, tenantID, prepareID)
	if !ok {
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
	prepareID := worldlinePreparationPathPart(request.URL.Path, "agents")
	if prepareID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "worldline prepared agents route not found", nil)
		return
	}
	if _, ok := s.authorizeWorldlinePreparationProjectRead(response, request, tenantID, prepareID); !ok {
		return
	}
	items, err := s.worldlinePreparationStore.ListPreparedAgents(request.Context(), worldline.ListPreparedAgentsInput{
		TenantID:  tenantID,
		PrepareID: prepareID,
	})
	if err != nil {
		code := worldline.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, worldlinePreparationOwnerPreflightPublicErrorMessage(code), nil)
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
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
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

func (s *Server) handleGetAssetSearchCapabilities(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID := projectIDFromPathWithSuffix(request.URL.Path, "assets/search-capabilities")
	if projectID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project asset search capabilities route not found", nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
		return
	}
	capabilities, err := assets.GetSearchCapabilities(request.Context(), tenantID, projectID, s.assetQueryEmbeddingResolver, s.assetSearchIndexChecker)
	if err != nil {
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetSearchCapabilitiesPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, capabilities)
}

func assetSearchCapabilitiesPublicErrorMessage(code string) string {
	switch code {
	case "ASSET_BACKEND_UNCONFIGURED":
		return "asset backend is not configured"
	case "ASSET_SEARCH_INDEX_QUERY_FAILED":
		return "asset vector search index check failed"
	case "LLM_BINDING_BACKEND_UNCONFIGURED":
		return "LLM binding backend is not configured"
	case "LLM_BINDING_QUERY_FAILED":
		return "asset query embedding binding query failed"
	case "VALIDATION_FAILED":
		return "invalid asset search capabilities request"
	default:
		return "asset search capabilities query failed"
	}
}

func (s *Server) handleSearchAssets(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	if s.actorUserID(request) == "" {
		writeError(response, request, http.StatusUnauthorized, auth.CodeUnauthenticated, "user context is required", nil)
		return
	}
	var payload assetSearchRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid asset search payload", nil)
		return
	}
	projectID := strings.TrimSpace(payload.ProjectID)
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, projectID) {
		return
	}
	items, err := s.assetReader.SearchAssets(request.Context(), assets.SearchAssetsInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		Query:     strings.TrimSpace(payload.Query),
		Mode:      strings.TrimSpace(payload.Mode),
		Filters:   payload.Filters,
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
	if strings.TrimSpace(payload.ProjectID) == "" {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid archive memory review payload", nil)
		return
	}
	owner, err := s.archiveMemoryReader.GetMemory(request.Context(), assets.GetArchiveMemoryInput{
		TenantID: tenantID,
		MemoryID: memoryID,
	})
	if err != nil {
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, archiveMemoryOwnerPreflightPublicErrorMessage(code), nil)
		return
	}
	projectID := strings.TrimSpace(owner.ProjectID)
	if projectID == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
		return
	}
	input := assets.ArchiveMemoryReviewInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		MemoryID:  memoryID,
		ActorID:   s.actorUserID(request),
		RequestID: requestID(request),
	}
	var record assets.ArchiveMemoryRecord
	if action == "adoptions" {
		record, err = s.archiveMemoryReviewStore.AdoptMemory(request.Context(), input)
	} else {
		record, err = s.archiveMemoryReviewStore.RejectMemory(request.Context(), input)
	}
	if err != nil {
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, archiveMemoryReviewPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, record)
}

func archiveMemoryOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "archive memory was not found"
	case "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED":
		return "archive memory backend is not configured"
	case "ARCHIVE_MEMORY_QUERY_FAILED":
		return "archive memory lookup failed"
	default:
		return "archive memory lookup failed"
	}
}

func archiveMemoryReviewPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "archive memory was not found"
	case "ARCHIVE_MEMORY_REVIEW_BACKEND_UNCONFIGURED":
		return "archive memory review backend is not configured"
	case "VALIDATION_FAILED":
		return "invalid archive memory review request"
	default:
		return "archive memory review failed"
	}
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
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
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
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetBulkActionPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, result)
}

func assetBulkActionPublicErrorMessage(code string) string {
	if code == "ASSET_BULK_ACTION_BACKEND_UNCONFIGURED" {
		return "asset bulk action backend is not configured"
	}
	return "asset bulk action failed"
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
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	if !s.authorizeAssetManage(response, request, tenantID, projectID) {
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusAccepted, startStoryGraphBondGenerationResponse{
		RunID:        run.RunID,
		ProjectID:    run.ProjectID,
		WorkflowType: run.WorkflowType,
		Status:       run.Status,
	})
}

func (s *Server) handleAdoptStoryGraphCandidate(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	projectID, assetID := storyGraphCandidateAdoptionPathParts(request.URL.Path)
	if projectID == "" || assetID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "project story graph candidate adoption route not found", nil)
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	var payload adoptStoryGraphCandidateRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid story graph candidate adoption payload", nil)
		return
	}
	result, err := s.storyGraphCandidateAdoptionStore.AdoptCandidate(request.Context(), storygraph.AdoptCandidateInput{
		TenantID:   tenantID,
		ProjectID:  projectID,
		AssetID:    assetID,
		ActorID:    s.actorUserID(request),
		RequestID:  requestID(request),
		TargetKind: strings.TrimSpace(payload.TargetKind),
	})
	if err != nil {
		code := storygraph.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, storyGraphCandidateAdoptionPublicErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, result)
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
	offset, ok := queryOffset(response, request, "story graph offset must be a non-negative integer")
	if !ok {
		return
	}
	view, err := s.storyGraphReader.GetView(request.Context(), storygraph.GetViewInput{
		TenantID:     tenantID,
		ProjectID:    projectID,
		ViewID:       viewID,
		Types:        commaList(request.URL.Query().Get("types")),
		Limit:        limit,
		Offset:       offset,
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
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
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
	offset, ok := queryOffset(response, request, "story graph cluster offset must be a non-negative integer")
	if !ok {
		return
	}
	clusters, err := s.storyGraphReader.ListClusters(request.Context(), storygraph.ListClustersInput{
		TenantID:  tenantID,
		ProjectID: projectID,
		Limit:     limit,
		Offset:    offset,
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
		code := assets.ErrorCode(err)
		writeError(response, request, statusForAppCode(code), code, assetOwnerPreflightPublicErrorMessage(code), nil)
		return
	}
	if strings.TrimSpace(record.ProjectID) == "" {
		writeError(response, request, http.StatusForbidden, auth.CodeAccessDenied, authPublicErrorMessage(auth.CodeAccessDenied), nil)
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, record.ProjectID) {
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
	if !s.authorizeSingleAssetManage(response, request, tenantID, assetID) {
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
	if !s.authorizeSingleAssetManage(response, request, tenantID, assetID) {
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
	if !s.authorizeSingleAssetManage(response, request, tenantID, assetID) {
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
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
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
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
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
		TenantID:              tenantID,
		Name:                  strings.TrimSpace(payload.Name),
		Provider:              strings.TrimSpace(payload.Provider),
		BaseURL:               strings.TrimSpace(payload.BaseURL),
		APIKey:                strings.TrimSpace(payload.APIKey),
		MaxConcurrency:        payload.MaxConcurrency,
		ExternalProviderOptIn: payload.ExternalProviderOptIn,
		Enabled:               enabled,
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
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
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
		TenantID:              tenantID,
		ChannelID:             channelID,
		Name:                  strings.TrimSpace(payload.Name),
		BaseURL:               strings.TrimSpace(payload.BaseURL),
		APIKey:                strings.TrimSpace(payload.APIKey),
		MaxConcurrency:        payload.MaxConcurrency,
		ExternalProviderOptIn: payload.ExternalProviderOptIn,
		Enabled:               enabled,
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
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
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
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
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

func (s *Server) handlePatchLLMChannelModel(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	channelID, modelID := llmChannelModelPathParts(request.URL.Path)
	if channelID == "" || modelID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "llm channel model route not found", nil)
		return
	}
	if !s.authorizeLLMTenantManage(response, request, tenantID) {
		return
	}
	var payload patchLLMChannelModelRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid llm model payload", nil)
		return
	}
	supportsTools := false
	if payload.SupportsTools != nil {
		supportsTools = *payload.SupportsTools
	}
	supportsJSON := false
	if payload.SupportsJSON != nil {
		supportsJSON = *payload.SupportsJSON
	}
	model, err := s.llmModelStore.UpdateModel(request.Context(), llm.UpdateModelInput{
		TenantID:      tenantID,
		ChannelID:     channelID,
		ModelID:       modelID,
		ContextWindow: payload.ContextWindow,
		SupportsTools: supportsTools,
		SupportsJSON:  supportsJSON,
		InputCost:     payload.InputCost,
		OutputCost:    payload.OutputCost,
	})
	if err != nil {
		writeLLMError(response, request, err)
		return
	}
	writeJSON(response, http.StatusOK, model)
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
	case "LLM_MODEL_BACKEND_UNCONFIGURED":
		return "LLM model backend is not configured"
	case "LLM_MODEL_NOT_FOUND":
		return "LLM model was not found"
	case "LLM_MODEL_UPDATE_FAILED":
		return "LLM model update failed"
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
	case "LLM_MODEL_TOOLS_UNSUPPORTED":
		return "writer_orchestrator binding must support tools"
	case "LLM_QUOTA_BACKEND_FAILED":
		return "LLM quota backend failed"
	case "LLM_BILLING_USAGE_QUERY_FAILED":
		return "LLM billing usage query failed"
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
	message := characterConsolePublicErrorMessage(code)
	writeError(response, request, statusForAppCode(code), code, message, nil)
}

func writeCharacterProposalError(response http.ResponseWriter, request *http.Request, err error) {
	code := characterconsole.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, characterProposalPublicErrorMessage(code), nil)
}

func characterProposalPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid character proposal request"
	case "NOT_FOUND":
		return "character proposal was not found"
	case "CHARACTER_PROPOSAL_ALREADY_ADOPTED":
		return "character proposal is no longer a candidate"
	case "CHARACTER_PROPOSAL_TARGET_CONFLICT":
		return "character proposal target is no longer a candidate"
	case "CHARACTER_PROPOSAL_BACKEND_UNCONFIGURED":
		return "character proposal backend is not configured"
	case "CHARACTER_PROPOSAL_QUERY_FAILED":
		return "character proposal query failed"
	case "CHARACTER_PROPOSAL_ADOPTION_FAILED":
		return "character proposal adoption failed"
	default:
		return "character proposal request failed"
	}
}

func writeCharacterConsoleLLMError(response http.ResponseWriter, request *http.Request, err error) {
	code := llm.ErrorCode(err)
	writeError(response, request, statusForAppCode(code), code, characterConsoleLLMPublicErrorMessage(code), nil)
}

func characterConsolePublicErrorMessage(code string) string {
	switch code {
	case "CHARACTER_INTERACTION_QUERY_FAILED":
		return "character interaction query failed"
	case "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED":
		return "character interaction backend is not configured"
	case "NOT_FOUND":
		return "character interaction was not found"
	default:
		return "character interaction request failed"
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
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	runID := writerRunPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "writer run route not found", nil)
		return
	}
	run, err := s.writerReader.GetWriterRun(request.Context(), workflows.GetWriterRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	writeJSON(response, http.StatusOK, startWriterRunResponse{
		RunID:       run.RunID,
		TraceID:     run.TraceID,
		ProjectID:   run.ProjectID,
		Mode:        run.Mode,
		Instruction: run.Instruction,
		Status:      run.Status,
	})
}

func (s *Server) handleGetWorkflowRun(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	runID := workflowRunPathPart(request.URL.Path)
	if runID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "workflow run route not found", nil)
		return
	}
	run, err := s.workflowReader.GetWorkflowRun(request.Context(), workflows.GetWorkflowRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
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
	run, err := s.writerReader.GetWriterRun(request.Context(), workflows.GetWriterRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	cursor := afterEventIDFromRequest(request)
	events, err := s.writerEventReader.ListWriterEvents(request.Context(), workflows.ListWriterEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: cursor,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	events = sanitizeWriterEvents(events)
	if strings.Contains(request.Header.Get("Accept"), "text/event-stream") {
		// Held-open SSE when stream=1 (or active run); otherwise batch-dump for compatibility.
		holdOpen := request.URL.Query().Get("stream") == "1" || isActiveWriterRunStatus(run.Status)
		if holdOpen {
			writeWriterEventsSSEHeldOpen(response, request, s.writerEventReader, s.writerReader, tenantID, runID, cursor, events, run.Status)
			return
		}
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
	run, err := s.workflowReader.GetWorkflowRun(request.Context(), workflows.GetWorkflowRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerProjectRead(response, request, tenantID, run.ProjectID) {
		return
	}
	events, err := s.workflowEventReader.ListWorkflowEvents(request.Context(), workflows.ListWorkflowEventsInput{
		TenantID:     tenantID,
		RunID:        runID,
		AfterEventID: afterEventIDFromRequest(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	run, err := s.writerReader.GetWriterRun(request.Context(), workflows.GetWriterRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalRunOwnerCreativeWrite(response, request, tenantID, run.ProjectID) {
		return
	}
	cancelled, err := s.writerCanceller.CancelWriterRun(request.Context(), workflows.CancelWriterRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	// CONN-004/005: durable outbox is inserted inside AdoptDraft's transaction via OutboxHook.
	// Temporal dispatch is recovered by the outbox dispatcher after commit.
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
	projectID, ok := s.lookupDraftReviewOwnerProject(response, request, tenantID, draftID, "")
	if !ok {
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	var payload startDraftReviewRequest
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil && !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid draft review payload", nil)
		return
	}
	bodyProjectID := strings.TrimSpace(payload.BodyProjectID)
	if bodyProjectID != "" && bodyProjectID != projectID {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "draft review project_id does not match the draft owner", nil)
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
	projectID, ok := s.lookupDraftReviewOwnerProject(response, request, tenantID, draftID, "")
	if !ok {
		return
	}
	if !s.authorizeProjectRead(response, request, tenantID, projectID) {
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

func (s *Server) handleUpdateDraftReviewIssue(response http.ResponseWriter, request *http.Request) {
	tenantID := strings.TrimSpace(request.Header.Get("X-Tenant-Id"))
	if tenantID == "" {
		writeError(response, request, http.StatusUnauthorized, "UNAUTHENTICATED", "tenant context is required", nil)
		return
	}
	issueID := draftReviewIssuePathPart(request.URL.Path)
	if issueID == "" {
		writeError(response, request, http.StatusNotFound, "NOT_FOUND", "draft review issue route not found", nil)
		return
	}
	projectID, ok := s.lookupDraftReviewOwnerProject(response, request, tenantID, "", issueID)
	if !ok {
		return
	}
	if !s.authorizeProject(response, request, tenantID, projectID, auth.PermissionCreativeWrite) {
		return
	}
	if s.draftReviewIssueStore == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WRITER_REVIEW_BACKEND_UNCONFIGURED", publicDraftReviewErrorMessage("WRITER_REVIEW_BACKEND_UNCONFIGURED"), nil)
		return
	}
	var payload updateDraftReviewIssueRequest
	decoder := json.NewDecoder(io.LimitReader(request.Body, 64<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid draft review issue payload", nil)
		return
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", "invalid draft review issue payload", nil)
		return
	}
	result, err := s.draftReviewIssueStore.UpdateIssueStatus(request.Context(), workflows.UpdateDraftReviewIssueInput{
		TenantID: tenantID, ProjectID: projectID, IssueID: issueID,
		ActorUserID: s.actorUserID(request), RequestID: requestID(request),
		Status: strings.TrimSpace(payload.Status), Version: strings.TrimSpace(payload.Version),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicDraftReviewErrorMessage(code), nil)
		return
	}
	writeJSON(response, http.StatusOK, result)
}

func (s *Server) lookupDraftReviewOwnerProject(
	response http.ResponseWriter,
	request *http.Request,
	tenantID string,
	draftID string,
	issueID string,
) (string, bool) {
	if s.draftReviewOwnerLookup == nil {
		writeError(response, request, http.StatusServiceUnavailable, "WRITER_REVIEW_BACKEND_UNCONFIGURED", publicDraftReviewErrorMessage("WRITER_REVIEW_BACKEND_UNCONFIGURED"), nil)
		return "", false
	}
	projectID, err := s.draftReviewOwnerLookup.LookupDraftReviewProject(request.Context(), workflows.DraftReviewOwnerLookupInput{
		TenantID: tenantID, DraftID: draftID, IssueID: issueID, ActorUserID: s.actorUserID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, publicDraftReviewErrorMessage(code), nil)
		return "", false
	}
	projectID = strings.TrimSpace(projectID)
	if projectID == "" {
		writeError(response, request, http.StatusServiceUnavailable, "WRITER_REVIEW_QUERY_FAILED", publicDraftReviewErrorMessage("WRITER_REVIEW_QUERY_FAILED"), nil)
		return "", false
	}
	return projectID, true
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
	if strings.EqualFold(strings.TrimSpace(request.URL.Query().Get("format")), workflows.ManuscriptArtifactFormatTXT) {
		s.handleDownloadManuscriptArtifact(response, request, tenantID, projectID)
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

func (s *Server) handleDownloadManuscriptArtifact(
	response http.ResponseWriter,
	request *http.Request,
	tenantID string,
	projectID string,
) {
	if s.manuscriptArtifactExporter == nil {
		writeError(response, request, http.StatusServiceUnavailable, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", "manuscript export backend is not configured", nil)
		return
	}
	artifact, err := s.manuscriptArtifactExporter.ExportManuscriptArtifact(request.Context(), workflows.ExportManuscriptArtifactInput{
		TenantID: tenantID, ProjectID: projectID, Format: workflows.ManuscriptArtifactFormatTXT,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForManuscriptArtifactError(code), code, publicManuscriptExportErrorMessage(code), nil)
		return
	}
	response.Header().Set("Content-Type", artifact.ContentType)
	response.Header().Set("Content-Disposition", `attachment; filename="`+artifact.FileName+`"`)
	response.Header().Set("Content-Length", strconv.FormatInt(artifact.SizeBytes, 10))
	response.Header().Set("X-Content-SHA256", artifact.SHA256)
	response.Header().Set("Cache-Control", "private, no-store")
	response.WriteHeader(http.StatusOK)
	_, _ = response.Write(artifact.Content)
}

func statusForManuscriptArtifactError(code string) int {
	switch code {
	case "VALIDATION_FAILED", "MANUSCRIPT_EXPORT_FORMAT_UNSUPPORTED":
		return http.StatusBadRequest
	case "MANUSCRIPT_EMPTY":
		return http.StatusConflict
	case "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED":
		return http.StatusServiceUnavailable
	default:
		return http.StatusInternalServerError
	}
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
	run, err := s.workflowReader.GetWorkflowRun(request.Context(), workflows.GetWorkflowRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalWorkflowRunControl(response, request, tenantID, run) {
		return
	}
	cancelled, err := s.workflowCanceller.CancelWorkflowRun(request.Context(), workflows.CancelWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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
	run, err := s.workflowReader.GetWorkflowRun(request.Context(), workflows.GetWorkflowRunInput{
		TenantID: tenantID,
		RunID:    runID,
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
		return
	}
	if !s.authorizeGlobalWorkflowRunControl(response, request, tenantID, run) {
		return
	}
	retried, err := s.workflowRetrier.RetryWorkflowRun(request.Context(), workflows.RetryWorkflowRunInput{
		TenantID:    tenantID,
		RunID:       runID,
		ActorUserID: s.actorUserID(request),
		RequestID:   requestID(request),
	})
	if err != nil {
		code := workflows.ErrorCode(err)
		writeError(response, request, statusForWorkflowError(err), code, workflowPublicErrorMessage(code), nil)
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

func writerThreadMessagesPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/writer-threads/")
	if !ok {
		return "", ""
	}
	threadID, tail, ok := strings.Cut(suffix, "/")
	if !ok || tail != "messages" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(threadID)
}

func writerApprovalDecisionPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/writer-approvals/")
	if !ok {
		return "", ""
	}
	approvalID, tail, ok := strings.Cut(suffix, "/")
	if !ok || tail != "decision" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(approvalID)
}

func storyGraphPathParts(path string, kind string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/story-graph/"+kind+"/")
	if !ok || strings.Contains(suffix, "/") {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(suffix)
}

func storyGraphCandidateAdoptionPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/projects/")
	projectID, suffix, ok := strings.Cut(remainder, "/story-graph/candidates/")
	if !ok {
		return "", ""
	}
	assetID, tail, ok := strings.Cut(suffix, "/")
	if !ok || tail != "adoptions" {
		return "", ""
	}
	return strings.TrimSpace(projectID), strings.TrimSpace(assetID)
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

func queryOffset(response http.ResponseWriter, request *http.Request, message string) (int, bool) {
	rawOffset := strings.TrimSpace(request.URL.Query().Get("offset"))
	if rawOffset == "" {
		return 0, true
	}
	parsedOffset, err := strconv.Atoi(rawOffset)
	if err != nil || parsedOffset < 0 {
		writeError(response, request, http.StatusBadRequest, "VALIDATION_FAILED", message, nil)
		return 0, false
	}
	return parsedOffset, true
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

func isLLMChannelMutationPath(path string) bool {
	return llmChannelIDFromPath(path) != ""
}

func llmChannelModelPathParts(path string) (string, string) {
	remainder := strings.TrimPrefix(path, "/v1/llm/channels/")
	channelID, rest, ok := strings.Cut(remainder, "/")
	if !ok {
		return "", ""
	}
	prefix, modelID, ok := strings.Cut(rest, "/")
	if !ok || prefix != "models" {
		return "", ""
	}
	channelID = strings.TrimSpace(channelID)
	modelID = strings.TrimSpace(modelID)
	if channelID == "" || modelID == "" || strings.Contains(modelID, "/") {
		return "", ""
	}
	return channelID, modelID
}

func isLLMChannelModelMutationPath(path string) bool {
	channelID, modelID := llmChannelModelPathParts(path)
	return channelID != "" && modelID != ""
}

func llmChannelSyncPathPart(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/llm/channels/")
	channelID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "sync-models" {
		return ""
	}
	return strings.TrimSpace(channelID)
}

func isLLMChannelSyncPath(path string) bool {
	return llmChannelSyncPathPart(path) != ""
}

func uploadIDFromCompletePath(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/uploads/")
	uploadID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "complete" {
		return ""
	}
	if !isSinglePathSegment(uploadID) {
		return ""
	}
	return strings.TrimSpace(uploadID)
}

func isCompleteUploadPath(path string) bool {
	return uploadIDFromCompletePath(path) != ""
}

func uploadIDFromObjectPath(path string) string {
	remainder := strings.TrimPrefix(path, "/v1/uploads/")
	uploadID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "object" {
		return ""
	}
	if !isSinglePathSegment(uploadID) {
		return ""
	}
	return strings.TrimSpace(uploadID)
}

func isUploadSourceObjectPath(path string) bool {
	return uploadIDFromObjectPath(path) != ""
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
	if !strings.HasPrefix(path, "/v1/assets/") {
		return ""
	}
	remainder := strings.TrimPrefix(path, "/v1/assets/")
	assetID, suffix, ok := strings.Cut(remainder, "/")
	assetID = strings.TrimSpace(assetID)
	if !ok || suffix != "adoptions" || assetID == "" || strings.Contains(assetID, "/") || isReservedAssetPathPart(assetID) {
		return ""
	}
	return assetID
}

func assetPathPart(path string) string {
	return singleAssetPathPart(path)
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
	remainder, prefixOK := strings.CutPrefix(path, "/v1/archive-memories/")
	if !prefixOK {
		return ""
	}
	memoryID, rest, ok := strings.Cut(remainder, "/")
	if !ok || rest != suffix || !isSinglePathSegment(memoryID) {
		return ""
	}
	return strings.TrimSpace(memoryID)
}

func isArchiveMemoryAdoptionPath(path string) bool {
	return archiveMemoryReviewPathPart(path, "adoptions") != ""
}

func isArchiveMemoryRejectionPath(path string) bool {
	return archiveMemoryReviewPathPart(path, "rejections") != ""
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
	if sceneID := strings.TrimSpace(payload.TargetSceneID); sceneID != "" {
		builder.WriteString("Target scene id: ")
		builder.WriteString(sceneID)
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
	if targetSceneID := strings.TrimSpace(payload.TargetSceneID); targetSceneID != "" {
		options["target_scene_id"] = targetSceneID
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
	remainder, ok := strings.CutPrefix(path, "/v1/writer-runs/")
	if !ok {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func workflowRunEventsPathPart(path string) string {
	remainder, ok := strings.CutPrefix(path, "/v1/workflow-runs/")
	if !ok {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunEventsPathPart(path string) string {
	remainder, ok := strings.CutPrefix(path, "/v1/seed-runs/")
	if !ok {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "events" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func writerRunPathPart(path string) string {
	runID, ok := strings.CutPrefix(path, "/v1/writer-runs/")
	if !ok || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func workflowRunPathPart(path string) string {
	runID, ok := strings.CutPrefix(path, "/v1/workflow-runs/")
	if !ok || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunPathPart(path string) string {
	runID, ok := strings.CutPrefix(path, "/v1/seed-runs/")
	if !ok || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunCancelPathPart(path string) string {
	const prefix = "/v1/seed-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedRunRetryPathPart(path string) string {
	const prefix = "/v1/seed-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "retry" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func seedSegmentRetryPathPart(path string) string {
	const prefix = "/v1/seed-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "segments/retry" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func normalizeNonEmptyStrings(values []string) []string {
	normalized := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			normalized = append(normalized, value)
		}
	}
	return normalized
}

func writerRunCancelPathPart(path string) string {
	const prefix = "/v1/writer-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func draftAdoptionPathPart(path string) string {
	remainder, prefixOK := strings.CutPrefix(path, "/v1/drafts/")
	if !prefixOK {
		return ""
	}
	draftID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "adoptions" || !isSinglePathSegment(draftID) {
		return ""
	}
	return strings.TrimSpace(draftID)
}

func draftReviewPathPart(path string) string {
	remainder, prefixOK := strings.CutPrefix(path, "/v1/drafts/")
	if !prefixOK {
		return ""
	}
	draftID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "reviews" || !isSinglePathSegment(draftID) {
		return ""
	}
	return strings.TrimSpace(draftID)
}

func isDraftAdoptionPath(path string) bool {
	return draftAdoptionPathPart(path) != ""
}

func isDraftReviewPath(path string) bool {
	return draftReviewPathPart(path) != ""
}

func isDraftReviewIssuePath(path string) bool {
	return draftReviewIssuePathPart(path) != ""
}

func draftReviewIssuePathPart(path string) string {
	const prefix = "/v1/draft-review-issues/"
	issueID := strings.TrimSpace(strings.TrimPrefix(path, prefix))
	if issueID == "" || issueID == path || strings.Contains(issueID, "/") {
		return ""
	}
	return issueID
}

func characterInteractionNestedPathPart(path string, expectedSuffix string) string {
	const prefix = "/v1/character-interactions/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	remainder := strings.TrimPrefix(path, prefix)
	interactionID, suffix, ok := strings.Cut(remainder, "/")
	interactionID = strings.TrimSpace(interactionID)
	if !ok || suffix != expectedSuffix || interactionID == "" || strings.Contains(interactionID, "/") {
		return ""
	}
	return interactionID
}

func characterInteractionPathPart(path string) string {
	const prefix = "/v1/character-interactions/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	interactionID := strings.TrimSpace(strings.TrimPrefix(path, prefix))
	if interactionID == "" || strings.Contains(interactionID, "/") {
		return ""
	}
	return interactionID
}

func characterProposalAdoptionPathParts(path string) (string, string) {
	const prefix = "/v1/character-interactions/"
	remainder, ok := strings.CutPrefix(path, prefix)
	if !ok {
		return "", ""
	}
	interactionID, remainder, ok := strings.Cut(remainder, "/proposals/")
	if !ok || !isSinglePathSegment(interactionID) {
		return "", ""
	}
	assetID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "adoptions" || !isSinglePathSegment(assetID) {
		return "", ""
	}
	return strings.TrimSpace(interactionID), strings.TrimSpace(assetID)
}

func isCharacterProposalAdoptionPath(path string) bool {
	interactionID, assetID := characterProposalAdoptionPathParts(path)
	return interactionID != "" && assetID != ""
}

func workflowRunCancelPathPart(path string) string {
	const prefix = "/v1/workflow-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "cancel" || !isSinglePathSegment(runID) {
		return ""
	}
	return strings.TrimSpace(runID)
}

func workflowRunRetryPathPart(path string) string {
	const prefix = "/v1/workflow-runs/"
	remainder, prefixOK := strings.CutPrefix(path, prefix)
	if !prefixOK {
		return ""
	}
	runID, suffix, ok := strings.Cut(remainder, "/")
	if !ok || suffix != "retry" || !isSinglePathSegment(runID) {
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

// requiredWriterRunModules returns LLM modules that must be bound before Pi dual-stage
// writer admission. Pi always runs writer_orchestrator then writer_composer.
func requiredWriterRunModules(options map[string]any) []string {
	primary := moduleKeyFromOptions(options)
	required := []string{"writer_orchestrator", "writer_composer"}
	seen := map[string]struct{}{"writer_orchestrator": {}, "writer_composer": {}}
	if _, ok := seen[primary]; !ok && primary != "" {
		required = append(required, primary)
	}
	return required
}

func reviewAfterWriteEnabled(options map[string]any) bool {
	if options == nil {
		return false
	}
	switch value := options["review_after_write"].(type) {
	case bool:
		return value
	case string:
		normalized := strings.ToLower(strings.TrimSpace(value))
		return normalized == "1" || normalized == "true" || normalized == "yes" || normalized == "on"
	case float64:
		return value != 0
	default:
		return false
	}
}

func writerThreadPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid writer thread request"
	case "NOT_FOUND", "WRITER_APPROVAL_NOT_FOUND":
		return "writer thread resource not found"
	case "WORKFLOW_BACKEND_UNCONFIGURED":
		return "writer thread backend is not configured"
	case "WRITER_THREAD_QUERY_FAILED", "WRITER_THREAD_MUTATION_FAILED":
		return "writer thread request failed"
	case "WRITER_APPROVAL_MUTATION_FAILED":
		return "writer approval request failed"
	default:
		return "writer thread request failed"
	}
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

func workflowPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "workflow run not found"
	case "VALIDATION_FAILED":
		return "invalid workflow request"
	case "WORKFLOW_QUERY_FAILED":
		return "workflow query failed"
	case "WORKFLOW_EVENT_QUERY_FAILED":
		return "workflow event query failed"
	case "EVENT_CURSOR_NOT_FOUND":
		return "workflow event cursor not found"
	case "WORKFLOW_BACKEND_UNCONFIGURED":
		return "workflow backend is not configured"
	case "IDEMPOTENCY_CONFLICT":
		return "request_id was already used with a different writer run request"
	case "WORKFLOW_RETRY_BACKEND_UNCONFIGURED":
		return "workflow retry backend is not configured"
	case "WORKFLOW_RETRY_NOT_ALLOWED":
		return "workflow run is not retryable"
	case "WORKFLOW_RETRY_FAILED":
		return "workflow retry failed"
	case "SEED_SEGMENT_RETRY_BACKEND_UNCONFIGURED":
		return "seed segment retry backend is not configured"
	case "SEED_SEGMENT_RETRY_FAILED":
		return "seed segment retry failed"
	default:
		return "workflow request failed"
	}
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
	case "UNAUTHENTICATED":
		return "sign in is required to adopt a draft"
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
	case "WRITER_REVIEW_ISSUE_WRITE_FAILED":
		return "writer review issue update failed"
	case "WRITER_REVIEW_ISSUE_CONFLICT":
		return "writer review issue changed; reload before updating"
	case "DRAFT_NOT_CANDIDATE":
		return "writer review requires a candidate draft"
	case "IDEMPOTENCY_CONFLICT":
		return "request_id was already used with a different writer review request"
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
	case "MANUSCRIPT_EMPTY":
		return "manuscript has no adopted content to export"
	case "MANUSCRIPT_EXPORT_FORMAT_UNSUPPORTED", "VALIDATION_FAILED":
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
	case "DRAFT_NOT_CANDIDATE":
		return http.StatusConflict
	case "EVENT_CURSOR_NOT_FOUND":
		return http.StatusBadRequest
	case "NOT_FOUND":
		return http.StatusNotFound
	case "WRITER_APPROVAL_NOT_FOUND":
		return http.StatusNotFound
	case "LLM_CHANNEL_NOT_FOUND":
		return http.StatusNotFound
	case "LLM_MODEL_NOT_FOUND":
		return http.StatusNotFound
	case "LLM_BINDING_NOT_FOUND":
		return http.StatusNotFound
	case "LLM_MODEL_TOOLS_UNSUPPORTED":
		return http.StatusUnprocessableEntity
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
	case "WORKFLOW_RETRY_NOT_ALLOWED":
		return http.StatusConflict
	case "WORLDLINE_STEP_ACTIVE":
		return http.StatusConflict
	case "WORLDLINE_AUTO_EVOLUTION_ACTIVE":
		return http.StatusConflict
	case "CURRENT_WORLD_REQUIRED":
		return http.StatusConflict
	case "WORLDLINE_SESSION_NOT_ACTIVE":
		return http.StatusConflict
	case "IDEMPOTENCY_CONFLICT":
		return http.StatusConflict
	case "WRITER_REVIEW_ISSUE_CONFLICT":
		return http.StatusConflict
	case "CHARACTER_TURN_ACTIVE":
		return http.StatusConflict
	case "CHARACTER_PROPOSAL_ALREADY_ADOPTED":
		return http.StatusConflict
	case "CHARACTER_PROPOSAL_TARGET_CONFLICT":
		return http.StatusConflict
	default:
		return http.StatusServiceUnavailable
	}
}

func characterDialoguePublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid character dialogue request"
	case "CHARACTER_TURN_ACTIVE":
		return "character interaction already has an active dialogue turn"
	case "CHARACTER_DIALOGUE_BACKEND_UNCONFIGURED":
		return "character dialogue backend is not configured"
	case "WORKFLOW_FAILED":
		return "character dialogue workflow failed to start"
	default:
		return "character dialogue request failed"
	}
}

func assetOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "asset was not found"
	case "ASSET_BACKEND_UNCONFIGURED":
		return "asset backend is not configured"
	case "ASSET_QUERY_FAILED":
		return "asset query failed"
	default:
		return "asset request failed"
	}
}

func worldlineSessionOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "worldline session was not found"
	case "VALIDATION_FAILED":
		return "invalid worldline session lookup"
	case "WORLDLINE_SESSION_BACKEND_UNCONFIGURED":
		return "worldline session backend is not configured"
	case "WORLDLINE_QUERY_FAILED":
		return "worldline session lookup failed"
	default:
		return "worldline session lookup failed"
	}
}

func worldlineAutoEvolutionPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid worldline auto-evolution request"
	case "NOT_FOUND":
		return "worldline session was not found"
	case "CURRENT_WORLD_REQUIRED":
		return "worldline auto-evolution requires the active current_world session"
	case "WORLDLINE_SESSION_NOT_ACTIVE":
		return "worldline session is not active"
	case "WORLDLINE_AUTO_EVOLUTION_ACTIVE":
		return "worldline session already has an active auto-evolution"
	case "WORLDLINE_AUTO_EVOLUTION_BACKEND_UNCONFIGURED":
		return "worldline auto-evolution backend is not configured"
	case "WORKFLOW_ADMISSION_FAILED":
		return "worldline auto-evolution admission failed"
	case "WORKFLOW_FAILED":
		return "worldline auto-evolution workflow failed to start"
	default:
		return "worldline auto-evolution request failed"
	}
}

func worldlinePreparationListPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid worldline preparation list request"
	case "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED":
		return "worldline preparation backend is not configured"
	case "WORLDLINE_QUERY_FAILED":
		return "worldline preparation query failed"
	default:
		return "worldline preparation list request failed"
	}
}

func worldlinePreparationStartPublicErrorMessage(code string) string {
	switch code {
	case "VALIDATION_FAILED":
		return "invalid worldline preparation request"
	case "IDEMPOTENCY_CONFLICT":
		return "worldline preparation request_id conflicts with an existing request"
	case "NOT_FOUND":
		return "worldline preparation source was not found"
	case "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED":
		return "worldline preparation backend is not configured"
	case "WORKFLOW_ADMISSION_FAILED":
		return "worldline preparation admission failed"
	case "WORKFLOW_FAILED":
		return "worldline preparation workflow failed to start"
	default:
		return "worldline preparation request failed"
	}
}

func worldlinePreparationOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "worldline preparation was not found"
	case "VALIDATION_FAILED":
		return "invalid worldline preparation lookup"
	case "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED":
		return "worldline preparation backend is not configured"
	case "WORLDLINE_QUERY_FAILED":
		return "worldline preparation lookup failed"
	default:
		return "worldline preparation lookup failed"
	}
}

func worldlineEventOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "worldline event was not found"
	case "VALIDATION_FAILED":
		return "invalid worldline event lookup"
	case "WORLDLINE_EVENT_BACKEND_UNCONFIGURED":
		return "worldline event backend is not configured"
	case "WORLDLINE_QUERY_FAILED":
		return "worldline event lookup failed"
	default:
		return "worldline event lookup failed"
	}
}

func characterInteractionOwnerPreflightPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "character interaction was not found"
	case "CHARACTER_INTERACTION_BACKEND_UNCONFIGURED":
		return "character interaction backend is not configured"
	case "CHARACTER_INTERACTION_QUERY_FAILED":
		return "character interaction lookup failed"
	default:
		return "character interaction lookup failed"
	}
}

func worldlineEventAdoptionPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "worldline event was not found"
	case "VALIDATION_FAILED":
		return "invalid worldline event adoption request"
	case "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED":
		return "worldline event adoption backend is not configured"
	default:
		return "worldline event adoption failed"
	}
}

func worldlineEventMutationPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "worldline event was not found"
	case "VALIDATION_FAILED":
		return "invalid worldline event mutation request"
	case "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED":
		return "worldline event mutation backend is not configured"
	default:
		return "worldline event mutation failed"
	}
}

func storyGraphCandidateAdoptionPublicErrorMessage(code string) string {
	switch code {
	case "NOT_FOUND":
		return "story graph candidate was not found"
	case "VALIDATION_FAILED":
		return "invalid story graph candidate adoption request"
	case "STORY_GRAPH_CANDIDATE_ADOPTION_BACKEND_UNCONFIGURED":
		return "story graph candidate adoption backend is not configured"
	default:
		return "story graph candidate adoption failed"
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
	response.Header().Set("Connection", "keep-alive")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	for _, event := range events {
		writeWriterEventSSEFrame(response, event)
	}
	if flusher, ok := response.(http.Flusher); ok {
		flusher.Flush()
	}
}

func isActiveWriterRunStatus(status string) bool {
	status = strings.TrimSpace(status)
	return status == "queued" || status == "running"
}

func isTerminalWriterEventType(eventType string) bool {
	switch eventType {
	case "writer.run.completed", "writer.run.failed", "writer.run.cancelled":
		return true
	default:
		return false
	}
}

func writeWriterEventSSEFrame(response http.ResponseWriter, event workflows.WriterEvent) {
	payload, err := json.Marshal(event)
	if err != nil {
		return
	}
	_, _ = response.Write([]byte("id: " + event.EventID + "\n"))
	_, _ = response.Write([]byte("event: workflow.event\n"))
	_, _ = response.Write([]byte("data: " + string(payload) + "\n\n"))
}

// writeWriterEventsSSEHeldOpen streams known events then poll-forwards new ones until
// terminal event, client disconnect, or hold budget (25s) is exhausted.
func writeWriterEventsSSEHeldOpen(
	response http.ResponseWriter,
	request *http.Request,
	eventReader workflows.WriterEventReader,
	runReader workflows.WriterReader,
	tenantID string,
	runID string,
	initialCursor string,
	initialEvents []workflows.WriterEvent,
	initialStatus string,
) {
	response.Header().Set("Content-Type", "text/event-stream")
	response.Header().Set("Cache-Control", "no-cache")
	response.Header().Set("Connection", "keep-alive")
	response.Header().Set("X-Accel-Buffering", "no")
	response.WriteHeader(http.StatusOK)
	flusher, _ := response.(http.Flusher)

	cursor := strings.TrimSpace(initialCursor)
	for _, event := range initialEvents {
		writeWriterEventSSEFrame(response, event)
		cursor = event.EventID
		if isTerminalWriterEventType(event.EventType) {
			if flusher != nil {
				flusher.Flush()
			}
			return
		}
	}
	if flusher != nil {
		flusher.Flush()
	}

	status := strings.TrimSpace(initialStatus)
	if !isActiveWriterRunStatus(status) {
		// Reads are paginated; a finished run may still have pages beyond the
		// initial batch. Drain them so the client receives the terminal event.
		drainWriterEventsSSE(request, response, flusher, eventReader, tenantID, runID, cursor)
		return
	}

	deadline := time.Now().Add(25 * time.Second)
	ticker := time.NewTicker(700 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-request.Context().Done():
			return
		case <-ticker.C:
			if time.Now().After(deadline) {
				_, _ = response.Write([]byte(": hold-timeout\n\n"))
				if flusher != nil {
					flusher.Flush()
				}
				return
			}
			if eventReader == nil {
				return
			}
			next, err := eventReader.ListWriterEvents(request.Context(), workflows.ListWriterEventsInput{
				TenantID:     tenantID,
				RunID:        runID,
				AfterEventID: cursor,
			})
			if err != nil {
				_, _ = response.Write([]byte(": poll-error\n\n"))
				if flusher != nil {
					flusher.Flush()
				}
				continue
			}
			next = sanitizeWriterEvents(next)
			for _, event := range next {
				writeWriterEventSSEFrame(response, event)
				cursor = event.EventID
				if isTerminalWriterEventType(event.EventType) {
					if flusher != nil {
						flusher.Flush()
					}
					return
				}
			}
			if flusher != nil {
				flusher.Flush()
			}
			if runReader != nil {
				if run, err := runReader.GetWriterRun(request.Context(), workflows.GetWriterRunInput{TenantID: tenantID, RunID: runID}); err == nil {
					status = run.Status
					if !isActiveWriterRunStatus(status) {
						// The run reached a terminal status between pages; flush any
						// remaining event pages (including the terminal event) first.
						drainWriterEventsSSE(request, response, flusher, eventReader, tenantID, runID, cursor)
						return
					}
				}
			}
			// Heartbeat keeps intermediaries from buffering/closing idle streams.
			_, _ = response.Write([]byte(": keepalive\n\n"))
			if flusher != nil {
				flusher.Flush()
			}
		}
	}
}

// drainWriterEventsSSE pages through stored writer events from cursor onward and
// writes every page to the stream, stopping at a terminal event, an empty page,
// or client disconnect. Used when the run is already terminal so the paginated
// reader (default page size 100) does not strand events past the first page.
func drainWriterEventsSSE(
	request *http.Request,
	response http.ResponseWriter,
	flusher http.Flusher,
	eventReader workflows.WriterEventReader,
	tenantID string,
	runID string,
	cursor string,
) {
	if eventReader == nil {
		return
	}
	for {
		if request.Context().Err() != nil {
			return
		}
		next, err := eventReader.ListWriterEvents(request.Context(), workflows.ListWriterEventsInput{
			TenantID:     tenantID,
			RunID:        runID,
			AfterEventID: cursor,
		})
		if err != nil || len(next) == 0 {
			if flusher != nil {
				flusher.Flush()
			}
			return
		}
		next = sanitizeWriterEvents(next)
		for _, event := range next {
			writeWriterEventSSEFrame(response, event)
			cursor = event.EventID
			if isTerminalWriterEventType(event.EventType) {
				if flusher != nil {
					flusher.Flush()
				}
				return
			}
		}
		if flusher != nil {
			flusher.Flush()
		}
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

func sanitizeWriterEvents(events []workflows.WriterEvent) []workflows.WriterEvent {
	sanitized := make([]workflows.WriterEvent, 0, len(events))
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
	if idempotencyKey := strings.TrimSpace(request.Header.Get("Idempotency-Key")); idempotencyKey != "" {
		if safeRequestID(idempotencyKey) {
			return idempotencyKey
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
