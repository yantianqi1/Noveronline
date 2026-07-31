package assetcatalog

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
)

func scanCollection(row interface{ Scan(...any) error }) (Collection, error) {
	var c Collection
	var metadata string
	if err := row.Scan(&c.CollectionID, &c.ProjectID, &c.Title, &c.Summary, &c.Lifecycle, &metadata, &c.CreatedAt, &c.UpdatedAt); err != nil {
		if err == sql.ErrNoRows {
			return Collection{}, ErrNotFound
		}
		return Collection{}, err
	}
	c.Metadata = map[string]any{}
	_ = json.Unmarshal([]byte(metadata), &c.Metadata)
	c.Items = []CollectionItem{}
	return c, nil
}

func scanCollectionWithItems(row interface{ Scan(...any) error }) (Collection, error) {
	var c Collection
	var metadata, itemsJSON string
	if err := row.Scan(&c.CollectionID, &c.ProjectID, &c.Title, &c.Summary, &c.Lifecycle, &metadata, &itemsJSON, &c.CreatedAt, &c.UpdatedAt); err != nil {
		if err == sql.ErrNoRows {
			return Collection{}, ErrNotFound
		}
		return Collection{}, err
	}
	c.Metadata = map[string]any{}
	if err := json.Unmarshal([]byte(metadata), &c.Metadata); err != nil {
		return Collection{}, err
	}
	c.Items = []CollectionItem{}
	if err := json.Unmarshal([]byte(itemsJSON), &c.Items); err != nil {
		return Collection{}, err
	}
	return c, nil
}

const collectionSelect = `SELECT collection_id::text,project_id::text,title,summary,lifecycle,metadata_jsonb::text,created_at,updated_at FROM asset_collections WHERE tenant_id=$1 AND project_id=$2`

func loadCollection(ctx context.Context, tx *sql.Tx, scope RequestScope, id string) (Collection, error) {
	c, err := scanCollection(tx.QueryRowContext(ctx, collectionSelect+` AND collection_id=$3`, scope.TenantID, scope.ProjectID, id))
	if err != nil {
		return Collection{}, err
	}
	rows, err := tx.QueryContext(ctx, `SELECT a.asset_id::text,a.title,a.asset_type,i.position,i.created_at FROM asset_collection_items i JOIN assets a ON a.tenant_id=i.tenant_id AND a.project_id=i.project_id AND a.asset_id=i.asset_id WHERE i.tenant_id=$1 AND i.project_id=$2 AND i.collection_id=$3 ORDER BY i.position,a.asset_id`, scope.TenantID, scope.ProjectID, id)
	if err != nil {
		return Collection{}, err
	}
	defer rows.Close()
	for rows.Next() {
		var item CollectionItem
		if err = rows.Scan(&item.AssetID, &item.Title, &item.AssetType, &item.Position, &item.CreatedAt); err != nil {
			return Collection{}, err
		}
		c.Items = append(c.Items, item)
	}
	if err = rows.Err(); err != nil {
		return Collection{}, err
	}
	return c, nil
}

