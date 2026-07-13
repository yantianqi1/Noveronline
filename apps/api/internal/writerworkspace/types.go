package writerworkspace

import (
	"context"
	"errors"
	"net/http"
	"time"
)

const (
	CodeValidationFailed = "VALIDATION_FAILED"
	CodeNotFound         = "WRITER_WORKSPACE_NOT_FOUND"
	CodeConflict         = "WRITER_WORKSPACE_VERSION_CONFLICT"
	CodeQueryFailed      = "WRITER_WORKSPACE_QUERY_FAILED"
	CodeReorderInvalid   = "WRITER_WORKSPACE_REORDER_INVALID"
	CodeAccessDenied     = "WRITER_WORKSPACE_ACCESS_DENIED"
)

type Error struct{ Code, Message string }

func (e *Error) Error() string         { return e.Message }
func coded(code, message string) error { return &Error{Code: code, Message: message} }
func ErrorCode(err error) string {
	var target *Error
	if errors.As(err, &target) {
		return target.Code
	}
	return CodeQueryFailed
}

type Scope struct{ TenantID, ProjectID, ActorUserID, RequestID string }
type PrivateFields struct {
	Brief   string `json:"brief"`
	Outline string `json:"outline"`
	Content string `json:"content_text"`
}
type Chapter struct {
	ChapterID string         `json:"chapter_id"`
	ProjectID string         `json:"project_id"`
	Title     string         `json:"title"`
	Status    string         `json:"status"`
	Order     int            `json:"chapter_order"`
	Version   int64          `json:"optimistic_version"`
	Private   *PrivateFields `json:"private,omitempty"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
}
type Scene struct {
	SceneID   string         `json:"scene_id"`
	ChapterID string         `json:"chapter_id"`
	ProjectID string         `json:"project_id"`
	Title     string         `json:"title"`
	Status    string         `json:"status"`
	Order     int            `json:"scene_order"`
	Version   int64          `json:"optimistic_version"`
	Private   *PrivateFields `json:"private,omitempty"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
}
type Version struct {
	VersionID  string         `json:"version_id"`
	ParentID   string         `json:"parent_id"`
	Title      string         `json:"title"`
	Status     string         `json:"status"`
	ChangeKind string         `json:"change_kind"`
	Version    int64          `json:"version_number"`
	Private    *PrivateFields `json:"private,omitempty"`
	CreatedAt  time.Time      `json:"created_at"`
}
type ChapterPatch struct {
	ExpectedVersion int64   `json:"expected_version"`
	Title           *string `json:"title"`
	Status          *string `json:"status"`
	Brief           *string `json:"brief"`
	Outline         *string `json:"outline"`
	Content         *string `json:"content_text"`
}
type ScenePatch = ChapterPatch
type CreateChapterInput struct {
	Scope                                  Scope
	Title, Status, Brief, Outline, Content string
	Order                                  *int
}
type CreateSceneInput struct {
	Scope                                             Scope
	ChapterID, Title, Status, Brief, Outline, Content string
	Order                                             *int
}

type OutlineVersion struct {
	OutlineVersionID      string    `json:"outline_version_id"`
	ProjectID             string    `json:"project_id"`
	ScopeType             string    `json:"scope_type"`
	ScopeID               string    `json:"scope_id,omitempty"`
	Lifecycle             string    `json:"lifecycle"`
	Title                 string    `json:"title"`
	OutlineText           string    `json:"outline_text"`
	RestoredFromVersionID string    `json:"restored_from_version_id,omitempty"`
	Version               int64     `json:"version_number"`
	CreatedAt             time.Time `json:"created_at"`
}
type CreateOutlineInput struct {
	Scope       Scope  `json:"-"`
	ScopeType   string `json:"scope_type"`
	ScopeID     string `json:"scope_id"`
	Lifecycle   string `json:"lifecycle"`
	Title       string `json:"title"`
	OutlineText string `json:"outline_text"`
}

type BookPlan struct {
	BookPlanID         string    `json:"book_plan_id"`
	ProjectID          string    `json:"project_id"`
	Title              string    `json:"title"`
	Status             string    `json:"status"`
	Premise            string    `json:"premise"`
	PlanningJSON       string    `json:"planning"`
	LastRunID          string    `json:"last_run_id,omitempty"`
	LastRunStatus      string    `json:"last_run_status,omitempty"`
	TargetChapterCount *int      `json:"target_chapter_count,omitempty"`
	Version            int64     `json:"optimistic_version"`
	CreatedAt          time.Time `json:"created_at"`
	UpdatedAt          time.Time `json:"updated_at"`
}
type BookPlanPatch struct {
	ExpectedVersion    int64   `json:"expected_version"`
	Title              *string `json:"title"`
	Status             *string `json:"status"`
	Premise            *string `json:"premise"`
	PlanningJSON       *string `json:"planning"`
	TargetChapterCount *int    `json:"target_chapter_count"`
}
type BookRunEvent struct {
	EventID      string    `json:"event_id"`
	BookPlanID   string    `json:"book_plan_id"`
	RunID        string    `json:"run_id,omitempty"`
	EventType    string    `json:"event_type"`
	Status       string    `json:"status"`
	Sequence     int       `json:"sequence"`
	ItemCount    int       `json:"item_count"`
	WarningCount int       `json:"warning_count"`
	CreatedAt    time.Time `json:"created_at"`
}
type BookRunAdmission struct {
	Plan  BookPlan     `json:"plan"`
	Event BookRunEvent `json:"event"`
}
type AdmitBookRunInput struct {
	ExpectedVersion int64  `json:"expected_version"`
	RunID           string `json:"run_id"`
	Status          string `json:"status"`
	ItemCount       int    `json:"item_count"`
	WarningCount    int    `json:"warning_count"`
}

