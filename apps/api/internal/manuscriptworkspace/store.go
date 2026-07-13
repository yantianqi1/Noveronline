package manuscriptworkspace

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"unicode"
)

type SQLStore struct {
	db *sql.DB
}

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func (s *SQLStore) ListBlocks(ctx context.Context, scope Scope, includeDeleted bool) ([]BlockMetadata, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, false); err != nil {
		return nil, err
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return nil, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	rows, err := tx.QueryContext(ctx, blockSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2
  AND ($3 OR status <> 'deleted')
ORDER BY block_order, block_id`, scope.TenantID, scope.ProjectID, includeDeleted)
	if err != nil {
		return nil, queryFailed()
	}
	blocks, err := scanMetadataRows(rows)
	if err != nil {
		return nil, queryFailed()
	}
	if err := tx.Commit(); err != nil {
		return nil, queryFailed()
	}
	return blocks, nil
}

func (s *SQLStore) GetPrivateBlock(ctx context.Context, scope Scope, blockID string) (PrivateBlock, error) {
	scope = normalizeScope(scope)
	blockID = strings.TrimSpace(blockID)
	if err := validateScope(scope, false); err != nil || blockID == "" {
		return PrivateBlock{}, validation("tenant_id, project_id, actor_user_id, and block_id are required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return PrivateBlock{}, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	block, err := getPrivateBlock(ctx, tx, scope, blockID, false)
	if err != nil {
		return PrivateBlock{}, err
	}
	if err := tx.Commit(); err != nil {
		return PrivateBlock{}, queryFailed()
	}
	return block, nil
}

func (s *SQLStore) CreateBlock(ctx context.Context, input CreateBlockInput) (PrivateBlock, error) {
	input.Scope = normalizeScope(input.Scope)
	input.ChapterID = strings.TrimSpace(input.ChapterID)
	input.SceneID = strings.TrimSpace(input.SceneID)
	if err := validateScope(input.Scope, true); err != nil {
		return PrivateBlock{}, err
	}
	tags, err := normalizeTags(input.Tags)
	if err != nil {
		return PrivateBlock{}, err
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := lockProject(ctx, tx, input.Scope); err != nil {
		return PrivateBlock{}, err
	}
	if err := validateLocation(ctx, tx, input.Scope, input.ChapterID, input.SceneID); err != nil {
		return PrivateBlock{}, err
	}
	nextOrder, err := nextActiveBlockOrder(ctx, tx, input.Scope)
	if err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	var created PrivateBlock
	err = scanPrivateBlock(tx.QueryRowContext(ctx, `INSERT INTO manuscript_blocks (
  tenant_id, project_id, chapter_id, scene_id, source_draft_id, source_writer_run_id,
  block_order, content_text, word_count, version, status, tags, created_by, updated_by
) VALUES (
  $1::uuid, $2::uuid, NULLIF($3, '')::uuid, NULLIF($4, '')::uuid, NULL, NULL,
  $5, $6, $7, 1, 'active', $8, $9::uuid, $9::uuid
)
RETURNING block_id::text, project_id::text, COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''), status, to_json(tags)::text,
  block_order, word_count, version, created_at::text, updated_at::text, content_text`,
		input.TenantID, input.ProjectID, input.ChapterID, input.SceneID, nextOrder,
		input.ContentText, countWords(input.ContentText), tags, input.ActorUserID), &created)
	if err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	if err := recordVersion(ctx, tx, input.Scope, created, "create", ""); err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	if err := tx.Commit(); err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	return created, nil
}

func (s *SQLStore) UpdateBlock(ctx context.Context, input UpdateBlockInput) (PrivateBlock, error) {
	input.Scope = normalizeScope(input.Scope)
	input.BlockID = strings.TrimSpace(input.BlockID)
	if err := validateMutation(input.Scope, input.BlockID, input.ExpectedVersion); err != nil {
		return PrivateBlock{}, err
	}
	if input.ContentText == nil && input.Status == nil && input.Tags == nil && input.ChapterID == nil && input.SceneID == nil {
		return PrivateBlock{}, validation("at least one manuscript block field is required")
	}
	if input.Status != nil && *input.Status != "active" && *input.Status != "deleted" {
		return PrivateBlock{}, validation("status must be active or deleted")
	}
	if input.Tags != nil {
		tags, err := normalizeTags(*input.Tags)
		if err != nil {
			return PrivateBlock{}, err
		}
		input.Tags = &tags
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	defer func() { _ = tx.Rollback() }()
	current, err := getPrivateBlock(ctx, tx, input.Scope, input.BlockID, true)
	if err != nil {
		return PrivateBlock{}, err
	}
	if current.Version != input.ExpectedVersion {
		return PrivateBlock{}, versionConflict()
	}
	if current.Status == "deleted" {
		return PrivateBlock{}, &AppError{Code: "MANUSCRIPT_BLOCK_DELETED", Message: "deleted manuscript blocks can only be restored from a version"}
	}
	chapterID, sceneID := updatedLocation(current, input.ChapterID, input.SceneID)
	if err := validateLocation(ctx, tx, input.Scope, chapterID, sceneID); err != nil {
		return PrivateBlock{}, err
	}
	reason := updateReason(input)
	if err := recordVersion(ctx, tx, input.Scope, current, reason, ""); err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	updated, err := updateLockedBlock(ctx, tx, input, current, chapterID, sceneID)
	if err != nil {
		return PrivateBlock{}, err
	}
	if err := recordVersion(ctx, tx, input.Scope, updated, reason, ""); err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	if err := tx.Commit(); err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	return updated, nil
}

func (s *SQLStore) DeleteBlock(ctx context.Context, input DeleteBlockInput) (BlockMetadata, error) {
	status := "deleted"
	result, err := s.UpdateBlock(ctx, UpdateBlockInput{
		Scope: input.Scope, BlockID: input.BlockID, ExpectedVersion: input.ExpectedVersion, Status: &status,
	})
	return result.BlockMetadata, err
}

func (s *SQLStore) TagBlock(ctx context.Context, input TagBlockInput) (BlockMetadata, error) {
	tags := append([]string(nil), input.Tags...)
	result, err := s.UpdateBlock(ctx, UpdateBlockInput{
		Scope: input.Scope, BlockID: input.BlockID, ExpectedVersion: input.ExpectedVersion, Tags: &tags,
	})
	return result.BlockMetadata, err
}

func (s *SQLStore) ReorderBlocks(ctx context.Context, input ReorderBlocksInput) ([]BlockMetadata, error) {
	return s.reorder(ctx, input.Scope, input.Items, nil)
}

func (s *SQLStore) MoveBlock(ctx context.Context, input MoveBlockInput) ([]BlockMetadata, error) {
	input.Scope = normalizeScope(input.Scope)
	input.BlockID = strings.TrimSpace(input.BlockID)
	input.ChapterID = strings.TrimSpace(input.ChapterID)
	input.SceneID = strings.TrimSpace(input.SceneID)
	if err := validateMutation(input.Scope, input.BlockID, input.ExpectedVersion); err != nil {
		return nil, err
	}
	return s.reorder(ctx, input.Scope, input.Items, &input)
}

func (s *SQLStore) reorder(ctx context.Context, scope Scope, items []ReorderItem, move *MoveBlockInput) ([]BlockMetadata, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, true); err != nil {
		return nil, err
	}
	if len(items) == 0 {
		return nil, validation("ordered manuscript blocks are required")
	}
	if err := validateReorderItems(items); err != nil {
		return nil, err
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return nil, reorderFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := lockProject(ctx, tx, scope); err != nil {
		return nil, err
	}
	blocks, err := lockActiveBlocks(ctx, tx, scope)
	if err != nil {
		return nil, err
	}
	if err := requireExactOrder(blocks, items); err != nil {
		return nil, err
	}
	if move != nil {
		if err := validateMove(blocks, *move); err != nil {
			return nil, err
		}
		if err := validateLocation(ctx, tx, scope, move.ChapterID, move.SceneID); err != nil {
			return nil, err
		}
	}
	if err := persistReorder(ctx, tx, scope, blocks, items, move); err != nil {
		return nil, err
	}
	result, err := listBlocksTx(ctx, tx, scope, false)
	if err != nil {
		return nil, reorderFailed()
	}
	if err := tx.Commit(); err != nil {
		return nil, reorderFailed()
	}
	return result, nil
}

func (s *SQLStore) ListVersions(ctx context.Context, scope Scope, blockID string) ([]BlockVersion, error) {
	scope = normalizeScope(scope)
	blockID = strings.TrimSpace(blockID)
	if err := validateScope(scope, false); err != nil || blockID == "" {
		return nil, validation("tenant_id, project_id, actor_user_id, and block_id are required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return nil, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := getPrivateBlock(ctx, tx, scope, blockID, false); err != nil {
		return nil, err
	}
	rows, err := tx.QueryContext(ctx, versionSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3
ORDER BY version_number DESC`, scope.TenantID, scope.ProjectID, blockID)
	if err != nil {
		return nil, queryFailed()
	}
	versions := []BlockVersion{}
	for rows.Next() {
		version, _, err := scanVersion(rows)
		if err != nil {
			_ = rows.Close()
			return nil, queryFailed()
		}
		versions = append(versions, version)
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return nil, queryFailed()
	}
	if err := rows.Close(); err != nil {
		return nil, queryFailed()
	}
	if err := tx.Commit(); err != nil {
		return nil, queryFailed()
	}
	return versions, nil
}

