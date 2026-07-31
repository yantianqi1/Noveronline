package assets

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"math"
	"strconv"
	"strings"
)

const (
	// defaultAssetListPageSize is the asset list page size when the caller does
	// not request one (and the reader has no configured override).
	defaultAssetListPageSize = 100
	// maximumAssetListPageSize caps a single page to bound the payload_jsonb
	// row scan; callers page forward via offset/next_offset instead of asking
	// for unbounded pages.
	maximumAssetListPageSize = 500
)

type ListAssetsInput struct {
	TenantID  string
	ProjectID string
	Offset    int
	Limit     int
}

// AssetPage is one offset/limit page of the asset list. HasMore/NextOffset let
// callers walk forward until the full set is assembled; ReturnedCount is the
// number of items actually on this page (<= AppliedLimit).
type AssetPage struct {
	Items         []Record
	Offset        int
	AppliedLimit  int
	ReturnedCount int
	HasMore       bool
	NextOffset    int
}

type GetAssetInput struct {
	TenantID string
	AssetID  string
}

type ListFacetsInput struct {
	TenantID  string
	ProjectID string
}

type SearchAssetsInput struct {
	TenantID       string
	ProjectID      string
	Query          string
	Mode           string
	Filters        SearchFilters
	QueryEmbedding []float64
	EmbeddingModel string
}