type WriterPreset struct {
	PresetID     string    `json:"writer_preset_id"`
	Scope        string    `json:"scope"`
	ProjectID    string    `json:"project_id,omitempty"`
	Name         string    `json:"name"`
	Description  string    `json:"description"`
	SettingsJSON string    `json:"settings"`
	Enabled      bool      `json:"enabled"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}
type ForbiddenEntry struct {
	EntryID             string    `json:"lexicon_entry_id"`
	ProjectID           string    `json:"project_id"`
	Term                string    `json:"term"`
	Category            string    `json:"category"`
	Severity            string    `json:"severity"`
	ReplacementGuidance string    `json:"replacement_guidance"`
	Enabled             bool      `json:"enabled"`
	CreatedAt           time.Time `json:"created_at"`
	UpdatedAt           time.Time `json:"updated_at"`
}

type Store interface {
	ListChapters(context.Context, Scope) ([]Chapter, error)
	CreateChapter(context.Context, CreateChapterInput) (Chapter, error)
	GetChapter(context.Context, Scope, string, bool) (Chapter, error)
	UpdateChapter(context.Context, Scope, string, ChapterPatch) (Chapter, error)
	DeleteChapter(context.Context, Scope, string, int64) error
	ReorderChapters(context.Context, Scope, []string) error
	ListChapterVersions(context.Context, Scope, string, bool) ([]Version, error)
	ListScenes(context.Context, Scope, string) ([]Scene, error)
	CreateScene(context.Context, CreateSceneInput) (Scene, error)
	GetScene(context.Context, Scope, string, bool) (Scene, error)
	UpdateScene(context.Context, Scope, string, ScenePatch) (Scene, error)
	DeleteScene(context.Context, Scope, string, int64) error
	ReorderScenes(context.Context, Scope, string, []string) error
	ListSceneVersions(context.Context, Scope, string, bool) ([]Version, error)
	ListOutlines(context.Context, Scope, string, string) ([]OutlineVersion, error)
	CreateOutline(context.Context, CreateOutlineInput) (OutlineVersion, error)
	RestoreOutline(context.Context, Scope, string) (OutlineVersion, error)
	ListBookPlans(context.Context, Scope) ([]BookPlan, error)
	GetBookPlan(context.Context, Scope, string) (BookPlan, error)
	CreateBookPlan(context.Context, Scope, BookPlan) (BookPlan, error)
	UpdateBookPlan(context.Context, Scope, string, BookPlanPatch) (BookPlan, error)
	DeleteBookPlan(context.Context, Scope, string, int64) error
	AdmitBookRun(context.Context, Scope, string, AdmitBookRunInput) (BookRunAdmission, error)
	AppendBookRunEvent(context.Context, Scope, BookRunEvent) (BookRunEvent, error)
	ListBookRunEvents(context.Context, Scope, string, int) ([]BookRunEvent, error)
	ListPresets(context.Context, Scope) ([]WriterPreset, error)
	GetPreset(context.Context, Scope, string) (WriterPreset, error)
	UpsertPreset(context.Context, Scope, WriterPreset) (WriterPreset, error)
	DeletePreset(context.Context, Scope, string) error
	ListLexicon(context.Context, Scope) ([]ForbiddenEntry, error)
	GetLexicon(context.Context, Scope, string) (ForbiddenEntry, error)
	UpsertLexicon(context.Context, Scope, ForbiddenEntry) (ForbiddenEntry, error)
	DeleteLexicon(context.Context, Scope, string) error
}

type Operation string

const (
	OperationRead               Operation = "writer_workspace_read"
	OperationPrivateRead        Operation = "writer_private_read"
	OperationWrite              Operation = "creative_write"
	OperationTenantPresetManage Operation = "tenant_writer_preset_manage"
)

type Actor struct{ UserID, TenantID, ProjectID, RequestID string }
type ActorResolver interface {
	ResolveActor(context.Context, *http.Request) (Actor, error)
}
type AuthorizeInput struct {
	Actor     Actor
	ProjectID string
	Operation Operation
}
type Authorizer interface {
	Authorize(context.Context, AuthorizeInput) error
}

type ResourceKind string

const (
	ResourceChapter      ResourceKind = "chapter"
	ResourceScene        ResourceKind = "scene"
	ResourceOutline      ResourceKind = "outline_version"
	ResourceBookPlan     ResourceKind = "book_plan"
	ResourceWriterPreset ResourceKind = "writer_preset"
	ResourceLexiconEntry ResourceKind = "forbidden_lexicon_entry"
)

type OwnerLookupInput struct {
	TenantID    string
	ActorUserID string
	Kind        ResourceKind
	ResourceID  string
}

type ResourceOwner struct {
	ProjectID    string
	TenantScoped bool
}

type OwnerProjectLookup interface {
	LookupResourceOwner(context.Context, OwnerLookupInput) (ResourceOwner, error)
}
