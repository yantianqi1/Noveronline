package assetcatalog

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

type Store interface {
	GetAsset(context.Context, RequestScope, string, bool) (Asset, error)
	ListVersions(context.Context, RequestScope, string, bool) ([]Version, error)
	UpdateAsset(context.Context, RequestScope, string, AssetPatch) (Asset, error)
	RestoreAsset(context.Context, RequestScope, string, RestoreInput) (Asset, error)
	ListCollections(context.Context, RequestScope) ([]Collection, error)
	CreateCollection(context.Context, RequestScope, CollectionInput) (Collection, error)
	UpdateCollection(context.Context, RequestScope, string, CollectionInput) (Collection, error)
	DeleteCollection(context.Context, RequestScope, string) error
	AddMembership(context.Context, RequestScope, string, string, MembershipInput) (Collection, error)
	RemoveMembership(context.Context, RequestScope, string, string) (Collection, error)
	ReorderMemberships(context.Context, RequestScope, string, ReorderInput) (Collection, error)
}

type SQLStore struct{ db *sql.DB }

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func (s *SQLStore) tenantTx(ctx context.Context, scope RequestScope, readOnly bool) (*sql.Tx, error) {
	if s == nil || s.db == nil {
		return nil, fmt.Errorf("asset catalog database is not configured")
	}
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: readOnly})
	if err != nil {
		return nil, err
	}
	if _, err = tx.ExecContext(ctx, "SELECT set_config('app.current_tenant_id', $1, true), set_config('app.current_user_id', $2, true)", scope.TenantID, scope.ActorID); err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	return tx, nil
}

const assetSelect = `
SELECT a.asset_id::text, a.project_id::text, a.asset_type, a.category, a.lifecycle,
       a.title, a.summary, a.content_text, a.payload_jsonb::text, a.tags_jsonb::text,
       a.source_kind, a.source_ref, a.enabled, a.pinned, a.created_at, a.updated_at,
       COALESCE((SELECT max(v.version_number) + 1 FROM asset_versions v
                 WHERE v.tenant_id=a.tenant_id AND v.project_id=a.project_id AND v.asset_id=a.asset_id), 1)
FROM assets a WHERE a.tenant_id=$1 AND a.project_id=$2 AND a.asset_id=$3`

func scanAsset(row interface{ Scan(...any) error }, includePrivate bool) (Asset, error) {
	var a Asset
	var content, payload, tags sql.NullString
	if err := row.Scan(&a.AssetID, &a.ProjectID, &a.AssetType, &a.Category, &a.Lifecycle,
		&a.Title, &a.Summary, &content, &payload, &tags, &a.Source.Kind, &a.Source.Ref,
		&a.Enabled, &a.Pinned, &a.CreatedAt, &a.UpdatedAt, &a.CurrentVersion); err != nil {
		if err == sql.ErrNoRows {
			return Asset{}, ErrNotFound
		}
		return Asset{}, err
	}
	a.Payload = map[string]any{}
	if payload.Valid {
		_ = json.Unmarshal([]byte(payload.String), &a.Payload)
	}
	a.Tags = []string{}
	if tags.Valid {
		_ = json.Unmarshal([]byte(tags.String), &a.Tags)
	}
	a.Collections = []CollectionRef{}
	if includePrivate {
		a.Private = &PrivateContent{}
		if content.Valid {
			a.Private.ContentText = &content.String
		}
	} else {
		a.Payload = nil
	}
	return a, nil
}

func (s *SQLStore) GetAsset(ctx context.Context, scope RequestScope, assetID string, includePrivate bool) (Asset, error) {
	tx, err := s.tenantTx(ctx, scope, true)
	if err != nil {
		return Asset{}, err
	}
	defer tx.Rollback()
	a, err := scanAsset(tx.QueryRowContext(ctx, assetSelect, scope.TenantID, scope.ProjectID, assetID), includePrivate)
	if err != nil {
		return Asset{}, err
	}
	rows, err := tx.QueryContext(ctx, `SELECT c.collection_id::text,c.title,c.lifecycle,i.position
FROM asset_collection_items i JOIN asset_collections c ON c.tenant_id=i.tenant_id AND c.project_id=i.project_id AND c.collection_id=i.collection_id
WHERE i.tenant_id=$1 AND i.project_id=$2 AND i.asset_id=$3 ORDER BY c.title,c.collection_id`, scope.TenantID, scope.ProjectID, assetID)
	if err != nil {
		return Asset{}, err
	}
	defer rows.Close()
	for rows.Next() {
		var ref CollectionRef
		if err := rows.Scan(&ref.CollectionID, &ref.Title, &ref.Lifecycle, &ref.Position); err != nil {
			return Asset{}, err
		}
		a.Collections = append(a.Collections, ref)
	}
	if err := rows.Err(); err != nil {
		return Asset{}, err
	}
	if err := tx.Commit(); err != nil {
		return Asset{}, err
	}
	return a, nil
}