type SearchFilters struct {
	AssetTypes []string `json:"asset_types,omitempty"`
	Categories []string `json:"categories,omitempty"`
	Lifecycles []string `json:"lifecycles,omitempty"`
	Sources    []string `json:"sources,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	Pinned     *bool    `json:"pinned,omitempty"`
}

type ListArchiveMemoriesInput struct {
	TenantID  string
	ProjectID string
	AssetID   string
}

type ListArchiveMemoryEventsInput struct {
	TenantID  string
	ProjectID string
	AssetID   string
}

type GetArchiveMemoryInput struct {
	TenantID string
	MemoryID string
}

type ArchiveMemoryReviewInput struct {
	TenantID  string
	ProjectID string
	MemoryID  string
	ActorID   string
	RequestID string
}

type AdoptAssetInput struct {
	TenantID        string
	AssetID         string
	ActorID         string
	RequestID       string
	TargetLifecycle string
}

type CreateAssetInput struct {
	TenantID     string
	ProjectID    string
	BodyTenantID string
	ActorID      string
	RequestID    string
	Scope        string
	AssetType    string
	Category     string
	Lifecycle    string
	Title        string
	Summary      string
	ContentText  string
	Payload      map[string]any
	Tags         []string
	SourceKind   string
	SourceRef    string
	Enabled      *bool
	Pinned       *bool
}

type PatchAssetInput struct {
	TenantID     string
	AssetID      string
	BodyTenantID string
	ActorID      string
	RequestID    string
	Scope        *string
	AssetType    *string
	Category     *string
	Lifecycle    *string
	Title        *string
	Summary      *string
	ContentText  *string
	Payload      *map[string]any
	Tags         *[]string
	SourceKind   *string
	SourceRef    *string
	Enabled      *bool
	Pinned       *bool
}

type DeleteAssetInput struct {
	TenantID  string
	AssetID   string
	ActorID   string
	RequestID string
}

type BulkActionInput struct {
	TenantID        string
	ProjectID       string
	BodyTenantID    string
	ActorID         string
	RequestID       string
	Action          string
	AssetIDs        []string
	TargetLifecycle string
	Category        string
	Enabled         *bool
	Pinned          *bool
	Payload         map[string]any
}

type DeleteResult struct {
	AssetID   string `json:"asset_id"`
	ProjectID string `json:"project_id"`
	Deleted   bool   `json:"deleted"`
}

type BulkActionResult struct {
	ProjectID    string `json:"project_id"`
	Action       string `json:"action"`
	Status       string `json:"status"`
	MatchedCount int    `json:"matched_count"`
	UpdatedCount int    `json:"updated_count"`
}

type Record struct {
	AssetID    string         `json:"asset_id"`
	ProjectID  string         `json:"project_id"`
	Scope      string         `json:"scope"`
	AssetType  string         `json:"asset_type"`
	Category   string         `json:"category"`
	Lifecycle  string         `json:"lifecycle"`
	Title      string         `json:"title"`
	Summary    string         `json:"summary"`
	SourceKind string         `json:"source_kind"`
	SourceRef  string         `json:"source_ref"`
	Enabled    bool           `json:"enabled"`
	Pinned     bool           `json:"pinned"`
	Tags       []string       `json:"tags"`
	Payload    map[string]any `json:"payload"`
	CreatedAt  string         `json:"created_at"`
	UpdatedAt  string         `json:"updated_at"`
}

type SearchRecord struct {
	SearchDocumentID string          `json:"search_document_id"`
	Source           string          `json:"source"`
	SourceRef        string          `json:"source_ref"`
	ProjectID        string          `json:"project_id"`
	EntityType       string          `json:"entity_type"`
	Title            string          `json:"title"`
	Tags             []string        `json:"tags"`
	Payload          map[string]any  `json:"payload"`
	Version          VersionSummary  `json:"version"`
	Collections      []CollectionRef `json:"collections"`
	Ranking          RankingMetadata `json:"ranking"`
	CreatedAt        string          `json:"created_at"`
	UpdatedAt        string          `json:"updated_at"`
}

type RankingMetadata struct {
	Mode                string  `json:"mode"`
	KeywordScore        float64 `json:"keyword_score"`
	VectorScore         float64 `json:"vector_score"`
	KeywordWeight       float64 `json:"keyword_weight"`
	VectorWeight        float64 `json:"vector_weight"`
	KeywordContribution float64 `json:"keyword_contribution"`
	VectorContribution  float64 `json:"vector_contribution"`
	RecencyBoost        float64 `json:"recency_boost"`
	LifecycleBoost      float64 `json:"lifecycle_boost"`
	PinnedBoost         float64 `json:"pinned_boost"`
	FinalScore          float64 `json:"final_score"`
	Rank                int     `json:"rank"`
	EmbeddingModel      string  `json:"embedding_model,omitempty"`
	Explanation         string  `json:"explanation"`
}

type VersionSummary struct {
	Count           int    `json:"count"`
	LatestVersion   int    `json:"latest_version"`
	LatestVersionID string `json:"latest_version_id"`
}

type CollectionRef struct {
	CollectionID string `json:"collection_id"`
	Title        string `json:"title"`
	Lifecycle    string `json:"lifecycle"`
}

type ArchiveMemoryRecord struct {
	MemoryID   string         `json:"memory_id"`
	AssetID    string         `json:"asset_id"`
	ProjectID  string         `json:"project_id"`
	MemoryType string         `json:"memory_type"`
	Status     string         `json:"status"`
	Summary    string         `json:"summary"`
	Payload    map[string]any `json:"payload"`
	SourceKind string         `json:"source_kind"`
	SourceRef  string         `json:"source_ref"`
	Enabled    bool           `json:"enabled"`
	CreatedAt  string         `json:"created_at"`
	UpdatedAt  string         `json:"updated_at"`
}

type ArchiveMemoryEventRecord struct {
	EventID   string         `json:"event_id"`
	MemoryID  string         `json:"memory_id"`
	AssetID   string         `json:"asset_id"`
	ProjectID string         `json:"project_id"`
	EventType string         `json:"event_type"`
	Status    string         `json:"status"`
	Payload   map[string]any `json:"payload"`
	ActorID   string         `json:"actor_id"`
	CreatedAt string         `json:"created_at"`
}

type FacetBucket struct {
	Value string `json:"value"`
	Count int    `json:"count"`
}

type Facets struct {
	AssetTypes []FacetBucket `json:"asset_types"`
	Categories []FacetBucket `json:"categories"`
	Lifecycles []FacetBucket `json:"lifecycles"`
	Sources    []FacetBucket `json:"sources"`
	Tags       []FacetBucket `json:"tags"`
}

type Reader interface {
	ListAssets(context.Context, ListAssetsInput) (AssetPage, error)
	GetAsset(context.Context, GetAssetInput) (Record, error)
	ListFacets(context.Context, ListFacetsInput) (Facets, error)
	SearchAssets(context.Context, SearchAssetsInput) ([]SearchRecord, error)
}

type ArchiveMemoryReader interface {
	ListMemories(context.Context, ListArchiveMemoriesInput) ([]ArchiveMemoryRecord, error)
	ListMemoryEvents(context.Context, ListArchiveMemoryEventsInput) ([]ArchiveMemoryEventRecord, error)
	GetMemory(context.Context, GetArchiveMemoryInput) (ArchiveMemoryRecord, error)
}

type ArchiveMemoryReviewStore interface {
	AdoptMemory(context.Context, ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error)
	RejectMemory(context.Context, ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error)
}

type AdoptionStore interface {
	AdoptAsset(context.Context, AdoptAssetInput) (Record, error)
}

type MutationStore interface {
	CreateAsset(context.Context, CreateAssetInput) (Record, error)
	PatchAsset(context.Context, PatchAssetInput) (Record, error)
	DeleteAsset(context.Context, DeleteAssetInput) (DeleteResult, error)
}

type BulkActionStore interface {
	ApplyBulkAction(context.Context, BulkActionInput) (BulkActionResult, error)
}

type AppError struct {
	Code    string
	Message string
}

func (e *AppError) Error() string {
	return e.Message
}

func ErrorCode(err error) string {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.Code
	}
	return "ASSET_ERROR"
}

type DisabledReader struct{}

func NewDisabledReader() DisabledReader {
	return DisabledReader{}
}

func (DisabledReader) ListAssets(context.Context, ListAssetsInput) (AssetPage, error) {
	return AssetPage{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
}

func (DisabledReader) GetAsset(context.Context, GetAssetInput) (Record, error) {
	return Record{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
}

func (DisabledReader) ListFacets(context.Context, ListFacetsInput) (Facets, error) {
	return Facets{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
}

func (DisabledReader) SearchAssets(context.Context, SearchAssetsInput) ([]SearchRecord, error) {
	return nil, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
}

type DisabledAdoptionStore struct{}

func NewDisabledAdoptionStore() DisabledAdoptionStore {
	return DisabledAdoptionStore{}
}

func (DisabledAdoptionStore) AdoptAsset(context.Context, AdoptAssetInput) (Record, error) {
	return Record{}, &AppError{
		Code:    "ASSET_ADOPTION_BACKEND_UNCONFIGURED",
		Message: "asset adoption backend is not configured",
	}
}

type DisabledMutationStore struct{}

func NewDisabledMutationStore() DisabledMutationStore {
	return DisabledMutationStore{}
}

func (DisabledMutationStore) CreateAsset(context.Context, CreateAssetInput) (Record, error) {
	return Record{}, &AppError{
		Code:    "ASSET_MUTATION_BACKEND_UNCONFIGURED",
		Message: "asset mutation backend is not configured",
	}
}

func (DisabledMutationStore) PatchAsset(context.Context, PatchAssetInput) (Record, error) {
	return Record{}, &AppError{
		Code:    "ASSET_MUTATION_BACKEND_UNCONFIGURED",
		Message: "asset mutation backend is not configured",
	}
}

func (DisabledMutationStore) DeleteAsset(context.Context, DeleteAssetInput) (DeleteResult, error) {
	return DeleteResult{}, &AppError{
		Code:    "ASSET_MUTATION_BACKEND_UNCONFIGURED",
		Message: "asset mutation backend is not configured",
	}
}

type DisabledBulkActionStore struct{}

func NewDisabledBulkActionStore() DisabledBulkActionStore {
	return DisabledBulkActionStore{}
}

func (DisabledBulkActionStore) ApplyBulkAction(context.Context, BulkActionInput) (BulkActionResult, error) {
	return BulkActionResult{}, &AppError{
		Code:    "ASSET_BULK_ACTION_BACKEND_UNCONFIGURED",
		Message: "asset bulk action backend is not configured",
	}
}

type DisabledArchiveMemoryReader struct{}

func NewDisabledArchiveMemoryReader() DisabledArchiveMemoryReader {
	return DisabledArchiveMemoryReader{}
}

func (DisabledArchiveMemoryReader) ListMemories(context.Context, ListArchiveMemoriesInput) ([]ArchiveMemoryRecord, error) {
	return nil, &AppError{
		Code:    "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED",
		Message: "archive memory backend is not configured",
	}
}

func (DisabledArchiveMemoryReader) ListMemoryEvents(context.Context, ListArchiveMemoryEventsInput) ([]ArchiveMemoryEventRecord, error) {
	return nil, &AppError{
		Code:    "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED",
		Message: "archive memory backend is not configured",
	}
}

func (DisabledArchiveMemoryReader) GetMemory(context.Context, GetArchiveMemoryInput) (ArchiveMemoryRecord, error) {
	return ArchiveMemoryRecord{}, &AppError{
		Code:    "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED",
		Message: "archive memory backend is not configured",
	}
}

type DisabledArchiveMemoryReviewStore struct{}

func NewDisabledArchiveMemoryReviewStore() DisabledArchiveMemoryReviewStore {
	return DisabledArchiveMemoryReviewStore{}
}

func (DisabledArchiveMemoryReviewStore) AdoptMemory(context.Context, ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error) {
	return ArchiveMemoryRecord{}, &AppError{
		Code:    "ARCHIVE_MEMORY_REVIEW_BACKEND_UNCONFIGURED",
		Message: "archive memory review backend is not configured",
	}
}

func (DisabledArchiveMemoryReviewStore) RejectMemory(context.Context, ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error) {
	return ArchiveMemoryRecord{}, &AppError{
		Code:    "ARCHIVE_MEMORY_REVIEW_BACKEND_UNCONFIGURED",
		Message: "archive memory review backend is not configured",
	}
}

type SQLRows interface {
	Next() bool
	Scan(...any) error
	Close() error
	Err() error
}

type SQLQueryer interface {
	QueryContext(context.Context, string, ...any) (SQLRows, error)
}

type SQLTenantQueryer interface {
	QueryTenantContext(context.Context, string, string, ...any) (SQLRows, error)
}

type SQLDBQueryer struct {
	db *sql.DB
}

func NewSQLDBQueryer(db *sql.DB) *SQLDBQueryer {
	return &SQLDBQueryer{db: db}
}

func (q *SQLDBQueryer) QueryContext(ctx context.Context, query string, args ...any) (SQLRows, error) {
	return q.db.QueryContext(ctx, query, args...)
}

func (q *SQLDBQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	tx, err := q.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULL::uuid, false)", strings.TrimSpace(tenantID)); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, query, args...)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return &tenantScopedRows{rows: rows, tx: tx}, nil
}

type tenantScopedRows struct {
	rows SQLRows
	tx   *sql.Tx
}

func (r *tenantScopedRows) Next() bool {
	return r.rows.Next()
}

func (r *tenantScopedRows) Scan(dest ...any) error {
	return r.rows.Scan(dest...)
}

func (r *tenantScopedRows) Close() error {
	closeErr := r.rows.Close()
	rowsErr := r.rows.Err()
	if closeErr != nil || rowsErr != nil {
		_ = r.tx.Rollback()
		if closeErr != nil {
			return closeErr
		}
		return rowsErr
	}
	return r.tx.Commit()
}

func (r *tenantScopedRows) Err() error {
	return r.rows.Err()
}

type SQLReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLReader struct {
	queryer SQLQueryer
	limit   int
}

type SQLAdoptionStoreConfig struct {
	Queryer SQLQueryer
}

type SQLAdoptionStore struct {
	queryer SQLQueryer
}

type SQLMutationStoreConfig struct {
	Queryer SQLQueryer
}

type SQLMutationStore struct {
	queryer SQLQueryer
}

type SQLBulkActionStoreConfig struct {
	Queryer SQLQueryer
}

type SQLBulkActionStore struct {
	queryer SQLQueryer
}

type SQLArchiveMemoryReaderConfig struct {
	Queryer SQLQueryer
	Limit   int
}

type SQLArchiveMemoryReader struct {
	queryer SQLQueryer
	limit   int
}

type SQLArchiveMemoryReviewStoreConfig struct {
	Queryer SQLQueryer
}

type SQLArchiveMemoryReviewStore struct {
	queryer SQLQueryer
}

func NewSQLReader(config SQLReaderConfig) *SQLReader {
	limit := config.Limit
	if limit <= 0 {
		limit = defaultAssetListPageSize
	}
	return &SQLReader{queryer: config.Queryer, limit: limit}
}

// normalizeAssetListLimit resolves the page size for a list request: an
// explicit positive input wins, otherwise the reader's configured default; the
// result is capped to bound the heavy payload_jsonb row scan per request.
func normalizeAssetListLimit(input int, configuredDefault int) int {
	limit := input
	if limit <= 0 {
		limit = configuredDefault
	}
	if limit <= 0 {
		limit = defaultAssetListPageSize
	}
	if limit > maximumAssetListPageSize {
		limit = maximumAssetListPageSize
	}
	return limit
}

func normalizeAssetListOffset(offset int) int {
	if offset < 0 {
		return 0
	}
	return offset
}

func NewSQLAdoptionStore(config SQLAdoptionStoreConfig) *SQLAdoptionStore {
	return &SQLAdoptionStore{queryer: config.Queryer}
}

func NewSQLMutationStore(config SQLMutationStoreConfig) *SQLMutationStore {
	return &SQLMutationStore{queryer: config.Queryer}
}

func NewSQLBulkActionStore(config SQLBulkActionStoreConfig) *SQLBulkActionStore {
	return &SQLBulkActionStore{queryer: config.Queryer}
}

func NewSQLArchiveMemoryReader(config SQLArchiveMemoryReaderConfig) *SQLArchiveMemoryReader {
	limit := config.Limit
	if limit <= 0 {
		limit = 50
	}
	return &SQLArchiveMemoryReader{queryer: config.Queryer, limit: limit}
}

func NewSQLArchiveMemoryReviewStore(config SQLArchiveMemoryReviewStoreConfig) *SQLArchiveMemoryReviewStore {
	return &SQLArchiveMemoryReviewStore{queryer: config.Queryer}
}

func queryWithTenantContext(ctx context.Context, queryer SQLQueryer, tenantID string, query string, args ...any) (SQLRows, error) {
	if tenantQueryer, ok := queryer.(SQLTenantQueryer); ok {
		return tenantQueryer.QueryTenantContext(ctx, strings.TrimSpace(tenantID), query, args...)
	}
	return queryer.QueryContext(ctx, query, args...)
}

func (r *SQLReader) ListAssets(ctx context.Context, input ListAssetsInput) (AssetPage, error) {
	if err := validateProjectInput(input.TenantID, input.ProjectID); err != nil {
		return AssetPage{}, err
	}
	if r.queryer == nil {
		return AssetPage{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
	}
	limit := normalizeAssetListLimit(input.Limit, r.limit)
	offset := normalizeAssetListOffset(input.Offset)
	// Fetch one extra row past the page to detect has_more without a COUNT query
	// (same idiom as the story graph reader). The extra row is trimmed below.
	query := `SELECT
  asset_id::text,
  project_id::text,
  scope,
  asset_type,
  COALESCE(category, ''),
  lifecycle,
  title,
  COALESCE(summary, ''),
  source_kind,
  source_ref,
  enabled,
  pinned,
  tags_jsonb::text,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM assets
WHERE tenant_id::text = $1
  AND project_id::text = $2
ORDER BY pinned DESC, updated_at DESC, asset_id::text ASC
LIMIT $3 OFFSET $4`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), limit+1, offset)
	if err != nil {
		return AssetPage{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	records := []Record{}
	for rows.Next() {
		record, err := scanAssetRecord(rows)
		if err != nil {
			return AssetPage{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return AssetPage{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	hasMore := len(records) > limit
	if hasMore {
		records = records[:limit]
	}
	page := AssetPage{
		Items:         records,
		Offset:        offset,
		AppliedLimit:  limit,
		ReturnedCount: len(records),
		HasMore:       hasMore,
	}
	if hasMore {
		page.NextOffset = offset + len(records)
	}
	return page, nil
}

func (r *SQLReader) GetAsset(ctx context.Context, input GetAssetInput) (Record, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.AssetID) == "" {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and asset_id are required"}
	}
	if r.queryer == nil {
		return Record{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
	}
	query := `SELECT
  asset_id::text,
  project_id::text,
  scope,
  asset_type,
  COALESCE(category, ''),
  lifecycle,
  title,
  COALESCE(summary, ''),
  source_kind,
  source_ref,
  enabled,
  pinned,
  tags_jsonb::text,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM assets
WHERE tenant_id::text = $1
  AND asset_id::text = $2
LIMIT 1`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.AssetID))
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return Record{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
		}
		return Record{}, &AppError{Code: "NOT_FOUND", Message: "asset was not found"}
	}
	record, err := scanAssetRecord(rows)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return Record{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

func (r *SQLReader) ListFacets(ctx context.Context, input ListFacetsInput) (Facets, error) {
	if err := validateProjectInput(input.TenantID, input.ProjectID); err != nil {
		return Facets{}, err
	}
	if r.queryer == nil {
		return Facets{}, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
	}
	query := `SELECT facet, value, item_count
FROM (
  SELECT 'asset_type' AS facet, asset_type AS value, COUNT(*)::int AS item_count
  FROM assets
  WHERE tenant_id::text = $1 AND project_id::text = $2
  GROUP BY asset_type
  UNION ALL
  SELECT 'category' AS facet, COALESCE(category, '') AS value, COUNT(*)::int AS item_count
  FROM assets
  WHERE tenant_id::text = $1 AND project_id::text = $2
  GROUP BY COALESCE(category, '')
  UNION ALL
  SELECT 'lifecycle' AS facet, lifecycle AS value, COUNT(*)::int AS item_count
  FROM assets
  WHERE tenant_id::text = $1 AND project_id::text = $2
  GROUP BY lifecycle
  UNION ALL
  SELECT 'source_kind' AS facet, source_kind AS value, COUNT(*)::int AS item_count
  FROM assets
  WHERE tenant_id::text = $1 AND project_id::text = $2
  GROUP BY source_kind
  UNION ALL
  SELECT 'tag' AS facet, tag AS value, COUNT(*)::int AS item_count
  FROM assets
  CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE WHEN jsonb_typeof(tags_jsonb) = 'array' THEN tags_jsonb ELSE '[]'::jsonb END
  ) AS tag
  WHERE tenant_id::text = $1 AND project_id::text = $2
  GROUP BY tag
) asset_facets
WHERE value <> ''
ORDER BY facet ASC, item_count DESC, value ASC`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID))
	if err != nil {
		return Facets{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	var facets Facets
	for rows.Next() {
		var facet string
		var value string
		var count int
		if err := rows.Scan(&facet, &value, &count); err != nil {
			return Facets{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
		}
		bucket := FacetBucket{Value: value, Count: count}
		switch facet {
		case "asset_type":
			facets.AssetTypes = append(facets.AssetTypes, bucket)
		case "category":
			facets.Categories = append(facets.Categories, bucket)
		case "lifecycle":
			facets.Lifecycles = append(facets.Lifecycles, bucket)
		case "source_kind":
			facets.Sources = append(facets.Sources, bucket)
		case "tag":
			facets.Tags = append(facets.Tags, bucket)
		}
	}
	if err := rows.Err(); err != nil {
		return Facets{}, &AppError{Code: "ASSET_QUERY_FAILED", Message: err.Error()}
	}
	return facets, nil
}

func (r *SQLReader) SearchAssets(ctx context.Context, input SearchAssetsInput) ([]SearchRecord, error) {
	if err := validateProjectInput(input.TenantID, input.ProjectID); err != nil {
		return nil, err
	}
	query := strings.TrimSpace(input.Query)
	if query == "" {
		return nil, &AppError{Code: "VALIDATION_FAILED", Message: "query is required"}
	}
	mode, embeddingLiteral, embeddingModel, err := validateSearchMode(input)
	if err != nil {
		return nil, err
	}
	filters := normalizeSearchFilters(input.Filters)
	if r.queryer == nil {
		return nil, &AppError{Code: "ASSET_BACKEND_UNCONFIGURED", Message: "asset backend is not configured"}
	}
	sql := `WITH search_input AS (
  SELECT
    $1::text AS tenant_id,
    $2::text AS project_id,
    $3::text AS query_text,
    $4::text[] AS keyword_patterns,
    $5::text AS search_mode,
    CASE WHEN $5::text = 'keyword' THEN NULL::vector ELSE $6::vector END AS query_embedding,
    $7::text AS embedding_model,
    $8::text[] AS asset_types,
    $9::text[] AS categories,
    $10::text[] AS lifecycles,
    $11::text[] AS sources,
    $12::text[] AS tags,
    $13::boolean AS pinned
),
candidate_scores AS (
  SELECT
    search_doc.search_document_id,
    search_doc.source,
    search_doc.source_ref,
    search_doc.project_id,
    search_doc.entity_type,
    search_doc.title,
    search_doc.tags_jsonb,
    search_doc.payload_jsonb,
    search_doc.created_at,
    search_doc.updated_at,
    asset.asset_id,
    asset.lifecycle,
    asset.pinned,
    input.search_mode,
    COALESCE(embedding.embedding_model, '') AS embedding_model,
    GREATEST(
      ts_rank_cd(search_doc.search_vector, websearch_to_tsquery('simple'::regconfig, input.query_text)),
      CASE
        WHEN cardinality(input.keyword_patterns) = 0 THEN 0.0
        ELSE 0.5 * (
          SELECT COUNT(*)::float8
            FROM unnest(input.keyword_patterns) AS term(pattern)
           WHERE search_doc.title ILIKE term.pattern
              OR COALESCE(search_doc.body, '') ILIKE term.pattern
              OR COALESCE(asset.content_text, '') ILIKE term.pattern
        ) / cardinality(input.keyword_patterns)
      END
    )::float8 AS keyword_score,
    CASE
      WHEN input.search_mode = 'keyword' OR embedding.embedding_id IS NULL THEN 0.0
      ELSE GREATEST(0.0, LEAST(1.0, 1.0 - (embedding.embedding <=> input.query_embedding)))
    END::float8 AS vector_score
  FROM global_search_index search_doc
  JOIN assets asset
    ON search_doc.source = 'asset'
    AND asset.tenant_id = search_doc.tenant_id
    AND asset.project_id = search_doc.project_id
    AND asset.asset_id::text = search_doc.source_ref
    AND asset.enabled = true
  CROSS JOIN search_input input
  LEFT JOIN asset_embeddings embedding
    ON embedding.tenant_id = asset.tenant_id
    AND embedding.project_id = asset.project_id
    AND embedding.asset_id = asset.asset_id
    AND embedding.embedding_model = input.embedding_model
    AND embedding.dimensions = vector_dims(input.query_embedding)
  WHERE search_doc.tenant_id::text = input.tenant_id
    AND search_doc.project_id::text = input.project_id
    AND (cardinality(input.asset_types) = 0 OR asset.asset_type = ANY(input.asset_types))
    AND (cardinality(input.categories) = 0 OR asset.category = ANY(input.categories))
    AND (cardinality(input.lifecycles) = 0 OR asset.lifecycle = ANY(input.lifecycles))
    AND (cardinality(input.sources) = 0 OR asset.source_kind = ANY(input.sources))
    AND (cardinality(input.tags) = 0 OR asset.tags_jsonb ?| input.tags)
    AND (input.pinned IS NULL OR asset.pinned = input.pinned)
    AND (
      (
        input.search_mode IN ('keyword', 'hybrid')
        AND (
          search_doc.search_vector @@ websearch_to_tsquery('simple'::regconfig, input.query_text)
          OR EXISTS (
            SELECT 1
              FROM unnest(input.keyword_patterns) AS term(pattern)
             WHERE search_doc.title ILIKE term.pattern
                OR COALESCE(search_doc.body, '') ILIKE term.pattern
                OR COALESCE(asset.content_text, '') ILIKE term.pattern
          )
        )
      )
      OR (
        input.search_mode IN ('vector', 'hybrid')
        AND embedding.embedding_id IS NOT NULL
      )
    )
),
boosted_scores AS (
  SELECT
    candidate.*,
    (0.05 / (1.0 + GREATEST(EXTRACT(EPOCH FROM (now() - candidate.updated_at)) / 86400.0, 0.0) / 365.0))::float8 AS recency_boost,
    CASE candidate.lifecycle
      WHEN 'canon' THEN 0.08
      WHEN 'manuscript' THEN 0.08
      WHEN 'seed' THEN 0.04
      WHEN 'material' THEN 0.04
      WHEN 'candidate' THEN 0.01
      ELSE 0.0
    END::float8 AS lifecycle_boost,
    CASE WHEN candidate.pinned THEN 0.05 ELSE 0.0 END::float8 AS pinned_boost
  FROM candidate_scores candidate
),
final_scores AS (
  SELECT
    boosted.*,
    CASE boosted.search_mode
      WHEN 'keyword' THEN boosted.keyword_score
      WHEN 'vector' THEN boosted.vector_score
      ELSE (0.45 * boosted.keyword_score) + (0.55 * boosted.vector_score)
    END + boosted.recency_boost + boosted.lifecycle_boost + boosted.pinned_boost AS final_score
  FROM boosted_scores boosted
),
ranked AS (
  SELECT
    final_scores.*,
    row_number() OVER (
      ORDER BY final_score DESC, keyword_score DESC, vector_score DESC, updated_at DESC, search_document_id::text ASC
    )::int AS result_rank
  FROM final_scores
)
SELECT
  ranked.search_document_id::text,
  ranked.source,
  ranked.source_ref,
  ranked.project_id::text,
  COALESCE(ranked.entity_type, ''),
  ranked.title,
  ranked.tags_jsonb::text,
  ranked.payload_jsonb::text,
  COALESCE(version_meta.version_count, 0)::int,
  COALESCE(version_meta.latest_version, 0)::int,
  COALESCE(version_meta.latest_version_id, ''),
  COALESCE(collection_meta.collections_json, '[]'),
  ranked.created_at::text,
  ranked.updated_at::text,
  ranked.search_mode,
  ranked.keyword_score,
  ranked.vector_score,
  ranked.recency_boost,
  ranked.lifecycle_boost,
  ranked.pinned_boost,
  ranked.final_score::float8,
  ranked.result_rank,
  ranked.embedding_model