func (s *SQLStore) ListCollections(ctx context.Context, scope RequestScope) ([]Collection, error) {
	tx, err := s.tenantTx(ctx, scope, true)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	rows, err := tx.QueryContext(ctx, `SELECT
  c.collection_id::text,
  c.project_id::text,
  c.title,
  c.summary,
  c.lifecycle,
  c.metadata_jsonb::text,
  COALESCE(
    jsonb_agg(jsonb_build_object(
      'asset_id', a.asset_id::text,
      'title', a.title,
      'asset_type', a.asset_type,
      'position', i.position,
      'created_at', i.created_at
    ) ORDER BY i.position, a.asset_id) FILTER (WHERE a.asset_id IS NOT NULL),
    '[]'::jsonb
  )::text,
  c.created_at,
  c.updated_at
FROM asset_collections c
LEFT JOIN asset_collection_items i
  ON i.tenant_id = c.tenant_id
 AND i.project_id = c.project_id
 AND i.collection_id = c.collection_id
LEFT JOIN assets a
  ON a.tenant_id = i.tenant_id
 AND a.project_id = i.project_id
 AND a.asset_id = i.asset_id
WHERE c.tenant_id = $1 AND c.project_id = $2
GROUP BY c.collection_id, c.project_id, c.title, c.summary, c.lifecycle,
         c.metadata_jsonb, c.created_at, c.updated_at
ORDER BY c.title, c.collection_id`, scope.TenantID, scope.ProjectID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	collections := []Collection{}
	for rows.Next() {
		c, scanErr := scanCollectionWithItems(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		collections = append(collections, c)
	}
	if err = rows.Err(); err != nil {
		return nil, err
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return collections, nil
}

func validLifecycle(v string) bool {
	switch v {
	case "seed", "candidate", "canon", "material", "simulation", "draft", "manuscript", "archived":
		return true
	}
	return false
}

func normalizeCollectionInput(input CollectionInput) (CollectionInput, error) {
	input.Title = strings.TrimSpace(input.Title)
	if input.Title == "" {
		return input, ErrInvalid
	}
	if input.Lifecycle == "" {
		input.Lifecycle = "material"
	}
	if !validLifecycle(input.Lifecycle) {
		return input, ErrInvalid
	}
	if input.Metadata == nil {
		input.Metadata = map[string]any{}
	}
	return input, nil
}

func (s *SQLStore) CreateCollection(ctx context.Context, scope RequestScope, input CollectionInput) (Collection, error) {
	input, err := normalizeCollectionInput(input)
	if err != nil {
		return Collection{}, err
	}
	raw, err := json.Marshal(input.Metadata)
	if err != nil {
		return Collection{}, ErrInvalid
	}
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Collection{}, err
	}
	defer tx.Rollback()
	var id string
	err = tx.QueryRowContext(ctx, `INSERT INTO asset_collections(tenant_id,project_id,title,summary,lifecycle,metadata_jsonb,created_by) VALUES($1,$2,$3,$4,$5,$6::jsonb,NULLIF($7,'')::uuid) RETURNING collection_id::text`, scope.TenantID, scope.ProjectID, input.Title, input.Summary, input.Lifecycle, string(raw), scope.ActorID).Scan(&id)
	if err != nil {
		return Collection{}, err
	}
	c, err := loadCollection(ctx, tx, scope, id)
	if err != nil {
		return Collection{}, err
	}
	if err = tx.Commit(); err != nil {
		return Collection{}, err
	}
	return c, nil
}

func (s *SQLStore) UpdateCollection(ctx context.Context, scope RequestScope, id string, input CollectionInput) (Collection, error) {
	input, err := normalizeCollectionInput(input)
	if err != nil {
		return Collection{}, err
	}
	raw, err := json.Marshal(input.Metadata)
	if err != nil {
		return Collection{}, ErrInvalid
	}
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Collection{}, err
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `UPDATE asset_collections SET title=$4,summary=$5,lifecycle=$6,metadata_jsonb=$7::jsonb,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3`, scope.TenantID, scope.ProjectID, id, input.Title, input.Summary, input.Lifecycle, string(raw))
	if err != nil {
		return Collection{}, err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return Collection{}, ErrNotFound
	}
	c, err := loadCollection(ctx, tx, scope, id)
	if err != nil {
		return Collection{}, err
	}
	if err = tx.Commit(); err != nil {
		return Collection{}, err
	}
	return c, nil
}

func (s *SQLStore) DeleteCollection(ctx context.Context, scope RequestScope, id string) error {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	result, err := tx.ExecContext(ctx, `DELETE FROM asset_collections WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3`, scope.TenantID, scope.ProjectID, id)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return ErrNotFound
	}
	return tx.Commit()
}

func ensureCollectionAndAsset(ctx context.Context, tx *sql.Tx, scope RequestScope, collectionID, assetID string) error {
	var ok bool
	if err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM asset_collections WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 FOR UPDATE)`, scope.TenantID, scope.ProjectID, collectionID).Scan(&ok); err != nil {
		return err
	}
	if !ok {
		return ErrNotFound
	}
	if err := tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM assets WHERE tenant_id=$1 AND project_id=$2 AND asset_id=$3)`, scope.TenantID, scope.ProjectID, assetID).Scan(&ok); err != nil {
		return err
	}
	if !ok {
		return ErrNotFound
	}
	return nil
}

