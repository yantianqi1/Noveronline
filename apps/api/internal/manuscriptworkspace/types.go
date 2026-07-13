package manuscriptworkspace

import (
	"context"
	"errors"
	"net/http"
)

const (
	CommandCompleteOutline   = "complete_outline"
	CommandAlignWords        = "align_words"
	CommandScanLexicon       = "scan_lexicon"
	CommandFillRelationships = "fill_relationships"
	CommandContinueChapter   = "continue_chapter"
)

type AppError struct {
	Code    string
	Message string
	cause   error
}

func (e *AppError) Error() string { return e.Message }
func (e *AppError) Unwrap() error { return e.cause }

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "MANUSCRIPT_WORKSPACE_FAILED"
}

type Scope struct {
	TenantID    string
	ProjectID   string
	ActorUserID string
	RequestID   string
}

type BlockMetadata struct {
	BlockID           string   `json:"block_id"`
	ProjectID         string   `json:"project_id"`
	ChapterID         string   `json:"chapter_id,omitempty"`
	SceneID           string   `json:"scene_id,omitempty"`
	SourceDraftID     string   `json:"source_draft_id,omitempty"`
	SourceWriterRunID string   `json:"source_writer_run_id,omitempty"`
	Status            string   `json:"status"`
	Tags              []string `json:"tags"`
	BlockOrder        int      `json:"block_order"`
	WordCount         int      `json:"word_count"`
	Version           int      `json:"version"`
	CreatedAt         string   `json:"created_at"`
	UpdatedAt         string   `json:"updated_at"`
}

type PrivateBlock struct {
	BlockMetadata
	ContentText string `json:"content_text"`
}

type BlockVersion struct {
	VersionID             string   `json:"version_id"`
	BlockID               string   `json:"block_id"`
	VersionNumber         int      `json:"version_number"`
	ChapterID             string   `json:"chapter_id,omitempty"`
	SceneID               string   `json:"scene_id,omitempty"`
	Status                string   `json:"status"`
	Tags                  []string `json:"tags"`
	BlockOrder            int      `json:"block_order"`
	WordCount             int      `json:"word_count"`
	SnapshotReason        string   `json:"snapshot_reason"`
	RestoredFromVersionID string   `json:"restored_from_version_id,omitempty"`
	CreatedBy             string   `json:"created_by"`
	CreatedAt             string   `json:"created_at"`
}

type PrivateBlockVersion struct {
	BlockVersion
	ContentText string `json:"content_text"`
}

type CreateBlockInput struct {
	Scope
	ChapterID   string
	SceneID     string
	ContentText string
	Tags        []string
}

type UpdateBlockInput struct {
	Scope
	BlockID         string
	ExpectedVersion int
	ContentText     *string
	Status          *string
	Tags            *[]string
	ChapterID       *string
	SceneID         *string
}

type DeleteBlockInput struct {
	Scope
	BlockID         string
	ExpectedVersion int
}

type TagBlockInput struct {
	Scope
	BlockID         string
	ExpectedVersion int
	Tags            []string
}

type ReorderItem struct {
	BlockID         string `json:"block_id"`
	ExpectedVersion int    `json:"expected_version"`
}

type ReorderBlocksInput struct {
	Scope
	Items []ReorderItem
}

type MoveBlockInput struct {
	Scope
	BlockID         string
	ExpectedVersion int
	ChapterID       string
	SceneID         string
	Items           []ReorderItem
}

type RestoreBlockInput struct {
	Scope
	BlockID         string
	VersionID       string
	ExpectedVersion int
}

type Store interface {
	ListBlocks(context.Context, Scope, bool) ([]BlockMetadata, error)
	GetPrivateBlock(context.Context, Scope, string) (PrivateBlock, error)
	CreateBlock(context.Context, CreateBlockInput) (PrivateBlock, error)
	UpdateBlock(context.Context, UpdateBlockInput) (PrivateBlock, error)
	TagBlock(context.Context, TagBlockInput) (BlockMetadata, error)
	DeleteBlock(context.Context, DeleteBlockInput) (BlockMetadata, error)
	ReorderBlocks(context.Context, ReorderBlocksInput) ([]BlockMetadata, error)
	MoveBlock(context.Context, MoveBlockInput) ([]BlockMetadata, error)
	ListVersions(context.Context, Scope, string) ([]BlockVersion, error)
	GetPrivateVersion(context.Context, Scope, string, string) (PrivateBlockVersion, error)
	RestoreVersion(context.Context, RestoreBlockInput) (PrivateBlock, error)
}

type TrustedContextResolver interface {
	ResolveManuscriptContext(context.Context, *http.Request, string) (Scope, error)
}

type PermissionAuthorizer interface {
	AuthorizeManuscript(context.Context, Scope, string) error
}

const (
	PermissionRead  = "manuscript_read"
	PermissionWrite = "manuscript_write"
)