FROM ranked
LEFT JOIN LATERAL (
  SELECT
    COUNT(*)::int AS version_count,
    COALESCE(MAX(version_number), 0)::int AS latest_version,
    COALESCE((ARRAY_AGG(asset_version_id::text ORDER BY version_number DESC, created_at DESC))[1], '') AS latest_version_id
  FROM asset_versions
  WHERE tenant_id::text = $1
    AND project_id = ranked.project_id
    AND asset_id = ranked.asset_id
) version_meta ON TRUE
LEFT JOIN LATERAL (
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'collection_id', collection.collection_id::text,
        'title', collection.title,
        'lifecycle', collection.lifecycle
      )
      ORDER BY collection.title ASC, collection.collection_id::text ASC
    ) FILTER (WHERE collection.collection_id IS NOT NULL),
    '[]'::jsonb
  )::text AS collections_json
  FROM asset_collection_items item
  JOIN asset_collections collection
    ON collection.tenant_id = item.tenant_id
    AND collection.project_id = item.project_id
    AND collection.collection_id = item.collection_id
  WHERE item.tenant_id::text = $1
    AND item.project_id = ranked.project_id
    AND item.asset_id = ranked.asset_id
) collection_meta ON TRUE
ORDER BY ranked.result_rank ASC
LIMIT $14`
	rows, err := queryWithTenantContext(
		ctx,
		r.queryer,
		input.TenantID,
		sql,
		strings.TrimSpace(input.TenantID),
		strings.TrimSpace(input.ProjectID),
		query,
		searchLikePatterns(TokenizeSearchQuery(query)),
		mode,
		embeddingLiteral,
		embeddingModel,
		filters.AssetTypes,
		filters.Categories,
		filters.Lifecycles,
		filters.Sources,
		filters.Tags,
		filters.Pinned,
		r.limit,
	)
	if err != nil {
		return nil, &AppError{Code: "ASSET_SEARCH_FAILED", Message: "asset search failed"}
	}
	defer rows.Close()

	records := []SearchRecord{}
	for rows.Next() {
		var record SearchRecord
		var tagsJSON string
		var payloadJSON string
		var collectionsJSON string
		if err := rows.Scan(
			&record.SearchDocumentID,
			&record.Source,
			&record.SourceRef,
			&record.ProjectID,
			&record.EntityType,
			&record.Title,
			&tagsJSON,
			&payloadJSON,
			&record.Version.Count,
			&record.Version.LatestVersion,
			&record.Version.LatestVersionID,
			&collectionsJSON,
			&record.CreatedAt,
			&record.UpdatedAt,
			&record.Ranking.Mode,
			&record.Ranking.KeywordScore,
			&record.Ranking.VectorScore,
			&record.Ranking.RecencyBoost,
			&record.Ranking.LifecycleBoost,
			&record.Ranking.PinnedBoost,
			&record.Ranking.FinalScore,
			&record.Ranking.Rank,
			&record.Ranking.EmbeddingModel,
		); err != nil {
			return nil, &AppError{Code: "ASSET_SEARCH_FAILED", Message: "asset search failed"}
		}
		record.Tags = sanitizeTags(decodeTags(tagsJSON))
		record.Payload = sanitizeObject(decodeObject(payloadJSON))
		record.Collections = decodeCollectionRefs(collectionsJSON)
		populateRankingExplanation(&record.Ranking)
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "ASSET_SEARCH_FAILED", Message: "asset search failed"}
	}
	return records, nil
}

func normalizeSearchFilters(filters SearchFilters) SearchFilters {
	return SearchFilters{
		AssetTypes: normalizeSearchFilterValues(filters.AssetTypes),
		Categories: normalizeSearchFilterValues(filters.Categories),
		Lifecycles: normalizeSearchFilterValues(filters.Lifecycles),
		Sources:    normalizeSearchFilterValues(filters.Sources),
		Tags:       normalizeSearchFilterValues(filters.Tags),
		Pinned:     filters.Pinned,
	}
}

func normalizeSearchFilterValues(values []string) []string {
	normalized := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	return normalized
}

func populateRankingExplanation(ranking *RankingMetadata) {
	switch ranking.Mode {
	case "keyword":
		ranking.KeywordWeight = 1
		ranking.Explanation = "keyword relevance plus recency, lifecycle, and pinned boosts"
	case "vector":
		ranking.VectorWeight = 1
		ranking.Explanation = "vector similarity plus recency, lifecycle, and pinned boosts"
	case "hybrid":
		ranking.KeywordWeight = 0.45
		ranking.VectorWeight = 0.55
		ranking.Explanation = "45% keyword relevance and 55% vector similarity plus recency, lifecycle, and pinned boosts"
	}
	ranking.KeywordContribution = ranking.KeywordScore * ranking.KeywordWeight
	ranking.VectorContribution = ranking.VectorScore * ranking.VectorWeight
}

func validateSearchMode(input SearchAssetsInput) (string, any, string, error) {
	mode := strings.ToLower(strings.TrimSpace(input.Mode))
	if mode == "" {
		mode = "keyword"
	}
	if mode != "keyword" && mode != "vector" && mode != "hybrid" {
		return "", nil, "", &AppError{Code: "VALIDATION_FAILED", Message: "search mode must be keyword, vector, or hybrid"}
	}
	if mode == "keyword" {
		return mode, nil, "", nil
	}
	embeddingModel := strings.TrimSpace(input.EmbeddingModel)
	if embeddingModel == "" || len(input.QueryEmbedding) == 0 {
		return "", nil, "", &AppError{Code: "ASSET_QUERY_EMBEDDING_REQUIRED", Message: "query embedding and model are required for vector search"}
	}
	nonZero := false
	parts := make([]string, len(input.QueryEmbedding))
	for index, component := range input.QueryEmbedding {
		if math.IsNaN(component) || math.IsInf(component, 0) {
			return "", nil, "", &AppError{Code: "VALIDATION_FAILED", Message: "query embedding components must be finite"}
		}
		if component != 0 {
			nonZero = true
		}
		parts[index] = strconv.FormatFloat(component, 'g', -1, 64)
	}
	if !nonZero {
		return "", nil, "", &AppError{Code: "VALIDATION_FAILED", Message: "query embedding must not be a zero vector"}
	}
	return mode, "[" + strings.Join(parts, ",") + "]", embeddingModel, nil
}

func (r *SQLArchiveMemoryReader) ListMemories(ctx context.Context, input ListArchiveMemoriesInput) ([]ArchiveMemoryRecord, error) {
	if err := validateArchiveMemoryInput(input.TenantID, input.ProjectID, input.AssetID); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED", Message: "archive memory backend is not configured"}
	}
	query := `SELECT
  memory.memory_id::text,
  memory.asset_id::text,
  asset.project_id::text,
  memory.memory_type,
  memory.status,
  COALESCE(memory.summary, ''),
  memory.payload_jsonb::text,
  memory.source_kind,
  memory.source_ref,
  memory.enabled,
  memory.created_at::text,
  memory.updated_at::text
