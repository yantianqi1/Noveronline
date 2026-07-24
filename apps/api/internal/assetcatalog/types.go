package assetcatalog

import (
	"context"
	"errors"
	"time"
)

type Permission string

const (
	PermissionReadPrivate Permission = "asset_catalog.read_private"
	PermissionMutate      Permission = "asset_catalog.mutate"
	PermissionCollections Permission = "asset_catalog.collections"
)

type RequestScope struct {
	ActorID     string
	TenantID    string
	ProjectID   string
	Role        string
	Permissions map[Permission]bool
}

func (s RequestScope) Can(permission Permission) bool { return s.Permissions[permission] }

type requestScopeKey struct{}

func WithRequestScope(ctx context.Context, scope RequestScope) context.Context {
	return context.WithValue(ctx, requestScopeKey{}, scope)
}

func RequestScopeFromContext(ctx context.Context) (RequestScope, bool) {
	scope, ok := ctx.Value(requestScopeKey{}).(RequestScope)
	return scope, ok
}

type Asset struct {
	AssetID        string          `json:"asset_id"`
	ProjectID      string          `json:"project_id"`
	AssetType      string          `json:"asset_type"`
	Category       *string         `json:"category"`
	Lifecycle      string          `json:"lifecycle"`
	Title          string          `json:"title"`
	Summary        *string         `json:"summary"`
	Payload        any             `json:"payload,omitempty"`
	Tags           []string        `json:"tags"`
	Source         Source          `json:"source"`
	Enabled        bool            `json:"enabled"`
	Pinned         bool            `json:"pinned"`
	AlwaysOn       bool            `json:"always_on"`
	// RevealAfterChapterOrder gates the asset out of writer recall until the
	// author writes at or past that chapter (doc 41 §4.5). NULL = always visible.
	RevealAfterChapterOrder *int           `json:"reveal_after_chapter_order"`
	CurrentVersion          int            `json:"current_version"`
	Collections             []CollectionRef `json:"collections"`
	CreatedAt               time.Time      `json:"created_at"`
	UpdatedAt               time.Time      `json:"updated_at"`
	Private                 *PrivateContent `json:"private,omitempty"`
	Capabilities            Capabilities   `json:"capabilities"`
}

type Capabilities struct {
	ReadPrivate       bool `json:"read_private"`
	Mutate            bool `json:"mutate"`
	ManageCollections bool `json:"manage_collections"`
}

type PrivateContent struct {
	ContentText *string `json:"content_text"`
}

type Source struct {
	Kind string `json:"kind"`
	Ref  string `json:"ref"`
}

type CollectionRef struct {
	CollectionID string `json:"collection_id"`
	Title        string `json:"title"`
	Lifecycle    string `json:"lifecycle"`
	Position     int    `json:"position"`
}

type Version struct {
	VersionID     string           `json:"version_id"`
	VersionNumber int              `json:"version_number"`
	Title         *string          `json:"title"`
	Summary       *string          `json:"summary"`
	Source        Source           `json:"source"`
	CreatedBy     *string          `json:"created_by"`
	CreatedAt     time.Time        `json:"created_at"`
	Snapshot      *VersionSnapshot `json:"snapshot,omitempty"`
}

type VersionSnapshot struct {
	AssetType   string   `json:"asset_type"`
	Category    *string  `json:"category"`
	Title       string   `json:"title"`
	Summary     *string  `json:"summary"`
	Payload     any      `json:"payload"`
	Tags        []string `json:"tags"`
	Source      Source   `json:"source"`
	Enabled     bool     `json:"enabled"`
	Pinned      bool     `json:"pinned"`
	AlwaysOn    bool     `json:"always_on"`
	ContentText *string  `json:"content_text,omitempty"`
}

type AssetPatch struct {
	ExpectedVersion int       `json:"expected_version"`
	Title           *string   `json:"title,omitempty"`
	SummaryValue    *string   `json:"summary,omitempty"`
	Category        *string   `json:"category,omitempty"`
	Payload         any       `json:"payload,omitempty"`
	Tags            *[]string `json:"tags,omitempty"`
	SourceKind      *string   `json:"source_kind,omitempty"`
	SourceRef       *string   `json:"source_ref,omitempty"`
	ContentText     *string   `json:"content_text,omitempty"`
	Enabled         *bool     `json:"enabled,omitempty"`
	Pinned          *bool     `json:"pinned,omitempty"`
	AlwaysOn        *bool     `json:"always_on,omitempty"`
	// Pointer-to-pointer would be needed to distinguish "clear" from "unset";
	// instead a negative value clears the gate (sets it back to NULL).
	RevealAfterChapterOrder *int `json:"reveal_after_chapter_order,omitempty"`
}

type RestoreInput struct {
	ExpectedVersion int `json:"expected_version"`
	VersionNumber   int `json:"version_number"`
}

type Collection struct {
	CollectionID string           `json:"collection_id"`
	ProjectID    string           `json:"project_id"`
	Title        string           `json:"title"`
	Summary      *string          `json:"summary"`
	Lifecycle    string           `json:"lifecycle"`
	Metadata     any              `json:"metadata"`
	Items        []CollectionItem `json:"items"`
	CreatedAt    time.Time        `json:"created_at"`
	UpdatedAt    time.Time        `json:"updated_at"`
}

type CollectionItem struct {
	AssetID   string    `json:"asset_id"`
	Title     string    `json:"title"`
	AssetType string    `json:"asset_type"`
	Position  int       `json:"position"`
	CreatedAt time.Time `json:"created_at"`
}

type CollectionInput struct {
	Title     string  `json:"title"`
	Summary   *string `json:"summary,omitempty"`
	Lifecycle string  `json:"lifecycle,omitempty"`
	Metadata  any     `json:"metadata,omitempty"`
}

type ReorderInput struct {
	AssetIDs []string `json:"asset_ids"`
}
type MembershipInput struct {
	Position *int `json:"position,omitempty"`
}

var (
	ErrNotFound = errors.New("asset catalog resource not found")
	ErrConflict = errors.New("asset catalog version conflict")
	ErrInvalid  = errors.New("asset catalog validation failed")
)

type Operation struct {
	Method     string
	Path       string
	Permission Permission
}

var Operations = []Operation{
	{Method: "GET", Path: "/assets/{assetId}", Permission: ""},
	{Method: "GET", Path: "/assets/{assetId}/versions", Permission: ""},
	{Method: "PATCH", Path: "/assets/{assetId}", Permission: PermissionMutate},
	{Method: "POST", Path: "/assets/{assetId}/restore", Permission: PermissionMutate},
	{Method: "GET", Path: "/collections", Permission: ""},
	{Method: "POST", Path: "/collections", Permission: PermissionCollections},
	{Method: "PATCH", Path: "/collections/{collectionId}", Permission: PermissionCollections},
	{Method: "DELETE", Path: "/collections/{collectionId}", Permission: PermissionCollections},
	{Method: "PUT", Path: "/collections/{collectionId}/items/{assetId}", Permission: PermissionCollections},
	{Method: "DELETE", Path: "/collections/{collectionId}/items/{assetId}", Permission: PermissionCollections},
	{Method: "PUT", Path: "/collections/{collectionId}/order", Permission: PermissionCollections},
}