func (s *SQLStore) GetPrivateVersion(ctx context.Context, scope Scope, blockID, versionID string) (PrivateBlockVersion, error) {
	scope = normalizeScope(scope)
	blockID, versionID = strings.TrimSpace(blockID), strings.TrimSpace(versionID)
	if err := validateScope(scope, false); err != nil || blockID == "" || versionID == "" {
		return PrivateBlockVersion{}, validation("tenant_id, project_id, actor_user_id, block_id, and version_id are required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return PrivateBlockVersion{}, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	version, err := getPrivateVersion(ctx, tx, scope, blockID, versionID)
	if err != nil {
		return PrivateBlockVersion{}, err
	}
	if err := tx.Commit(); err != nil {
		return PrivateBlockVersion{}, queryFailed()
	}
	return version, nil
}

func (s *SQLStore) RestoreVersion(ctx context.Context, input RestoreBlockInput) (PrivateBlock, error) {
	input.Scope = normalizeScope(input.Scope)
	input.BlockID, input.VersionID = strings.TrimSpace(input.BlockID), strings.TrimSpace(input.VersionID)
	if err := validateMutation(input.Scope, input.BlockID, input.ExpectedVersion); err != nil || input.VersionID == "" {
		return PrivateBlock{}, validation("tenant_id, project_id, actor_user_id, block_id, version_id, and expected_version are required")
	}
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return PrivateBlock{}, restoreFailed()
	}
	defer func() { _ = tx.Rollback() }()
	current, err := getPrivateBlock(ctx, tx, input.Scope, input.BlockID, true)
	if err != nil {
		return PrivateBlock{}, err
	}
	if current.Version != input.ExpectedVersion {
		return PrivateBlock{}, versionConflict()
	}
	target, err := getPrivateVersion(ctx, tx, input.Scope, input.BlockID, input.VersionID)
	if err != nil {
		return PrivateBlock{}, err
	}
	if err := validateLocation(ctx, tx, input.Scope, target.ChapterID, target.SceneID); err != nil {
		return PrivateBlock{}, err
	}
	if err := recordVersion(ctx, tx, input.Scope, current, "restore", ""); err != nil {
		return PrivateBlock{}, restoreFailed()
	}
	target.BlockOrder = current.BlockOrder
	if current.Status == "deleted" && target.Status == "active" {
		target.BlockOrder, err = nextActiveBlockOrder(ctx, tx, input.Scope)
		if err != nil {
			return PrivateBlock{}, restoreFailed()
		}
	}
	updated, err := restoreLockedBlock(ctx, tx, input, target)
	if err != nil {
		return PrivateBlock{}, err
	}
	if err := recordVersion(ctx, tx, input.Scope, updated, "restore", input.VersionID); err != nil {
		return PrivateBlock{}, restoreFailed()
	}
	if err := tx.Commit(); err != nil {
		return PrivateBlock{}, restoreFailed()
	}
	return updated, nil
}

func nextActiveBlockOrder(ctx context.Context, tx *sql.Tx, scope Scope) (int, error) {
	var order int
	err := tx.QueryRowContext(ctx, `SELECT COALESCE(MAX(block_order), 0) + 1
FROM manuscript_blocks WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'active'`,
		scope.TenantID, scope.ProjectID).Scan(&order)
	return order, err
}

func (s *SQLStore) begin(ctx context.Context, scope Scope) (*sql.Tx, error) {
	if s == nil || s.db == nil {
		return nil, errors.New("backend unavailable")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, $2::uuid, false)", scope.TenantID, scope.ActorUserID); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

const blockSelect = `SELECT block_id::text, project_id::text,
  COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''),
	status, to_json(tags)::text, block_order, word_count, version, created_at::text, updated_at::text
FROM manuscript_blocks`

const privateBlockSelect = `SELECT block_id::text, project_id::text,
  COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''),
	status, to_json(tags)::text, block_order, word_count, version, created_at::text, updated_at::text,
  content_text
FROM manuscript_blocks`

func getPrivateBlock(ctx context.Context, tx *sql.Tx, scope Scope, blockID string, lock bool) (PrivateBlock, error) {
	query := privateBlockSelect + ` WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3`
	if lock {
		query += " FOR UPDATE"
	}
	var block PrivateBlock
	err := scanPrivateBlock(tx.QueryRowContext(ctx, query, scope.TenantID, scope.ProjectID, blockID), &block)
	if errors.Is(err, sql.ErrNoRows) {
		return PrivateBlock{}, notFound("manuscript block not found")
	}
	if err != nil {
		return PrivateBlock{}, queryFailed()
	}
	return block, nil
}

type scanner interface{ Scan(...any) error }

func scanPrivateBlock(row scanner, block *PrivateBlock) error {
	var tags jsonStringList
	err := row.Scan(&block.BlockID, &block.ProjectID, &block.ChapterID, &block.SceneID,
		&block.SourceDraftID, &block.SourceWriterRunID, &block.Status, &tags,
		&block.BlockOrder, &block.WordCount, &block.Version, &block.CreatedAt, &block.UpdatedAt,
		&block.ContentText)
	block.Tags = []string(tags)
	return err
}

func scanMetadataRows(rows *sql.Rows) ([]BlockMetadata, error) {
	defer rows.Close()
	blocks := []BlockMetadata{}
	for rows.Next() {
		var block BlockMetadata
		var tags jsonStringList
		if err := rows.Scan(&block.BlockID, &block.ProjectID, &block.ChapterID, &block.SceneID,
			&block.SourceDraftID, &block.SourceWriterRunID, &block.Status, &tags,
			&block.BlockOrder, &block.WordCount, &block.Version, &block.CreatedAt, &block.UpdatedAt); err != nil {
			return nil, err
		}
		block.Tags = []string(tags)
		blocks = append(blocks, block)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return blocks, rows.Close()
}

func updateLockedBlock(ctx context.Context, tx *sql.Tx, input UpdateBlockInput, current PrivateBlock, chapterID, sceneID string) (PrivateBlock, error) {
	content, status, tags := current.ContentText, current.Status, current.Tags
	if input.ContentText != nil {
		content = *input.ContentText
	}
	if input.Status != nil {
		status = *input.Status
	}
	if input.Tags != nil {
		tags = *input.Tags
	}
	var updated PrivateBlock
	err := scanPrivateBlock(tx.QueryRowContext(ctx, `UPDATE manuscript_blocks SET
  chapter_id = NULLIF($5, '')::uuid, scene_id = NULLIF($6, '')::uuid,
  content_text = $7, word_count = $8, status = $9, tags = $10,
  version = version + 1, updated_by = $4::uuid, updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND version = $11
RETURNING block_id::text, project_id::text, COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
	  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''), status, to_json(tags)::text,
  block_order, word_count, version, created_at::text, updated_at::text, content_text`,
		input.TenantID, input.ProjectID, input.BlockID, input.ActorUserID, chapterID, sceneID,
		content, countWords(content), status, tags, input.ExpectedVersion), &updated)
	if errors.Is(err, sql.ErrNoRows) {
		return PrivateBlock{}, versionConflict()
	}
	if err != nil {
		return PrivateBlock{}, mutationFailed()
	}
	return updated, nil
}

func restoreLockedBlock(ctx context.Context, tx *sql.Tx, input RestoreBlockInput, target PrivateBlockVersion) (PrivateBlock, error) {
	var updated PrivateBlock
	err := scanPrivateBlock(tx.QueryRowContext(ctx, `UPDATE manuscript_blocks SET
  chapter_id = NULLIF($5, '')::uuid, scene_id = NULLIF($6, '')::uuid,
  content_text = $7, word_count = $8, status = $9, tags = $10,
  block_order = $11, version = version + 1, updated_by = $4::uuid, updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND version = $12
RETURNING block_id::text, project_id::text, COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
	  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''), status, to_json(tags)::text,
  block_order, word_count, version, created_at::text, updated_at::text, content_text`,
		input.TenantID, input.ProjectID, input.BlockID, input.ActorUserID, target.ChapterID, target.SceneID,
		target.ContentText, target.WordCount, target.Status, target.Tags, target.BlockOrder, input.ExpectedVersion), &updated)
	if errors.Is(err, sql.ErrNoRows) {
		return PrivateBlock{}, versionConflict()
	}
	if err != nil {
		return PrivateBlock{}, restoreFailed()
	}
	return updated, nil
}

func recordVersion(ctx context.Context, tx *sql.Tx, scope Scope, block PrivateBlock, reason, restoredFrom string) error {
	_, err := tx.ExecContext(ctx, `INSERT INTO manuscript_block_versions (
  tenant_id, project_id, block_id, version_number, chapter_id, scene_id, status, tags,
  block_order, content_text, word_count, pov_entity_id, source_draft_id, source_writer_run_id,
  snapshot_reason, restored_from_version_id, created_by
) SELECT tenant_id, project_id, block_id, version, chapter_id, scene_id, status, tags,
  block_order, content_text, word_count, pov_entity_id, source_draft_id, source_writer_run_id,
  $5, NULLIF($6, '')::uuid, $4::uuid
FROM manuscript_blocks
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND version = $7
ON CONFLICT (tenant_id, project_id, block_id, version_number) DO NOTHING`,
		scope.TenantID, scope.ProjectID, block.BlockID, scope.ActorUserID, reason, restoredFrom, block.Version)
	return err
}

const versionSelect = `SELECT version_id::text, block_id::text, version_number,
	COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''), status, to_json(tags)::text,
  block_order, word_count, snapshot_reason, COALESCE(restored_from_version_id::text, ''),
  created_by::text, created_at::text, content_text
FROM manuscript_block_versions`

func scanVersion(row scanner) (BlockVersion, string, error) {
	var version BlockVersion
	var content string
	var tags jsonStringList
	err := row.Scan(&version.VersionID, &version.BlockID, &version.VersionNumber,
		&version.ChapterID, &version.SceneID, &version.Status, &tags,
		&version.BlockOrder, &version.WordCount, &version.SnapshotReason,
		&version.RestoredFromVersionID, &version.CreatedBy, &version.CreatedAt, &content)
	version.Tags = []string(tags)
	return version, content, err
}

func getPrivateVersion(ctx context.Context, tx *sql.Tx, scope Scope, blockID, versionID string) (PrivateBlockVersion, error) {
	version, content, err := scanVersion(tx.QueryRowContext(ctx, versionSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND version_id::text = $4`,
		scope.TenantID, scope.ProjectID, blockID, versionID))
	if errors.Is(err, sql.ErrNoRows) {
		return PrivateBlockVersion{}, notFound("manuscript block version not found")
	}
	if err != nil {
		return PrivateBlockVersion{}, queryFailed()
	}
	return PrivateBlockVersion{BlockVersion: version, ContentText: content}, nil
}

func validateLocation(ctx context.Context, tx *sql.Tx, scope Scope, chapterID, sceneID string) error {
	if sceneID != "" && chapterID == "" {
		return validation("scene_id requires chapter_id")
	}
	if chapterID == "" {
		return nil
	}
	var found string
	if sceneID == "" {
		err := tx.QueryRowContext(ctx, `SELECT chapter_id::text FROM chapters
WHERE tenant_id::text = $1 AND project_id::text = $2 AND chapter_id::text = $3`,
			scope.TenantID, scope.ProjectID, chapterID).Scan(&found)
		return locationResult(err)
	}
	err := tx.QueryRowContext(ctx, `SELECT scene_id::text FROM scenes
WHERE tenant_id::text = $1 AND project_id::text = $2 AND scene_id::text = $3 AND chapter_id::text = $4`,
		scope.TenantID, scope.ProjectID, sceneID, chapterID).Scan(&found)
	return locationResult(err)
}

func locationResult(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return notFound("manuscript block chapter or scene not found")
	}
	if err != nil {
		return mutationFailed()
	}
	return nil
}

func lockProject(ctx context.Context, tx *sql.Tx, scope Scope) error {
	var id string
	err := tx.QueryRowContext(ctx, `SELECT project_id::text FROM projects
WHERE tenant_id::text = $1 AND project_id::text = $2 FOR UPDATE`, scope.TenantID, scope.ProjectID).Scan(&id)
	if errors.Is(err, sql.ErrNoRows) {
		return notFound("project not found")
	}
	if err != nil {
		return reorderFailed()
	}
	return nil
}

func lockActiveBlocks(ctx context.Context, tx *sql.Tx, scope Scope) ([]PrivateBlock, error) {
	rows, err := tx.QueryContext(ctx, privateBlockSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'active'
ORDER BY block_order, block_id FOR UPDATE`, scope.TenantID, scope.ProjectID)
	if err != nil {
		return nil, reorderFailed()
	}
	defer rows.Close()
	blocks := []PrivateBlock{}
	for rows.Next() {
		var block PrivateBlock
		if err := scanPrivateBlock(rows, &block); err != nil {
			return nil, reorderFailed()
		}
		blocks = append(blocks, block)
	}
	if err := rows.Err(); err != nil {
		return nil, reorderFailed()
	}
	return blocks, nil
}

func persistReorder(ctx context.Context, tx *sql.Tx, scope Scope, blocks []PrivateBlock, items []ReorderItem, move *MoveBlockInput) error {
	byID := make(map[string]PrivateBlock, len(blocks))
	for _, block := range blocks {
		byID[block.BlockID] = block
		if err := recordVersion(ctx, tx, scope, block, reorderReason(block.BlockID, move), ""); err != nil {
			return reorderFailed()
		}
	}
	if _, err := tx.ExecContext(ctx, `UPDATE manuscript_blocks SET block_order = -block_order - 1000000
WHERE tenant_id::text = $1 AND project_id::text = $2 AND status = 'active'`, scope.TenantID, scope.ProjectID); err != nil {
		return reorderFailed()
	}
	for index, item := range items {
		block := byID[item.BlockID]
		chapterID, sceneID := block.ChapterID, block.SceneID
		if move != nil && item.BlockID == move.BlockID {
			chapterID, sceneID = move.ChapterID, move.SceneID
		}
		var updated PrivateBlock
		err := scanPrivateBlock(tx.QueryRowContext(ctx, `UPDATE manuscript_blocks SET
  block_order = $5, chapter_id = NULLIF($6, '')::uuid, scene_id = NULLIF($7, '')::uuid,
  version = version + 1, updated_by = $4::uuid, updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND version = $8
RETURNING block_id::text, project_id::text, COALESCE(chapter_id::text, ''), COALESCE(scene_id::text, ''),
	  COALESCE(source_draft_id::text, ''), COALESCE(source_writer_run_id::text, ''), status, to_json(tags)::text,
  block_order, word_count, version, created_at::text, updated_at::text, content_text`,
			scope.TenantID, scope.ProjectID, item.BlockID, scope.ActorUserID, index+1,
			chapterID, sceneID, item.ExpectedVersion), &updated)
		if errors.Is(err, sql.ErrNoRows) {
			return versionConflict()
		}
		if err != nil {
			return reorderFailed()
		}
		if err := recordVersion(ctx, tx, scope, updated, reorderReason(item.BlockID, move), ""); err != nil {
			return reorderFailed()
		}
	}
	return nil
}

func listBlocksTx(ctx context.Context, tx *sql.Tx, scope Scope, includeDeleted bool) ([]BlockMetadata, error) {
	rows, err := tx.QueryContext(ctx, blockSelect+`
WHERE tenant_id::text = $1 AND project_id::text = $2 AND ($3 OR status <> 'deleted')
ORDER BY block_order, block_id`, scope.TenantID, scope.ProjectID, includeDeleted)
	if err != nil {
		return nil, err
	}
	return scanMetadataRows(rows)
}

func validateReorderItems(items []ReorderItem) error {
	seen := map[string]struct{}{}
	for _, item := range items {
		id := strings.TrimSpace(item.BlockID)
		if id == "" || item.ExpectedVersion <= 0 {
			return validation("each ordered block requires block_id and expected_version")
		}
		if _, exists := seen[id]; exists {
			return validation("ordered manuscript block ids must be unique")
		}
		seen[id] = struct{}{}
	}
	return nil
}

func requireExactOrder(blocks []PrivateBlock, items []ReorderItem) error {
	if len(blocks) != len(items) {
		return &AppError{Code: "MANUSCRIPT_REORDER_SET_MISMATCH", Message: "ordered block ids must match all active project blocks"}
	}
	versions := map[string]int{}
	for _, block := range blocks {
		versions[block.BlockID] = block.Version
	}
	for _, item := range items {
		version, ok := versions[item.BlockID]
		if !ok {
			return &AppError{Code: "MANUSCRIPT_REORDER_SET_MISMATCH", Message: "ordered block ids must match all active project blocks"}
		}
		if version != item.ExpectedVersion {
			return versionConflict()
		}
	}
	return nil
}

func validateMove(blocks []PrivateBlock, move MoveBlockInput) error {
	for _, block := range blocks {
		if block.BlockID == move.BlockID {
			if block.Version != move.ExpectedVersion {
				return versionConflict()
			}
			return nil
		}
	}
	return notFound("manuscript block not found")
}

func updatedLocation(current PrivateBlock, chapter, scene *string) (string, string) {
	chapterID, sceneID := current.ChapterID, current.SceneID
	if chapter != nil {
		chapterID = strings.TrimSpace(*chapter)
	}
	if scene != nil {
		sceneID = strings.TrimSpace(*scene)
	}
	return chapterID, sceneID
}

func updateReason(input UpdateBlockInput) string {
	if input.Status != nil && *input.Status == "deleted" {
		return "delete"
	}
	if input.ChapterID != nil || input.SceneID != nil {
		return "move"
	}
	if input.Tags != nil && input.ContentText == nil {
		return "tag"
	}
	return "update"
}

func reorderReason(blockID string, move *MoveBlockInput) string {
	if move != nil && blockID == move.BlockID {
		return "move"
	}
	return "update"
}

func normalizeScope(scope Scope) Scope {
	scope.TenantID = strings.TrimSpace(scope.TenantID)
	scope.ProjectID = strings.TrimSpace(scope.ProjectID)
	scope.ActorUserID = strings.TrimSpace(scope.ActorUserID)
	scope.RequestID = strings.TrimSpace(scope.RequestID)
	return scope
}

func validateScope(scope Scope, requireRequest bool) error {
	if scope.TenantID == "" || scope.ProjectID == "" || scope.ActorUserID == "" || (requireRequest && scope.RequestID == "") {
		return validation("tenant_id, project_id, actor_user_id, and request_id are required")
	}
	return nil
}

func validateMutation(scope Scope, blockID string, expectedVersion int) error {
	if err := validateScope(scope, true); err != nil || strings.TrimSpace(blockID) == "" || expectedVersion <= 0 {
		return validation("tenant_id, project_id, actor_user_id, request_id, block_id, and expected_version are required")
	}
	return nil
}

func normalizeTags(tags []string) ([]string, error) {
	set := map[string]struct{}{}
	result := make([]string, 0, len(tags))
	for _, tag := range tags {
		tag = strings.TrimSpace(tag)
		if tag == "" {
			return nil, validation("tags must not be blank")
		}
		if _, exists := set[tag]; exists {
			continue
		}
		set[tag] = struct{}{}
		result = append(result, tag)
	}
	sort.Strings(result)
	return result, nil
}

type jsonStringList []string

func (list *jsonStringList) Scan(value any) error {
	var payload []byte
	switch typed := value.(type) {
	case string:
		payload = []byte(typed)
	case []byte:
		payload = typed
	default:
		return errors.New("tags JSON has an unsupported database type")
	}
	return json.Unmarshal(payload, list)
}

func countWords(content string) int {
	count, inToken := 0, false
	for _, r := range content {
		switch {
		case unicode.Is(unicode.Han, r):
			count++
			inToken = false
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			if !inToken {
				count++
				inToken = true
			}
		default:
			inToken = false
		}
	}
	return count
}

func validation(message string) *AppError {
	return &AppError{Code: "VALIDATION_FAILED", Message: message}
}
func notFound(message string) *AppError { return &AppError{Code: "NOT_FOUND", Message: message} }
func versionConflict() *AppError {
	return &AppError{Code: "OPTIMISTIC_CONFLICT", Message: "manuscript block version changed"}
}
func queryFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_QUERY_FAILED", Message: "manuscript workspace query failed"}
}
func mutationFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_MUTATION_FAILED", Message: "manuscript block mutation failed"}
}
func reorderFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_REORDER_FAILED", Message: "manuscript block reorder failed"}
}
func restoreFailed() *AppError {
	return &AppError{Code: "MANUSCRIPT_RESTORE_FAILED", Message: "manuscript block restore failed"}
}