FROM archive_memories memory
JOIN assets asset
  ON asset.tenant_id = memory.tenant_id
 AND asset.asset_id = memory.asset_id
WHERE memory.tenant_id::text = $1
  AND asset.project_id::text = $2
  AND memory.asset_id::text = $3
ORDER BY memory.updated_at DESC, memory.memory_id::text ASC
LIMIT $4`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), strings.TrimSpace(input.AssetID), r.limit)
	if err != nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	records := []ArchiveMemoryRecord{}
	for rows.Next() {
		record, err := scanArchiveMemoryRecord(rows)
		if err != nil {
			return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (r *SQLArchiveMemoryReader) ListMemoryEvents(ctx context.Context, input ListArchiveMemoryEventsInput) ([]ArchiveMemoryEventRecord, error) {
	if err := validateArchiveMemoryInput(input.TenantID, input.ProjectID, input.AssetID); err != nil {
		return nil, err
	}
	if r.queryer == nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED", Message: "archive memory backend is not configured"}
	}
	limit := r.limit
	if limit < 100 {
		limit = 100
	}
	query := `SELECT
  event.event_id::text,
  event.memory_id::text,
  memory.asset_id::text,
  asset.project_id::text,
  event.event_type,
  event.status,
  event.payload_jsonb::text,
  COALESCE(event.actor_user_id::text, ''),
  event.created_at::text