type snapshotEnvelope struct {
	Schema   int             `json:"_asset_version_schema"`
	Snapshot VersionSnapshot `json:"snapshot"`
}

func envelopeFromAsset(a Asset, content *string) snapshotEnvelope {
	return snapshotEnvelope{Schema: 1, Snapshot: VersionSnapshot{AssetType: a.AssetType, Category: a.Category, Title: a.Title, Summary: a.Summary,
		Payload: a.Payload, Tags: a.Tags, Source: a.Source, Enabled: a.Enabled, Pinned: a.Pinned, ContentText: content}}
}

func decodeVersionPayload(raw string, v Version, includePrivate bool) Version {
	var envelope snapshotEnvelope
	if json.Unmarshal([]byte(raw), &envelope) == nil && envelope.Schema == 1 {
		if !includePrivate {
			envelope.Snapshot.ContentText = nil
		}
		v.Snapshot = &envelope.Snapshot
	}
	return v
}

func (s *SQLStore) ListVersions(ctx context.Context, scope RequestScope, assetID string, includePrivate bool) ([]Version, error) {
	tx, err := s.tenantTx(ctx, scope, true)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	var exists bool
	if err = tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM assets WHERE tenant_id=$1 AND project_id=$2 AND asset_id=$3)`, scope.TenantID, scope.ProjectID, assetID).Scan(&exists); err != nil {
		return nil, err
	}
	if !exists {
		return nil, ErrNotFound
	}
	rows, err := tx.QueryContext(ctx, `SELECT asset_version_id::text,version_number,title,summary,COALESCE(source_kind,''),COALESCE(source_ref,''),created_by::text,created_at,payload_jsonb::text
FROM asset_versions WHERE tenant_id=$1 AND project_id=$2 AND asset_id=$3 ORDER BY version_number DESC`, scope.TenantID, scope.ProjectID, assetID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	versions := []Version{}
	for rows.Next() {
		var v Version
		var raw string
		if err = rows.Scan(&v.VersionID, &v.VersionNumber, &v.Title, &v.Summary, &v.Source.Kind, &v.Source.Ref, &v.CreatedBy, &v.CreatedAt, &raw); err != nil {
			return nil, err
		}
		versions = append(versions, decodeVersionPayload(raw, v, includePrivate))
	}
	if err = rows.Err(); err != nil {
		return nil, err
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return versions, nil
}

func loadLockedAsset(ctx context.Context, tx *sql.Tx, scope RequestScope, assetID string) (Asset, *string, error) {
	a, err := scanAsset(tx.QueryRowContext(ctx, assetSelect+" FOR UPDATE", scope.TenantID, scope.ProjectID, assetID), true)
	if err != nil {
		return Asset{}, nil, err
	}
	var content *string
	if a.Private != nil {
		content = a.Private.ContentText
	}
	a.Private = nil
	return a, content, nil
}

func writeSnapshot(ctx context.Context, tx *sql.Tx, scope RequestScope, a Asset, content *string) error {
	raw, err := json.Marshal(envelopeFromAsset(a, content))
	if err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO asset_versions(tenant_id,project_id,asset_id,version_number,title,summary,payload_jsonb,source_kind,source_ref,created_by)
VALUES($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,NULLIF($10,'')::uuid)`, scope.TenantID, scope.ProjectID, a.AssetID, a.CurrentVersion, a.Title, a.Summary, string(raw), a.Source.Kind, a.Source.Ref, scope.ActorID)
	return err
}

func applyPatch(a *Asset, content **string, p AssetPatch) {
	if p.Title != nil {
		a.Title = strings.TrimSpace(*p.Title)
	}
	if p.SummaryValue != nil {
		a.Summary = p.SummaryValue
	}
	if p.Category != nil {
		a.Category = p.Category
	}
	if p.Payload != nil {
		a.Payload = p.Payload
	}
	if p.Tags != nil {
		a.Tags = *p.Tags
	}
	if p.SourceKind != nil {
		a.Source.Kind = strings.TrimSpace(*p.SourceKind)
	}
	if p.SourceRef != nil {
		a.Source.Ref = strings.TrimSpace(*p.SourceRef)
	}
	if p.ContentText != nil {
		*content = p.ContentText
	}
	if p.Enabled != nil {
		a.Enabled = *p.Enabled
	}
	if p.Pinned != nil {
		a.Pinned = *p.Pinned
	}
}