func (s *SQLStore) AddMembership(ctx context.Context, scope RequestScope, collectionID, assetID string, input MembershipInput) (Collection, error) {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Collection{}, err
	}
	defer tx.Rollback()
	if err = ensureCollectionAndAsset(ctx, tx, scope, collectionID, assetID); err != nil {
		return Collection{}, err
	}
	position := 0
	if input.Position == nil {
		if err = tx.QueryRowContext(ctx, `SELECT COALESCE(max(position)+1,0) FROM asset_collection_items WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3`, scope.TenantID, scope.ProjectID, collectionID).Scan(&position); err != nil {
			return Collection{}, err
		}
	} else {
		position = *input.Position
		if position < 0 {
			return Collection{}, ErrInvalid
		}
	}
	if input.Position != nil {
		_, err = tx.ExecContext(ctx, `UPDATE asset_collection_items SET position=position+1 WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 AND position >= $4 AND asset_id<>$5`, scope.TenantID, scope.ProjectID, collectionID, position, assetID)
		if err != nil {
			return Collection{}, err
		}
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO asset_collection_items(tenant_id,project_id,collection_id,asset_id,position,added_by) VALUES($1,$2,$3,$4,$5,NULLIF($6,'')::uuid) ON CONFLICT(tenant_id,project_id,collection_id,asset_id) DO UPDATE SET position=CASE WHEN $7 THEN EXCLUDED.position ELSE asset_collection_items.position END`, scope.TenantID, scope.ProjectID, collectionID, assetID, position, scope.ActorID, input.Position != nil)
	if err != nil {
		return Collection{}, err
	}
	if err = compactPositions(ctx, tx, scope, collectionID); err != nil {
		return Collection{}, err
	}
	c, err := loadCollection(ctx, tx, scope, collectionID)
	if err != nil {
		return Collection{}, err
	}
	if err = tx.Commit(); err != nil {
		return Collection{}, err
	}
	return c, nil
}

func compactPositions(ctx context.Context, tx *sql.Tx, scope RequestScope, collectionID string) error {
	_, err := tx.ExecContext(ctx, `WITH ranked AS (SELECT asset_id,row_number() OVER(ORDER BY position,created_at,asset_id)-1 AS new_position FROM asset_collection_items WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3) UPDATE asset_collection_items i SET position=r.new_position FROM ranked r WHERE i.tenant_id=$1 AND i.project_id=$2 AND i.collection_id=$3 AND i.asset_id=r.asset_id AND i.position<>r.new_position`, scope.TenantID, scope.ProjectID, collectionID)
	return err
}

func (s *SQLStore) RemoveMembership(ctx context.Context, scope RequestScope, collectionID, assetID string) (Collection, error) {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Collection{}, err
	}
	defer tx.Rollback()
	var exists bool
	if err = tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM asset_collections WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 FOR UPDATE)`, scope.TenantID, scope.ProjectID, collectionID).Scan(&exists); err != nil {
		return Collection{}, err
	}
	if !exists {
		return Collection{}, ErrNotFound
	}
	_, err = tx.ExecContext(ctx, `DELETE FROM asset_collection_items WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 AND asset_id=$4`, scope.TenantID, scope.ProjectID, collectionID, assetID)
	if err != nil {
		return Collection{}, err
	}
	if err = compactPositions(ctx, tx, scope, collectionID); err != nil {
		return Collection{}, err
	}
	c, err := loadCollection(ctx, tx, scope, collectionID)
	if err != nil {
		return Collection{}, err
	}
	if err = tx.Commit(); err != nil {
		return Collection{}, err
	}
	return c, nil
}

func (s *SQLStore) ReorderMemberships(ctx context.Context, scope RequestScope, collectionID string, input ReorderInput) (Collection, error) {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Collection{}, err
	}
	defer tx.Rollback()
	var exists bool
	if err = tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM asset_collections WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 FOR UPDATE)`, scope.TenantID, scope.ProjectID, collectionID).Scan(&exists); err != nil {
		return Collection{}, err
	}
	if !exists {
		return Collection{}, ErrNotFound
	}
	rows, err := tx.QueryContext(ctx, `SELECT asset_id::text FROM asset_collection_items WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3`, scope.TenantID, scope.ProjectID, collectionID)
	if err != nil {
		return Collection{}, err
	}
	actual := map[string]bool{}
	for rows.Next() {
		var id string
		if err = rows.Scan(&id); err != nil {
			rows.Close()
			return Collection{}, err
		}
		actual[id] = true
	}
	rows.Close()
	if len(actual) != len(input.AssetIDs) {
		return Collection{}, ErrInvalid
	}
	seen := map[string]bool{}
	for _, id := range input.AssetIDs {
		if !actual[id] || seen[id] {
			return Collection{}, ErrInvalid
		}
		seen[id] = true
	}
	for position, id := range input.AssetIDs {
		if _, err = tx.ExecContext(ctx, `UPDATE asset_collection_items SET position=$5 WHERE tenant_id=$1 AND project_id=$2 AND collection_id=$3 AND asset_id=$4`, scope.TenantID, scope.ProjectID, collectionID, id, position); err != nil {
			return Collection{}, err
		}
	}
	c, err := loadCollection(ctx, tx, scope, collectionID)
	if err != nil {
		return Collection{}, err
	}
	if err = tx.Commit(); err != nil {
		return Collection{}, err
	}
	return c, nil
}