FROM archive_memory_events event
JOIN archive_memories memory
  ON memory.tenant_id = event.tenant_id
 AND memory.memory_id = event.memory_id
JOIN assets asset
  ON asset.tenant_id = memory.tenant_id
 AND asset.asset_id = memory.asset_id
WHERE event.tenant_id::text = $1
  AND asset.project_id::text = $2
  AND memory.asset_id::text = $3
ORDER BY event.created_at DESC, event.event_id::text ASC
LIMIT $4`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.ProjectID), strings.TrimSpace(input.AssetID), limit)
	if err != nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	records := []ArchiveMemoryEventRecord{}
	for rows.Next() {
		record, err := scanArchiveMemoryEventRecord(rows)
		if err != nil {
			return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
		}
		records = append(records, record)
	}
	if err := rows.Err(); err != nil {
		return nil, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	return records, nil
}

func (r *SQLArchiveMemoryReader) GetMemory(ctx context.Context, input GetArchiveMemoryInput) (ArchiveMemoryRecord, error) {
	if err := validateArchiveMemoryLookupInput(input.TenantID, input.MemoryID); err != nil {
		return ArchiveMemoryRecord{}, err
	}
	if r.queryer == nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_BACKEND_UNCONFIGURED", Message: "archive memory backend is not configured"}
	}
	query := `SELECT
  memory.memory_id::text,
  memory.asset_id::text,
  asset.project_id::text,
  memory.memory_type,
  memory.status,
  COALESCE(memory.summary, ''),
  memory.payload_jsonb::text,
  memory.source_kind,
  memory.source_ref,
  memory.enabled,
  memory.created_at::text,
  memory.updated_at::text
FROM archive_memories memory
JOIN assets asset
  ON asset.tenant_id = memory.tenant_id
 AND asset.asset_id = memory.asset_id
 AND asset.project_id = memory.project_id
WHERE memory.tenant_id::text = $1
  AND memory.memory_id::text = $2
LIMIT 1`
	rows, err := queryWithTenantContext(ctx, r.queryer, input.TenantID, query, strings.TrimSpace(input.TenantID), strings.TrimSpace(input.MemoryID))
	if err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	defer rows.Close()

	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
		}
		return ArchiveMemoryRecord{}, &AppError{Code: "NOT_FOUND", Message: "archive memory was not found"}
	}
	record, err := scanArchiveMemoryRecord(rows)
	if err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_QUERY_FAILED", Message: err.Error()}
	}
	return record, nil
}

func (s *SQLArchiveMemoryReviewStore) AdoptMemory(ctx context.Context, input ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error) {
	return s.reviewMemory(ctx, input, archiveMemoryReviewSpec{
		targetStatus: "canon",
		enabledSQL:   "TRUE",
		eventType:    "archive_memory.adopted",
		eventStatus:  "accepted",
		auditAction:  "archive_memory.adopt",
		notFoundText: "candidate archive memory was not found",
	})
}

func (s *SQLArchiveMemoryReviewStore) RejectMemory(ctx context.Context, input ArchiveMemoryReviewInput) (ArchiveMemoryRecord, error) {
	return s.reviewMemory(ctx, input, archiveMemoryReviewSpec{
		targetStatus: "rejected",
		enabledSQL:   "FALSE",
		eventType:    "archive_memory.rejected",
		eventStatus:  "rejected",
		auditAction:  "archive_memory.reject",
		notFoundText: "candidate archive memory was not found",
	})
}

type archiveMemoryReviewSpec struct {
	targetStatus string
	enabledSQL   string
	eventType    string
	eventStatus  string
	auditAction  string
	notFoundText string
}

func (s *SQLArchiveMemoryReviewStore) reviewMemory(ctx context.Context, input ArchiveMemoryReviewInput, spec archiveMemoryReviewSpec) (ArchiveMemoryRecord, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	memoryID := strings.TrimSpace(input.MemoryID)
	if tenantID == "" || projectID == "" || memoryID == "" {
		return ArchiveMemoryRecord{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and memory_id are required"}
	}
	if s.queryer == nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_REVIEW_BACKEND_UNCONFIGURED", Message: "archive memory review backend is not configured"}
	}
	query := `WITH reviewed AS (
  UPDATE archive_memories memory
  SET status = '` + spec.targetStatus + `',
      enabled = ` + spec.enabledSQL + `,
      updated_at = now()
  FROM assets asset
  WHERE memory.tenant_id::text = $1
    AND memory.project_id::text = $2
    AND memory.memory_id::text = $3
    AND memory.status = 'candidate'
    AND asset.tenant_id = memory.tenant_id
    AND asset.asset_id = memory.asset_id
    AND asset.project_id = memory.project_id
  RETURNING
    memory.memory_id,
    memory.asset_id,
    memory.project_id,
    memory.memory_type,
    memory.status,
    memory.summary,
    memory.payload_jsonb,
    memory.source_kind,
    memory.source_ref,
    memory.enabled,
    memory.created_at,
    memory.updated_at
),
memory_event AS (
  INSERT INTO archive_memory_events (
    tenant_id, memory_id, asset_id, project_id, event_type, status,
    payload_jsonb, actor_user_id
  )
  SELECT
    $1::uuid,
    reviewed.memory_id,
    reviewed.asset_id,
    reviewed.project_id,
    '` + spec.eventType + `',
    '` + spec.eventStatus + `',
    jsonb_build_object(
      'memory_id', reviewed.memory_id::text,
      'asset_id', reviewed.asset_id::text,
      'actor_id', $4,
      'request_id', $5
    ),
    CASE
      WHEN $4 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $4::uuid
      ELSE NULL
    END
  FROM reviewed
  RETURNING event_id
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $4 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $4::uuid
      ELSE NULL
    END,
    '` + spec.auditAction + `',
    'archive_memory',
    reviewed.memory_id,
    reviewed.project_id,
    NULL,
    $5,
    jsonb_build_object(
      'memory_id', reviewed.memory_id::text,
      'asset_id', reviewed.asset_id::text,
      'actor_id', $4,
      'target_status', '` + spec.targetStatus + `',
      'source_kind', reviewed.source_kind,
      'source_ref', reviewed.source_ref
    )
  FROM reviewed
  RETURNING audit_id
)
SELECT
  memory_id::text,
  asset_id::text,
  project_id::text,
  memory_type,
  status,
  COALESCE(summary, ''),
  payload_jsonb::text,
  source_kind,
  source_ref,
  enabled,
  created_at::text,
  updated_at::text