func updateAssetRow(ctx context.Context, tx *sql.Tx, scope RequestScope, a Asset, content *string) error {
	payload, _ := json.Marshal(a.Payload)
	tags, _ := json.Marshal(a.Tags)
	_, err := tx.ExecContext(ctx, `UPDATE assets SET title=$4,summary=$5,category=$6,content_text=$7,payload_jsonb=$8::jsonb,tags_jsonb=$9::jsonb,source_kind=$10,source_ref=$11,enabled=$12,pinned=$13,asset_type=$14,updated_at=now()
WHERE tenant_id=$1 AND project_id=$2 AND asset_id=$3`, scope.TenantID, scope.ProjectID, a.AssetID, a.Title, a.Summary, a.Category, content, string(payload), string(tags), a.Source.Kind, a.Source.Ref, a.Enabled, a.Pinned, a.AssetType)
	return err
}

func (s *SQLStore) UpdateAsset(ctx context.Context, scope RequestScope, assetID string, p AssetPatch) (Asset, error) {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Asset{}, err
	}
	defer tx.Rollback()
	a, content, err := loadLockedAsset(ctx, tx, scope, assetID)
	if err != nil {
		return Asset{}, err
	}
	if p.ExpectedVersion != a.CurrentVersion {
		return Asset{}, ErrConflict
	}
	if err = writeSnapshot(ctx, tx, scope, a, content); err != nil {
		return Asset{}, err
	}
	applyPatch(&a, &content, p)
	if a.Title == "" {
		return Asset{}, ErrInvalid
	}
	if err = updateAssetRow(ctx, tx, scope, a, content); err != nil {
		return Asset{}, err
	}
	if err = tx.Commit(); err != nil {
		return Asset{}, err
	}
	return s.GetAsset(ctx, scope, assetID, scope.Can(PermissionReadPrivate))
}

func (s *SQLStore) RestoreAsset(ctx context.Context, scope RequestScope, assetID string, input RestoreInput) (Asset, error) {
	tx, err := s.tenantTx(ctx, scope, false)
	if err != nil {
		return Asset{}, err
	}
	defer tx.Rollback()
	a, content, err := loadLockedAsset(ctx, tx, scope, assetID)
	if err != nil {
		return Asset{}, err
	}
	if input.ExpectedVersion != a.CurrentVersion {
		return Asset{}, ErrConflict
	}
	var raw string
	var legacyTitle *string
	var legacySummary *string
	var sk, sr sql.NullString
	err = tx.QueryRowContext(ctx, `SELECT payload_jsonb::text,title,summary,source_kind,source_ref FROM asset_versions WHERE tenant_id=$1 AND project_id=$2 AND asset_id=$3 AND version_number=$4`, scope.TenantID, scope.ProjectID, assetID, input.VersionNumber).Scan(&raw, &legacyTitle, &legacySummary, &sk, &sr)
	if err == sql.ErrNoRows {
		return Asset{}, ErrNotFound
	}
	if err != nil {
		return Asset{}, err
	}
	var env snapshotEnvelope
	if json.Unmarshal([]byte(raw), &env) != nil || env.Schema != 1 {
		return Asset{}, fmt.Errorf("%w: version snapshot predates restorable schema", ErrInvalid)
	}
	if err = writeSnapshot(ctx, tx, scope, a, content); err != nil {
		return Asset{}, err
	}
	lifecycle := a.Lifecycle
	restored := env.Snapshot
	a.AssetType = restored.AssetType
	a.Category = restored.Category
	a.Title = restored.Title
	a.Summary = restored.Summary
	a.Payload = restored.Payload
	a.Tags = restored.Tags
	a.Source = restored.Source
	a.Enabled = restored.Enabled
	a.Pinned = restored.Pinned
	content = restored.ContentText
	a.Lifecycle = lifecycle
	if err = updateAssetRow(ctx, tx, scope, a, content); err != nil {
		return Asset{}, err
	}
	if err = tx.Commit(); err != nil {
		return Asset{}, err
	}
	return s.GetAsset(ctx, scope, assetID, scope.Can(PermissionReadPrivate))
}
