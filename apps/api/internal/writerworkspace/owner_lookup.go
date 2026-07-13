package writerworkspace

import (
	"context"
	"database/sql"
	"strings"
)

func (s *SQLStore) LookupResourceOwner(ctx context.Context, input OwnerLookupInput) (ResourceOwner, error) {
	if strings.TrimSpace(input.TenantID) == "" || strings.TrimSpace(input.ActorUserID) == "" || strings.TrimSpace(input.ResourceID) == "" {
		return ResourceOwner{}, coded(CodeValidationFailed, "tenant, actor, and resource are required")
	}
	query, nullableProject := ownerLookupQuery(input.Kind)
	if query == "" {
		return ResourceOwner{}, coded(CodeValidationFailed, "unsupported writer workspace resource")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return ResourceOwner{}, stableDBError()
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `SELECT app_set_tenant_context($1::uuid, $2::uuid, false)`, input.TenantID, input.ActorUserID); err != nil {
		return ResourceOwner{}, stableDBError()
	}
	owner := ResourceOwner{}
	if nullableProject {
		var projectID sql.NullString
		err = tx.QueryRowContext(ctx, query, input.TenantID, input.ResourceID).Scan(&projectID)
		owner.ProjectID = projectID.String
		owner.TenantScoped = !projectID.Valid
	} else {
		err = tx.QueryRowContext(ctx, query, input.TenantID, input.ResourceID).Scan(&owner.ProjectID)
	}
	if err == sql.ErrNoRows {
		return ResourceOwner{}, notFound()
	}
	if err != nil {
		return ResourceOwner{}, stableDBError()
	}
	if err = tx.Commit(); err != nil {
		return ResourceOwner{}, stableDBError()
	}
	return owner, nil
}

func ownerLookupQuery(kind ResourceKind) (string, bool) {
	switch kind {
	case ResourceChapter:
		return `SELECT project_id::text FROM chapters WHERE tenant_id=$1 AND chapter_id=$2`, false
	case ResourceScene:
		return `SELECT project_id::text FROM scenes WHERE tenant_id=$1 AND scene_id=$2`, false
	case ResourceOutline:
		return `SELECT project_id::text FROM outline_versions WHERE tenant_id=$1 AND outline_version_id=$2`, false
	case ResourceBookPlan:
		return `SELECT project_id::text FROM book_plans WHERE tenant_id=$1 AND book_plan_id=$2`, false
	case ResourceWriterPreset:
		return `SELECT project_id::text FROM writer_presets WHERE tenant_id=$1 AND writer_preset_id=$2`, true
	case ResourceLexiconEntry:
		return `SELECT project_id::text FROM forbidden_lexicon_entries WHERE tenant_id=$1 AND lexicon_entry_id=$2`, false
	default:
		return "", false
	}
}