FROM reviewed`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		tenantID,
		projectID,
		memoryID,
		strings.TrimSpace(input.ActorID),
		strings.TrimSpace(input.RequestID),
	)
	if err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_REVIEW_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_REVIEW_FAILED", Message: err.Error()}
		}
		return ArchiveMemoryRecord{}, &AppError{Code: "NOT_FOUND", Message: spec.notFoundText}
	}
	record, err := scanArchiveMemoryRecord(rows)
	if err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_REVIEW_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return ArchiveMemoryRecord{}, &AppError{Code: "ARCHIVE_MEMORY_REVIEW_FAILED", Message: err.Error()}
	}
	return record, nil
}

func (s *SQLAdoptionStore) AdoptAsset(ctx context.Context, input AdoptAssetInput) (Record, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	assetID := strings.TrimSpace(input.AssetID)
	targetLifecycle := strings.TrimSpace(input.TargetLifecycle)
	if tenantID == "" || assetID == "" {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and asset_id are required"}
	}
	if targetLifecycle != "canon" && targetLifecycle != "material" {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: "target_lifecycle must be canon or material"}
	}
	if s.queryer == nil {
		return Record{}, &AppError{Code: "ASSET_ADOPTION_BACKEND_UNCONFIGURED", Message: "asset adoption backend is not configured"}
	}
	query := `WITH adopted AS (
  UPDATE assets
  SET lifecycle = $3,
      updated_at = now()
  WHERE tenant_id::text = $1
    AND asset_id::text = $2
    AND lifecycle = 'candidate'
  RETURNING
    asset_id,
    project_id,
    scope,
    asset_type,
    category,
    lifecycle,
    title,
    summary,
    source_kind,
    source_ref,
    enabled,
    pinned,
    tags_jsonb,
    payload_jsonb,
    created_at,
    updated_at
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $4 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $4::uuid
      ELSE NULL
    END,
    'asset.adopt',
    'asset',
    adopted.asset_id,
    adopted.project_id,
    NULL,
    $5,
    jsonb_build_object(
      'asset_id', adopted.asset_id::text,
      'actor_id', $4,
      'target_lifecycle', $3,
      'source_kind', adopted.source_kind,
      'source_ref', adopted.source_ref
    )
  FROM adopted
  RETURNING audit_id
)
SELECT
  asset_id::text,
  project_id::text,
  scope,
  asset_type,
  COALESCE(category, ''),
  lifecycle,
  title,
  COALESCE(summary, ''),
  source_kind,
  source_ref,
  enabled,
  pinned,
  tags_jsonb::text,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM adopted`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		tenantID,
		assetID,
		targetLifecycle,
		strings.TrimSpace(input.ActorID),
		strings.TrimSpace(input.RequestID),
	)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_ADOPTION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return Record{}, &AppError{Code: "ASSET_ADOPTION_FAILED", Message: err.Error()}
		}
		return Record{}, &AppError{Code: "NOT_FOUND", Message: "candidate asset was not found"}
	}
	record, err := scanAssetRecord(rows)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_ADOPTION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return Record{}, &AppError{Code: "ASSET_ADOPTION_FAILED", Message: err.Error()}
	}
	return record, nil
}

func (s *SQLMutationStore) CreateAsset(ctx context.Context, input CreateAssetInput) (Record, error) {
	normalized, err := normalizeCreateInput(input)
	if err != nil {
		return Record{}, err
	}
	if s.queryer == nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_BACKEND_UNCONFIGURED", Message: "asset mutation backend is not configured"}
	}
	payloadJSON, err := encodeObject(normalized.Payload)
	if err != nil {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: err.Error()}
	}
	tagsJSON, err := encodeTags(normalized.Tags)
	if err != nil {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: err.Error()}
	}
	query := `WITH created AS (
  INSERT INTO assets (
    tenant_id, project_id, scope, asset_type, category, lifecycle,
    title, summary, content_text, payload_jsonb, tags_jsonb,
    source_kind, source_ref, enabled, pinned, created_by
  )
  VALUES (
    $1::uuid, $2::uuid, $3, $4, NULLIF($5, ''), $6,
    $7, NULLIF($8, ''), NULLIF($9, ''), $10::jsonb, $11::jsonb,
    $12, $13, $14, $15,
    CASE
      WHEN $16 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $16::uuid
      ELSE NULL
    END
  )
  RETURNING
    asset_id, project_id, scope, asset_type, category, lifecycle, title, summary,
    source_kind, source_ref, enabled, pinned, tags_jsonb, payload_jsonb, created_at, updated_at
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $16 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $16::uuid
      ELSE NULL
    END,
    'asset.create',
    'asset',
    created.asset_id,
    created.project_id,
    NULL,
    $17,
    jsonb_build_object(
      'asset_id', created.asset_id::text,
      'actor_id', $16,
      'asset_type', created.asset_type,
      'lifecycle', created.lifecycle,
      'source_kind', created.source_kind,
      'source_ref', created.source_ref
    )
  FROM created
  RETURNING audit_id
)
SELECT
  asset_id::text,
  project_id::text,
  scope,
  asset_type,
  COALESCE(category, ''),
  lifecycle,
  title,
  COALESCE(summary, ''),
  source_kind,
  source_ref,
  enabled,
  pinned,
  tags_jsonb::text,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM created`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		normalized.TenantID,
		normalized.ProjectID,
		normalized.Scope,
		normalized.AssetType,
		normalized.Category,
		normalized.Lifecycle,
		normalized.Title,
		normalized.Summary,
		normalized.ContentText,
		payloadJSON,
		tagsJSON,
		normalized.SourceKind,
		normalized.SourceRef,
		*normalized.Enabled,
		*normalized.Pinned,
		normalized.ActorID,
		normalized.RequestID,
	)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	return scanSingleMutatedAsset(rows)
}

func (s *SQLMutationStore) PatchAsset(ctx context.Context, input PatchAssetInput) (Record, error) {
	normalized, err := normalizePatchInput(input)
	if err != nil {
		return Record{}, err
	}
	if s.queryer == nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_BACKEND_UNCONFIGURED", Message: "asset mutation backend is not configured"}
	}
	payloadJSON, err := optionalObjectJSON(normalized.Payload)
	if err != nil {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: err.Error()}
	}
	tagsJSON, err := optionalTagsJSON(normalized.Tags)
	if err != nil {
		return Record{}, &AppError{Code: "VALIDATION_FAILED", Message: err.Error()}
	}
	query := `WITH updated AS (
  UPDATE assets
  SET scope = CASE WHEN $3 THEN $4 ELSE scope END,
      asset_type = CASE WHEN $5 THEN $6 ELSE asset_type END,
      category = CASE WHEN $7 THEN NULLIF($8, '') ELSE category END,
      lifecycle = CASE WHEN $9 THEN $10 ELSE lifecycle END,
      title = CASE WHEN $11 THEN $12 ELSE title END,
      summary = CASE WHEN $13 THEN NULLIF($14, '') ELSE summary END,
      content_text = CASE WHEN $15 THEN NULLIF($16, '') ELSE content_text END,
      payload_jsonb = CASE WHEN $17 THEN $18::jsonb ELSE payload_jsonb END,
      tags_jsonb = CASE WHEN $19 THEN $20::jsonb ELSE tags_jsonb END,
      source_kind = CASE WHEN $21 THEN $22 ELSE source_kind END,
      source_ref = CASE WHEN $23 THEN $24 ELSE source_ref END,
      enabled = CASE WHEN $25 THEN $26 ELSE enabled END,
      pinned = CASE WHEN $27 THEN $28 ELSE pinned END,
      updated_at = now()
  WHERE tenant_id::text = $1
    AND asset_id::text = $2
  RETURNING
    asset_id, project_id, scope, asset_type, category, lifecycle, title, summary,
    source_kind, source_ref, enabled, pinned, tags_jsonb, payload_jsonb, created_at, updated_at
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $29 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $29::uuid
      ELSE NULL
    END,
    'asset.update',
    'asset',
    updated.asset_id,
    updated.project_id,
    NULL,
    $30,
    jsonb_build_object(
      'asset_id', updated.asset_id::text,
      'actor_id', $29,
      'asset_type', updated.asset_type,
      'lifecycle', updated.lifecycle
    )
  FROM updated
  RETURNING audit_id
)
SELECT
  asset_id::text,
  project_id::text,
  scope,
  asset_type,
  COALESCE(category, ''),
  lifecycle,
  title,
  COALESCE(summary, ''),
  source_kind,
  source_ref,
  enabled,
  pinned,
  tags_jsonb::text,
  payload_jsonb::text,
  created_at::text,
  updated_at::text
