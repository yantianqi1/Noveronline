package assetdistillation

import (
	"errors"
	"net/http"
	"time"
)

const (
	ModuleKey               = "writer_asset_distiller"
	WorkflowType            = "manuscript_asset_distillation"
	WorkflowName            = "ManuscriptAssetDistillationWorkflow"
	TaskQueue               = "writer-planning"
	ExtractorContractV1     = 1
	CodeValidationFailed    = "VALIDATION_FAILED"
	CodeNotFound            = "ASSET_DISTILLATION_NOT_FOUND"
	CodeConflict            = "ASSET_DISTILLATION_CONFLICT"
	CodeAccessDenied        = "ASSET_DISTILLATION_ACCESS_DENIED"
	CodeBackendUnconfigured = "ASSET_DISTILLATION_BACKEND_UNCONFIGURED"
	CodeStartFailed         = "ASSET_DISTILLATION_START_FAILED"
	CodeIdempotencyConflict = "IDEMPOTENCY_CONFLICT"
	CodeProposalStale       = "ASSET_PROPOSAL_STALE"
	CodeTargetConflict      = "ASSET_TARGET_VERSION_CONFLICT"
)

type AppError struct {
	Code    string
	Message string
	cause   error
}

func (e *AppError) Error() string {
	if e == nil {
		return ""
	}
	return e.Message
}
func (e *AppError) Unwrap() error { return e.cause }

func appError(code, message string) error { return &AppError{Code: code, Message: message} }
func ErrorCode(err error) string {
	var target *AppError
	if errors.As(err, &target) {
		return target.Code
	}
	return "ASSET_DISTILLATION_FAILED"
}

func HTTPStatus(err error) int {
	switch ErrorCode(err) {
	case CodeValidationFailed:
		return http.StatusBadRequest
	case CodeNotFound:
		return http.StatusNotFound
	case CodeAccessDenied:
		return http.StatusForbidden
	case CodeConflict, CodeIdempotencyConflict, CodeProposalStale, CodeTargetConflict:
		return http.StatusConflict
	case CodeBackendUnconfigured:
		return http.StatusServiceUnavailable
	default:
		return http.StatusInternalServerError
	}
}

type Scope struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
}

type Settings struct {
	ProjectID         string   `json:"project_id"`
	TriggerMode       string   `json:"trigger_mode"`
	EnabledAssetTypes []string `json:"enabled_asset_types"`
	UpdatedAt         string   `json:"updated_at,omitempty"`
}

type SettingsPatch struct {
	TriggerMode       *string  `json:"trigger_mode"`
	EnabledAssetTypes []string `json:"enabled_asset_types"`
}

type SourceBlock struct {
	BlockID      string `json:"block_id"`
	BlockVersion int    `json:"block_version"`
	ContentSHA   string `json:"content_sha256"`
	ChapterID    string `json:"chapter_id,omitempty"`
	SceneID      string `json:"scene_id,omitempty"`
}

type StartManualInput struct {
	Scope                 Scope
	BlockIDs              []string
	ExpectedVersions      map[string]int
	ChapterID             string
	ExpectedBlockVersions map[string]int
}

type Admission struct {
	RunID        string `json:"run_id"`
	RequestID    string `json:"request_id"`
	ProjectID    string `json:"project_id"`
	WorkflowType string `json:"workflow_type"`
	ModuleKey    string `json:"module_key"`
	Status       string `json:"status"`
	TriggerKind  string `json:"trigger_kind"`
	Replay       bool   `json:"replay"`
}

type ProposalSummary struct {
	CandidateAssetID      string   `json:"candidate_asset_id"`
	ProjectID             string   `json:"project_id"`
	RequestID             string   `json:"request_id"`
	Operation             string   `json:"operation"`
	ReviewStatus          string   `json:"review_status"`
	NormalizedIdentity    string   `json:"normalized_identity"`
	Title                 string   `json:"title"`
	AssetType             string   `json:"asset_type"`
	Summary               string   `json:"summary,omitempty"`
	TargetAssetID         string   `json:"target_asset_id,omitempty"`
	ExpectedTargetVersion *int     `json:"expected_target_version,omitempty"`
	Confidence            *float64 `json:"confidence,omitempty"`
	EvidenceCount         int      `json:"evidence_count"`
	CreatedAt             string   `json:"created_at"`
}

type ProposalDetail struct {
	ProposalSummary
	AcceptedAssetID string            `json:"accepted_asset_id,omitempty"`
	DecisionNote    string            `json:"decision_note,omitempty"`
	Evidence        []EvidencePublic  `json:"evidence"`
	EvidencePrivate []EvidencePrivate `json:"evidence_private,omitempty"`
	Payload         map[string]any    `json:"payload,omitempty"`
}

type EvidencePublic struct {
	EvidenceID   string `json:"evidence_id"`
	BlockID      string `json:"block_id"`
	BlockVersion int    `json:"block_version"`
	StartOffset  int    `json:"start_offset"`
	EndOffset    int    `json:"end_offset"`
	Current      bool   `json:"current"`
}

type EvidencePrivate struct {
	EvidenceID   string `json:"evidence_id"`
	EvidenceText string `json:"evidence_text"`
}

type DecisionInput struct {
	Scope                 Scope
	CandidateAssetID      string
	Decision              string // accept_create | accept_update | reject
	TargetLifecycle       string
	TargetAssetID         string
	ExpectedTargetVersion int
	Note                  string
}

type DecisionResult struct {
	CandidateAssetID string `json:"candidate_asset_id"`
	ReviewStatus     string `json:"review_status"`
	AcceptedAssetID  string `json:"accepted_asset_id,omitempty"`
	Replay           bool   `json:"replay,omitempty"`
}

type OutboxItem struct {
	RequestID   string
	TenantID    string
	ProjectID   string
	RunID       string
	TriggerKind string
	Attempt     int
}

type TemporalClient interface {
	ExecuteWorkflow(ctx interface {
		Deadline() (time.Time, bool)
		Done() <-chan struct{}
		Err() error
		Value(any) any
	}, options any, workflow any, args ...any) (any, error)
}