FROM updated`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		normalized.TenantID,
		normalized.AssetID,
		normalized.Scope != nil, derefString(normalized.Scope),
		normalized.AssetType != nil, derefString(normalized.AssetType),
		normalized.Category != nil, derefString(normalized.Category),
		normalized.Lifecycle != nil, derefString(normalized.Lifecycle),
		normalized.Title != nil, derefString(normalized.Title),
		normalized.Summary != nil, derefString(normalized.Summary),
		normalized.ContentText != nil, derefString(normalized.ContentText),
		normalized.Payload != nil, payloadJSON,
		normalized.Tags != nil, tagsJSON,
		normalized.SourceKind != nil, derefString(normalized.SourceKind),
		normalized.SourceRef != nil, derefString(normalized.SourceRef),
		normalized.Enabled != nil, derefBool(normalized.Enabled),
		normalized.Pinned != nil, derefBool(normalized.Pinned),
		normalized.ActorID,
		normalized.RequestID,
	)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	return scanSingleMutatedAsset(rows)
}

func (s *SQLMutationStore) DeleteAsset(ctx context.Context, input DeleteAssetInput) (DeleteResult, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	assetID := strings.TrimSpace(input.AssetID)
	if tenantID == "" || assetID == "" {
		return DeleteResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and asset_id are required"}
	}
	if s.queryer == nil {
		return DeleteResult{}, &AppError{Code: "ASSET_MUTATION_BACKEND_UNCONFIGURED", Message: "asset mutation backend is not configured"}
	}
	query := `WITH deleted AS (
  DELETE FROM assets
  WHERE tenant_id::text = $1
    AND asset_id::text = $2
  RETURNING asset_id, project_id, asset_type, source_kind, source_ref
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $3 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $3::uuid
      ELSE NULL
    END,
    'asset.delete',
    'asset',
    deleted.asset_id,
    deleted.project_id,
    NULL,
    $4,
    jsonb_build_object(
      'asset_id', deleted.asset_id::text,
      'actor_id', $3,
      'asset_type', deleted.asset_type,
      'source_kind', deleted.source_kind,
      'source_ref', deleted.source_ref
    )
  FROM deleted
  RETURNING audit_id
)
SELECT asset_id::text, project_id::text, true
FROM deleted`
	rows, err := s.queryer.QueryContext(ctx, query, tenantID, assetID, strings.TrimSpace(input.ActorID), strings.TrimSpace(input.RequestID))
	if err != nil {
		return DeleteResult{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return DeleteResult{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
		}
		return DeleteResult{}, &AppError{Code: "NOT_FOUND", Message: "asset was not found"}
	}
	var result DeleteResult
	if err := rows.Scan(&result.AssetID, &result.ProjectID, &result.Deleted); err != nil {
		return DeleteResult{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return DeleteResult{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	return result, nil
}

func (s *SQLBulkActionStore) ApplyBulkAction(ctx context.Context, input BulkActionInput) (BulkActionResult, error) {
	normalized, err := normalizeBulkActionInput(input)
	if err != nil {
		return BulkActionResult{}, err
	}
	if s.queryer == nil {
		return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_BACKEND_UNCONFIGURED", Message: "asset bulk action backend is not configured"}
	}
	payloadJSON, err := encodeObject(normalized.Payload)
	if err != nil {
		return BulkActionResult{}, &AppError{Code: "VALIDATION_FAILED", Message: err.Error()}
	}
	query := `WITH selected AS (
  SELECT COUNT(*)::int AS matched_count
  FROM assets
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND asset_id::text = ANY($3::text[])
),
updated AS (
  UPDATE assets
  SET lifecycle = CASE WHEN $4 = 'set_lifecycle' THEN $5 ELSE lifecycle END,
      category = CASE WHEN $4 = 'categorize' THEN NULLIF($6, '') ELSE category END,
      enabled = CASE WHEN $7 THEN $8 ELSE enabled END,
      pinned = CASE WHEN $9 THEN $10 ELSE pinned END,
      updated_at = now()
  WHERE tenant_id::text = $1
    AND project_id::text = $2
    AND asset_id::text = ANY($3::text[])
  RETURNING asset_id
),
counts AS (
  SELECT
    (SELECT matched_count FROM selected) AS matched_count,
    COUNT(updated.asset_id)::int AS updated_count
  FROM updated
),
audit AS (
  INSERT INTO audit_logs (
    tenant_id, actor_user_id, action, resource_type, resource_id,
    project_id, run_id, request_id, metadata_jsonb
  )
  SELECT
    $1::uuid,
    CASE
      WHEN $12 ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN $12::uuid
      ELSE NULL
    END,
    'asset.bulk_action',
    'asset_bulk_action',
    NULL,
    $2::uuid,
    NULL,
    $13,
    jsonb_build_object(
      'actor_id', $12,
      'action', $4,
      'matched_count', counts.matched_count,
      'updated_count', counts.updated_count,
      'target_lifecycle', NULLIF($5, ''),
      'category', NULLIF($6, ''),
      'enabled_updated', $7,
      'pinned_updated', $9,
      'options', $11::jsonb
    )
  FROM counts
  RETURNING audit_id
)
SELECT
  $2 AS project_id,
  $4 AS action,
  'completed' AS status,
  counts.matched_count,
  counts.updated_count
FROM counts`
	rows, err := s.queryer.QueryContext(
		ctx,
		query,
		normalized.TenantID,
		normalized.ProjectID,
		normalized.AssetIDs,
		normalized.Action,
		normalized.TargetLifecycle,
		normalized.Category,
		normalized.Enabled != nil,
		derefBool(normalized.Enabled),
		normalized.Pinned != nil,
		derefBool(normalized.Pinned),
		payloadJSON,
		normalized.ActorID,
		normalized.RequestID,
	)
	if err != nil {
		return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_FAILED", Message: err.Error()}
	}
	defer rows.Close()
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_FAILED", Message: err.Error()}
		}
		return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_FAILED", Message: "asset bulk action did not return a result"}
	}
	var result BulkActionResult
	if err := rows.Scan(&result.ProjectID, &result.Action, &result.Status, &result.MatchedCount, &result.UpdatedCount); err != nil {
		return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return BulkActionResult{}, &AppError{Code: "ASSET_BULK_ACTION_FAILED", Message: err.Error()}
	}
	return result, nil
}

func scanSingleMutatedAsset(rows SQLRows) (Record, error) {
	if !rows.Next() {
		if err := rows.Err(); err != nil {
			return Record{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
		}
		return Record{}, &AppError{Code: "NOT_FOUND", Message: "asset was not found"}
	}
	record, err := scanAssetRecord(rows)
	if err != nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	if err := rows.Err(); err != nil {
		return Record{}, &AppError{Code: "ASSET_MUTATION_FAILED", Message: err.Error()}
	}
	return record, nil
}

func scanAssetRecord(rows SQLRows) (Record, error) {
	var record Record
	var tagsJSON string
	var payloadJSON string
	if err := rows.Scan(
		&record.AssetID,
		&record.ProjectID,
		&record.Scope,
		&record.AssetType,
		&record.Category,
		&record.Lifecycle,
		&record.Title,
		&record.Summary,
		&record.SourceKind,
		&record.SourceRef,
		&record.Enabled,
		&record.Pinned,
		&tagsJSON,
		&payloadJSON,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return Record{}, err
	}
	record.Tags = decodeTags(tagsJSON)
	record.Payload = sanitizeObject(decodeObject(payloadJSON))
	return record, nil
}

func scanArchiveMemoryRecord(rows SQLRows) (ArchiveMemoryRecord, error) {
	var record ArchiveMemoryRecord
	var payloadJSON string
	if err := rows.Scan(
		&record.MemoryID,
		&record.AssetID,
		&record.ProjectID,
		&record.MemoryType,
		&record.Status,
		&record.Summary,
		&payloadJSON,
		&record.SourceKind,
		&record.SourceRef,
		&record.Enabled,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		return ArchiveMemoryRecord{}, err
	}
	record.Payload = sanitizeObject(decodeObject(payloadJSON))
	return record, nil
}

func scanArchiveMemoryEventRecord(rows SQLRows) (ArchiveMemoryEventRecord, error) {
	var record ArchiveMemoryEventRecord
	var payloadJSON string
	if err := rows.Scan(
		&record.EventID,
		&record.MemoryID,
		&record.AssetID,
		&record.ProjectID,
		&record.EventType,
		&record.Status,
		&payloadJSON,
		&record.ActorID,
		&record.CreatedAt,
	); err != nil {
		return ArchiveMemoryEventRecord{}, err
	}
	record.Payload = decodeObject(payloadJSON)
	return record, nil
}

func validateProjectInput(tenantID string, projectID string) error {
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(projectID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	return nil
}

func validateArchiveMemoryInput(tenantID string, projectID string, assetID string) error {
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(projectID) == "" || strings.TrimSpace(assetID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and asset_id are required"}
	}
	return nil
}

func validateArchiveMemoryLookupInput(tenantID string, memoryID string) error {
	if strings.TrimSpace(tenantID) == "" || strings.TrimSpace(memoryID) == "" {
		return &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and memory_id are required"}
	}
	return nil
}

func normalizeCreateInput(input CreateAssetInput) (CreateAssetInput, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.ActorID = strings.TrimSpace(input.ActorID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Scope = defaultString(input.Scope, "project")
	input.AssetType = strings.TrimSpace(input.AssetType)
	input.Category = strings.TrimSpace(input.Category)
	input.Lifecycle = defaultString(input.Lifecycle, "material")
	input.Title = strings.TrimSpace(input.Title)
	input.Summary = strings.TrimSpace(input.Summary)
	input.SourceKind = defaultString(input.SourceKind, "manual")
	input.SourceRef = defaultString(input.SourceRef, input.RequestID)
	input.Payload = sanitizeObject(input.Payload)
	input.Tags = sanitizeTags(input.Tags)
	if input.Enabled == nil {
		value := true
		input.Enabled = &value
	}
	if input.Pinned == nil {
		value := false
		input.Pinned = &value
	}
	if input.TenantID == "" || input.ProjectID == "" {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if input.AssetType == "" || input.Title == "" {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "asset_type and title are required"}
	}
	if !validScope(input.Scope) {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "scope must be tenant, project, or system"}
	}
	if !validLifecycle(input.Lifecycle) {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "invalid asset lifecycle"}
	}
	if input.SourceKind == "" || input.SourceRef == "" {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "source_kind and source_ref are required"}
	}
	return input, nil
}

func normalizePatchInput(input PatchAssetInput) (PatchAssetInput, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.AssetID = strings.TrimSpace(input.AssetID)
	input.ActorID = strings.TrimSpace(input.ActorID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	trimStringPtr(input.Scope)
	trimStringPtr(input.AssetType)
	trimStringPtr(input.Category)
	trimStringPtr(input.Lifecycle)
	trimStringPtr(input.Title)
	trimStringPtr(input.Summary)
	trimStringPtr(input.ContentText)
	trimStringPtr(input.SourceKind)
	trimStringPtr(input.SourceRef)
	if input.Payload != nil {
		value := sanitizeObject(*input.Payload)
		input.Payload = &value
	}
	if input.Tags != nil {
		value := sanitizeTags(*input.Tags)
		input.Tags = &value
	}
	if input.TenantID == "" || input.AssetID == "" {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and asset_id are required"}
	}
	if input.Scope != nil && !validScope(*input.Scope) {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "scope must be tenant, project, or system"}
	}
	if input.Lifecycle != nil && !validLifecycle(*input.Lifecycle) {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "invalid asset lifecycle"}
	}
	return input, nil
}

func normalizeBulkActionInput(input BulkActionInput) (BulkActionInput, error) {
	input.TenantID = strings.TrimSpace(input.TenantID)
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.ActorID = strings.TrimSpace(input.ActorID)
	input.RequestID = strings.TrimSpace(input.RequestID)
	input.Action = strings.TrimSpace(input.Action)
	input.TargetLifecycle = strings.TrimSpace(input.TargetLifecycle)
	input.Category = strings.TrimSpace(input.Category)
	input.AssetIDs = uniqueNonEmptyStrings(input.AssetIDs)
	input.Payload = sanitizeObject(input.Payload)
	if input.TenantID == "" || input.ProjectID == "" {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	if len(input.AssetIDs) == 0 {
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "asset_ids are required"}
	}
	switch input.Action {
	case "enable":
		value := true
		input.Enabled = &value
	case "disable":
		value := false
		input.Enabled = &value
	case "pin":
		value := true
		input.Pinned = &value
	case "unpin":
		value := false
		input.Pinned = &value
	case "set_lifecycle":
		if !validLifecycle(input.TargetLifecycle) {
			return input, &AppError{Code: "VALIDATION_FAILED", Message: "invalid target lifecycle"}
		}
	case "categorize":
		if input.Category == "" {
			return input, &AppError{Code: "VALIDATION_FAILED", Message: "category is required"}
		}
	default:
		return input, &AppError{Code: "VALIDATION_FAILED", Message: "invalid asset bulk action"}
	}
	return input, nil
}

func validScope(scope string) bool {
	switch scope {
	case "tenant", "project", "system":
		return true
	default:
		return false
	}
}

func validLifecycle(lifecycle string) bool {
	switch lifecycle {
	case "seed", "candidate", "canon", "material", "simulation", "draft", "manuscript", "archived":
		return true
	default:
		return false
	}
}

func defaultString(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}

func trimStringPtr(value *string) {
	if value == nil {
		return
	}
	*value = strings.TrimSpace(*value)
}

func derefString(value *string) string {
	if value == nil {
		return ""
	}
	return *value
}

func derefBool(value *bool) bool {
	if value == nil {
		return false
	}
	return *value
}

func optionalObjectJSON(value *map[string]any) (string, error) {
	if value == nil {
		return "{}", nil
	}
	return encodeObject(*value)
}

func optionalTagsJSON(value *[]string) (string, error) {
	if value == nil {
		return "[]", nil
	}
	return encodeTags(*value)
}

func encodeObject(value map[string]any) (string, error) {
	if value == nil {
		value = map[string]any{}
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func encodeTags(value []string) (string, error) {
	if value == nil {
		value = []string{}
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	return string(raw), nil
}

func sanitizeObject(value map[string]any) map[string]any {
	clean := map[string]any{}
	for key, item := range value {
		if isHighRiskField(key) {
			continue
		}
		clean[key] = sanitizeValue(item)
	}
	return clean
}

func sanitizeValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return sanitizeObject(typed)
	case []any:
		values := make([]any, 0, len(typed))
		for _, item := range typed {
			values = append(values, sanitizeValue(item))
		}
		return values
	default:
		return value
	}
}

func sanitizeTags(tags []string) []string {
	clean := make([]string, 0, len(tags))
	for _, tag := range tags {
		value := strings.TrimSpace(tag)
		if value == "" || isHighRiskField(value) {
			continue
		}
		clean = append(clean, value)
	}
	return clean
}

func isHighRiskField(field string) bool {
	switch normalizeRiskField(field) {
	case "apikey",
		"encryptedapikey",
		"encryptedcredential",
		"credentialref",
		"materialtext",
		"sourcematerial",
		"sourcetext",
		"inputtext",
		"outputtext",
		"prompt",
		"response",
		"rawbody",
		"rawcontent",
		"body",
		"content",
		"bodytext",
		"contenttext",
		"rawtext",
		"objectkey",
		"sourceobjectkey",
		"artifactobjectkey",
		"segmentobjectkey",
		"candidatebody",
		"eventbody",
		"candidateeventbody",
		"draft",
		"drafttext",
		"manuscript":
		return true
	case "manuscripttext":
		return true
	default:
		return false
	}
}

func normalizeRiskField(field string) string {
	field = strings.TrimSpace(field)
	var builder strings.Builder
	builder.Grow(len(field))
	for _, char := range field {
		switch char {
		case '_', '-', ' ', '.', ':':
			continue
		default:
			builder.WriteRune(char)
		}
	}
	return strings.ToLower(builder.String())
}

func uniqueNonEmptyStrings(values []string) []string {
	clean := make([]string, 0, len(values))
	seen := map[string]struct{}{}
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		clean = append(clean, trimmed)
	}
	return clean
}

func decodeTags(raw string) []string {
	var values []string
	if err := json.Unmarshal([]byte(raw), &values); err != nil {
		return []string{}
	}
	return values
}

func decodeObject(raw string) map[string]any {
	var value map[string]any
	if err := json.Unmarshal([]byte(raw), &value); err != nil {
		return map[string]any{}
	}
	return value
}

func decodeCollectionRefs(raw string) []CollectionRef {
	var values []CollectionRef
	if err := json.Unmarshal([]byte(raw), &values); err != nil {
		return []CollectionRef{}
	}
	clean := []CollectionRef{}
	for _, value := range values {
		collection := CollectionRef{
			CollectionID: strings.TrimSpace(value.CollectionID),
			Title:        strings.TrimSpace(value.Title),
			Lifecycle:    strings.TrimSpace(value.Lifecycle),
		}
		if collection.CollectionID == "" {
			continue
		}
		clean = append(clean, collection)
	}
	return clean
}
