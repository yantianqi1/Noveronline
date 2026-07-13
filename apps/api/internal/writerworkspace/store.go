package writerworkspace

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

type SQLStore struct{ db *sql.DB }

func NewSQLStore(db *sql.DB) *SQLStore { return &SQLStore{db: db} }

func validateScope(s Scope) error {
	if strings.TrimSpace(s.TenantID) == "" || strings.TrimSpace(s.ProjectID) == "" {
		return coded(CodeValidationFailed, "tenant and project are required")
	}
	return nil
}
func stableDBError() error { return coded(CodeQueryFailed, "writer workspace query failed") }
func notFound() error      { return coded(CodeNotFound, "writer workspace resource not found") }
func conflict() error      { return coded(CodeConflict, "writer workspace version conflict") }

func (s *SQLStore) tx(ctx context.Context, scope Scope, fn func(*sql.Tx) error) error {
	if err := validateScope(scope); err != nil {
		return err
	}
	return s.tenantTx(ctx, scope, fn)
}

func (s *SQLStore) tenantTx(ctx context.Context, scope Scope, fn func(*sql.Tx) error) error {
	if strings.TrimSpace(scope.TenantID) == "" {
		return coded(CodeValidationFailed, "tenant is required")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return stableDBError()
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `SELECT app_set_tenant_context($1::uuid, NULLIF($2,'')::uuid, false)`, scope.TenantID, scope.ActorUserID); err != nil {
		return stableDBError()
	}
	if err = fn(tx); err != nil {
		return err
	}
	if err = tx.Commit(); err != nil {
		return stableDBError()
	}
	return nil
}

const chapterColumns = `chapter_id::text, project_id::text, chapter_order, title, status, optimistic_version, created_at, updated_at`

func scanChapter(row interface{ Scan(...any) error }) (Chapter, error) {
	var r Chapter
	err := row.Scan(&r.ChapterID, &r.ProjectID, &r.Order, &r.Title, &r.Status, &r.Version, &r.CreatedAt, &r.UpdatedAt)
	return r, err
}
func scanPrivateChapter(row interface{ Scan(...any) error }) (Chapter, error) {
	var r Chapter
	var p PrivateFields
	err := row.Scan(&r.ChapterID, &r.ProjectID, &r.Order, &r.Title, &r.Status, &r.Version, &r.CreatedAt, &r.UpdatedAt, &p.Brief, &p.Outline, &p.Content)
	r.Private = &p
	return r, err
}

func (s *SQLStore) ListChapters(ctx context.Context, scope Scope) (out []Chapter, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+chapterColumns+` FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND status<>'archived' ORDER BY chapter_order`, scope.TenantID, scope.ProjectID)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanChapter(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		if rows.Err() != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) CreateChapter(ctx context.Context, in CreateChapterInput) (out Chapter, err error) {
	if strings.TrimSpace(in.Title) == "" {
		return out, coded(CodeValidationFailed, "chapter title is required")
	}
	if in.Status == "" {
		in.Status = "planned"
	}
	err = s.tx(ctx, in.Scope, func(tx *sql.Tx) error {
		if e := lockWriterProject(ctx, tx, in.Scope); e != nil {
			return e
		}
		order := 0
		if in.Order != nil {
			order = *in.Order
		} else if e := tx.QueryRowContext(ctx, `SELECT COALESCE(MAX(chapter_order)+1,0) FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND status<>'archived'`, in.Scope.TenantID, in.Scope.ProjectID).Scan(&order); e != nil {
			return stableDBError()
		}
		row := tx.QueryRowContext(ctx, `INSERT INTO chapters(tenant_id,project_id,chapter_order,title,status,brief,outline,content_text,created_by,updated_by) VALUES($1,$2,$3,$4,$5,NULLIF($6,''),NULLIF($7,''),NULLIF($8,''),NULLIF($9,'')::uuid,NULLIF($9,'')::uuid) RETURNING `+chapterColumns, in.Scope.TenantID, in.Scope.ProjectID, order, in.Title, in.Status, in.Brief, in.Outline, in.Content, in.Scope.ActorUserID)
		var e error
		out, e = scanChapter(row)
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) GetChapter(ctx context.Context, scope Scope, id string, private bool) (out Chapter, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		var e error
		if private {
			out, e = scanPrivateChapter(tx.QueryRowContext(ctx, `SELECT `+chapterColumns+`,COALESCE(brief,''),COALESCE(outline,''),COALESCE(content_text,'') FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND status<>'archived'`, scope.TenantID, scope.ProjectID, id))
		} else {
			out, e = scanChapter(tx.QueryRowContext(ctx, `SELECT `+chapterColumns+` FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND status<>'archived'`, scope.TenantID, scope.ProjectID, id))
		}
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}

func snapshotChapter(ctx context.Context, tx *sql.Tx, scope Scope, id, kind string, expected int64) error {
	res, err := tx.ExecContext(ctx, `INSERT INTO chapter_versions(tenant_id,project_id,chapter_id,version_number,title,status,brief,outline,content_text,change_kind,created_by) SELECT tenant_id,project_id,chapter_id,optimistic_version,title,status,brief,outline,content_text,$5,NULLIF($6,'')::uuid FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND optimistic_version=$4 AND status<>'archived'`, scope.TenantID, scope.ProjectID, id, expected, kind, scope.ActorUserID)
	if err != nil {
		return stableDBError()
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return conflict()
	}
	return nil
}
func coalescePatch(v *string) any {
	if v == nil {
		return nil
	}
	return *v
}
func (s *SQLStore) UpdateChapter(ctx context.Context, scope Scope, id string, p ChapterPatch) (out Chapter, err error) {
	if p.ExpectedVersion <= 0 {
		return out, coded(CodeValidationFailed, "expected_version is required")
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		if e := snapshotChapter(ctx, tx, scope, id, "update", p.ExpectedVersion); e != nil {
			return e
		}
		row := tx.QueryRowContext(ctx, `UPDATE chapters SET title=COALESCE(NULLIF($5,''),title),status=COALESCE(NULLIF($6,''),status),brief=CASE WHEN $7::boolean THEN $8 ELSE brief END,outline=CASE WHEN $9::boolean THEN $10 ELSE outline END,content_text=CASE WHEN $11::boolean THEN $12 ELSE content_text END,optimistic_version=optimistic_version+1,updated_by=NULLIF($4,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND optimistic_version=$13 RETURNING `+chapterColumns, scope.TenantID, scope.ProjectID, id, scope.ActorUserID, coalescePatch(p.Title), coalescePatch(p.Status), p.Brief != nil, coalescePatch(p.Brief), p.Outline != nil, coalescePatch(p.Outline), p.Content != nil, coalescePatch(p.Content), p.ExpectedVersion)
		var e error
		out, e = scanChapter(row)
		if e == sql.ErrNoRows {
			return conflict()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) DeleteChapter(ctx context.Context, scope Scope, id string, expected int64) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error {
		if e := snapshotChapter(ctx, tx, scope, id, "delete", expected); e != nil {
			return e
		}
		res, e := tx.ExecContext(ctx, `UPDATE chapters SET status='archived',optimistic_version=optimistic_version+1,updated_by=NULLIF($4,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND optimistic_version=$5`, scope.TenantID, scope.ProjectID, id, scope.ActorUserID, expected)
		if e != nil {
			return stableDBError()
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return conflict()
		}
		return nil
	})
}

func reorder(ctx context.Context, tx *sql.Tx, scope Scope, table, parentColumn, parentID, idColumn string, ids []string) error {
	if len(ids) == 0 {
		return coded(CodeReorderInvalid, "complete ordered ids are required")
	}
	seen := map[string]bool{}
	for _, id := range ids {
		if id == "" || seen[id] {
			return coded(CodeReorderInvalid, "ordered ids must be unique")
		}
		seen[id] = true
	}
	if err := lockWriterProject(ctx, tx, scope); err != nil {
		return err
	}
	where := `tenant_id=$1 AND project_id=$2 AND status<>'archived'`
	args := []any{scope.TenantID, scope.ProjectID}
	if parentColumn != "" {
		where += ` AND ` + parentColumn + `=$3`
		args = append(args, parentID)
	}
	rows, e := tx.QueryContext(ctx, fmt.Sprintf(`SELECT %s::text FROM %s WHERE %s FOR UPDATE`, idColumn, table, where), args...)
	if e != nil {
		return stableDBError()
	}
	actual := map[string]bool{}
	for rows.Next() {
		var id string
		if rows.Scan(&id) != nil {
			rows.Close()
			return stableDBError()
		}
		actual[id] = true
	}
	if rows.Close() != nil || rows.Err() != nil {
		return stableDBError()
	}
	if len(actual) != len(ids) {
		return coded(CodeReorderInvalid, "ordered ids must exactly match the parent collection")
	}
	for _, id := range ids {
		if !actual[id] {
			return coded(CodeReorderInvalid, "ordered ids must exactly match the parent collection")
		}
	}
	if _, e = tx.ExecContext(ctx, `SET CONSTRAINTS ALL DEFERRED`); e != nil {
		return stableDBError()
	}
	orderColumn, ok := map[string]string{"chapters": "chapter_order", "scenes": "scene_order"}[table]
	if !ok {
		return stableDBError()
	}
	var maxOrder int
	if e = tx.QueryRowContext(ctx, fmt.Sprintf(`SELECT COALESCE(MAX(%s), -1) FROM %s WHERE %s`, orderColumn, table, where), args...).Scan(&maxOrder); e != nil {
		return stableDBError()
	}
	temporaryBase := maxOrder + len(ids) + 1
	for pos, id := range ids {
		q := fmt.Sprintf(`UPDATE %s SET %s=$1,updated_at=now() WHERE tenant_id=$2 AND project_id=$3 AND %s=$4 AND status<>'archived'`, table, orderColumn, idColumn)
		if _, e = tx.ExecContext(ctx, q, temporaryBase+pos, scope.TenantID, scope.ProjectID, id); e != nil {
			return stableDBError()
		}
	}
	for pos, id := range ids {
		q := fmt.Sprintf(`UPDATE %s SET %s=$1,updated_at=now() WHERE tenant_id=$2 AND project_id=$3 AND %s=$4 AND status<>'archived'`, table, orderColumn, idColumn)
		if _, e = tx.ExecContext(ctx, q, pos, scope.TenantID, scope.ProjectID, id); e != nil {
			return stableDBError()
		}
	}
	return nil
}

func lockWriterProject(ctx context.Context, tx *sql.Tx, scope Scope) error {
	var projectID string
	err := tx.QueryRowContext(ctx, `SELECT project_id::text FROM projects WHERE tenant_id=$1 AND project_id=$2 FOR UPDATE`, scope.TenantID, scope.ProjectID).Scan(&projectID)
	if err == sql.ErrNoRows {
		return notFound()
	}
	if err != nil {
		return stableDBError()
	}
	return nil
}
func (s *SQLStore) ReorderChapters(ctx context.Context, scope Scope, ids []string) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error { return reorder(ctx, tx, scope, "chapters", "", "", "chapter_id", ids) })
}

func (s *SQLStore) ListChapterVersions(ctx context.Context, scope Scope, id string, private bool) (out []Version, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		cols := `chapter_version_id::text,chapter_id::text,version_number,title,status,change_kind,created_at`
		if private {
			cols += `,COALESCE(brief,''),COALESCE(outline,''),COALESCE(content_text,'')`
		}
		rows, e := tx.QueryContext(ctx, `SELECT `+cols+` FROM chapter_versions WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 ORDER BY version_number DESC`, scope.TenantID, scope.ProjectID, id)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			var v Version
			if private {
				v.Private = &PrivateFields{}
				e = rows.Scan(&v.VersionID, &v.ParentID, &v.Version, &v.Title, &v.Status, &v.ChangeKind, &v.CreatedAt, &v.Private.Brief, &v.Private.Outline, &v.Private.Content)
			} else {
				e = rows.Scan(&v.VersionID, &v.ParentID, &v.Version, &v.Title, &v.Status, &v.ChangeKind, &v.CreatedAt)
			}
			if e != nil {
				return stableDBError()
			}
			out = append(out, v)
		}
		if rows.Err() != nil {
			return stableDBError()
		}
		return nil
	})
	return
}

const sceneColumns = `scene_id::text,chapter_id::text,project_id::text,scene_order,title,status,optimistic_version,created_at,updated_at`
const sceneColumnsAliased = `s.scene_id::text,s.chapter_id::text,s.project_id::text,s.scene_order,s.title,s.status,s.optimistic_version,s.created_at,s.updated_at`

func scanScene(row interface{ Scan(...any) error }) (Scene, error) {
	var r Scene
	e := row.Scan(&r.SceneID, &r.ChapterID, &r.ProjectID, &r.Order, &r.Title, &r.Status, &r.Version, &r.CreatedAt, &r.UpdatedAt)
	return r, e
}
func scanPrivateScene(row interface{ Scan(...any) error }) (Scene, error) {
	var r Scene
	var p PrivateFields
	e := row.Scan(&r.SceneID, &r.ChapterID, &r.ProjectID, &r.Order, &r.Title, &r.Status, &r.Version, &r.CreatedAt, &r.UpdatedAt, &p.Brief, &p.Outline, &p.Content)
	r.Private = &p
	return r, e
}
func (s *SQLStore) ListScenes(ctx context.Context, scope Scope, chapterID string) (out []Scene, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+sceneColumnsAliased+` FROM scenes s JOIN chapters c ON c.tenant_id=s.tenant_id AND c.project_id=s.project_id AND c.chapter_id=s.chapter_id WHERE s.tenant_id=$1 AND s.project_id=$2 AND s.chapter_id=$3 AND s.status<>'archived' AND c.status<>'archived' ORDER BY s.scene_order`, scope.TenantID, scope.ProjectID, chapterID)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanScene(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return rows.Err()
	})
	if err != nil && ErrorCode(err) == CodeQueryFailed {
		err = stableDBError()
	}
	return
}
func (s *SQLStore) CreateScene(ctx context.Context, in CreateSceneInput) (out Scene, err error) {
	if in.ChapterID == "" || strings.TrimSpace(in.Title) == "" {
		return out, coded(CodeValidationFailed, "chapter and scene title are required")
	}
	if in.Status == "" {
		in.Status = "planned"
	}
	err = s.tx(ctx, in.Scope, func(tx *sql.Tx) error {
		if e := lockWriterProject(ctx, tx, in.Scope); e != nil {
			return e
		}
		order := 0
		if in.Order != nil {
			order = *in.Order
		} else if e := tx.QueryRowContext(ctx, `SELECT COALESCE(MAX(scene_order)+1,0) FROM scenes WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND status<>'archived'`, in.Scope.TenantID, in.Scope.ProjectID, in.ChapterID).Scan(&order); e != nil {
			return stableDBError()
		}
		row := tx.QueryRowContext(ctx, `INSERT INTO scenes(tenant_id,project_id,chapter_id,scene_order,title,status,brief,outline,content_text,created_by,updated_by) SELECT $1,$2,$3,$4,$5,$6,NULLIF($7,''),NULLIF($8,''),NULLIF($9,''),NULLIF($10,'')::uuid,NULLIF($10,'')::uuid FROM chapters WHERE tenant_id=$1 AND project_id=$2 AND chapter_id=$3 AND status<>'archived' RETURNING `+sceneColumns, in.Scope.TenantID, in.Scope.ProjectID, in.ChapterID, order, in.Title, in.Status, in.Brief, in.Outline, in.Content, in.Scope.ActorUserID)
		var e error
		out, e = scanScene(row)
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) GetScene(ctx context.Context, scope Scope, id string, private bool) (out Scene, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		var e error
		if private {
			out, e = scanPrivateScene(tx.QueryRowContext(ctx, `SELECT s.scene_id::text,s.chapter_id::text,s.project_id::text,s.scene_order,s.title,s.status,s.optimistic_version,s.created_at,s.updated_at,COALESCE(s.brief,''),COALESCE(s.outline,''),COALESCE(s.content_text,'') FROM scenes s JOIN chapters c ON c.tenant_id=s.tenant_id AND c.project_id=s.project_id AND c.chapter_id=s.chapter_id WHERE s.tenant_id=$1 AND s.project_id=$2 AND s.scene_id=$3 AND s.status<>'archived' AND c.status<>'archived'`, scope.TenantID, scope.ProjectID, id))
		} else {
			out, e = scanScene(tx.QueryRowContext(ctx, `SELECT s.scene_id::text,s.chapter_id::text,s.project_id::text,s.scene_order,s.title,s.status,s.optimistic_version,s.created_at,s.updated_at FROM scenes s JOIN chapters c ON c.tenant_id=s.tenant_id AND c.project_id=s.project_id AND c.chapter_id=s.chapter_id WHERE s.tenant_id=$1 AND s.project_id=$2 AND s.scene_id=$3 AND s.status<>'archived' AND c.status<>'archived'`, scope.TenantID, scope.ProjectID, id))
		}
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func snapshotScene(ctx context.Context, tx *sql.Tx, scope Scope, id, kind string, expected int64) error {
	res, e := tx.ExecContext(ctx, `INSERT INTO scene_versions(tenant_id,project_id,scene_id,chapter_id,version_number,title,status,brief,outline,content_text,change_kind,created_by) SELECT tenant_id,project_id,scene_id,chapter_id,optimistic_version,title,status,brief,outline,content_text,$5,NULLIF($6,'')::uuid FROM scenes WHERE tenant_id=$1 AND project_id=$2 AND scene_id=$3 AND optimistic_version=$4 AND status<>'archived'`, scope.TenantID, scope.ProjectID, id, expected, kind, scope.ActorUserID)
	if e != nil {
		return stableDBError()
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return conflict()
	}
	return nil
}
func (s *SQLStore) UpdateScene(ctx context.Context, scope Scope, id string, p ScenePatch) (out Scene, err error) {
	if p.ExpectedVersion <= 0 {
		return out, coded(CodeValidationFailed, "expected_version is required")
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		if e := snapshotScene(ctx, tx, scope, id, "update", p.ExpectedVersion); e != nil {
			return e
		}
		row := tx.QueryRowContext(ctx, `UPDATE scenes SET title=COALESCE(NULLIF($5,''),title),status=COALESCE(NULLIF($6,''),status),brief=CASE WHEN $7::boolean THEN $8 ELSE brief END,outline=CASE WHEN $9::boolean THEN $10 ELSE outline END,content_text=CASE WHEN $11::boolean THEN $12 ELSE content_text END,optimistic_version=optimistic_version+1,updated_by=NULLIF($4,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND scene_id=$3 AND optimistic_version=$13 RETURNING `+sceneColumns, scope.TenantID, scope.ProjectID, id, scope.ActorUserID, coalescePatch(p.Title), coalescePatch(p.Status), p.Brief != nil, coalescePatch(p.Brief), p.Outline != nil, coalescePatch(p.Outline), p.Content != nil, coalescePatch(p.Content), p.ExpectedVersion)
		var e error
		out, e = scanScene(row)
		if e == sql.ErrNoRows {
			return conflict()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) DeleteScene(ctx context.Context, scope Scope, id string, expected int64) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error {
		if e := snapshotScene(ctx, tx, scope, id, "delete", expected); e != nil {
			return e
		}
		res, e := tx.ExecContext(ctx, `UPDATE scenes SET status='archived',optimistic_version=optimistic_version+1,updated_by=NULLIF($4,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND scene_id=$3 AND optimistic_version=$5`, scope.TenantID, scope.ProjectID, id, scope.ActorUserID, expected)
		if e != nil {
			return stableDBError()
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return conflict()
		}
		return nil
	})
}
func (s *SQLStore) ReorderScenes(ctx context.Context, scope Scope, chapterID string, ids []string) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error {
		return reorder(ctx, tx, scope, "scenes", "chapter_id", chapterID, "scene_id", ids)
	})
}
func (s *SQLStore) ListSceneVersions(ctx context.Context, scope Scope, id string, private bool) (out []Version, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		cols := `scene_version_id::text,scene_id::text,version_number,title,status,change_kind,created_at`
		if private {
			cols += `,COALESCE(brief,''),COALESCE(outline,''),COALESCE(content_text,'')`
		}
		rows, e := tx.QueryContext(ctx, `SELECT `+cols+` FROM scene_versions WHERE tenant_id=$1 AND project_id=$2 AND scene_id=$3 ORDER BY version_number DESC`, scope.TenantID, scope.ProjectID, id)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			var v Version
			if private {
				v.Private = &PrivateFields{}
				e = rows.Scan(&v.VersionID, &v.ParentID, &v.Version, &v.Title, &v.Status, &v.ChangeKind, &v.CreatedAt, &v.Private.Brief, &v.Private.Outline, &v.Private.Content)
			} else {
				e = rows.Scan(&v.VersionID, &v.ParentID, &v.Version, &v.Title, &v.Status, &v.ChangeKind, &v.CreatedAt)
			}
			if e != nil {
				return stableDBError()
			}
			out = append(out, v)
		}
		if rows.Err() != nil {
			return stableDBError()
		}
		return nil
	})
	return
}

func scanOutline(row interface{ Scan(...any) error }) (OutlineVersion, error) {
	var r OutlineVersion
	e := row.Scan(&r.OutlineVersionID, &r.ProjectID, &r.ScopeType, &r.ScopeID, &r.Version, &r.Lifecycle, &r.Title, &r.OutlineText, &r.RestoredFromVersionID, &r.CreatedAt)
	return r, e
}

const outlineCols = `outline_version_id::text,project_id::text,scope_type,COALESCE(scope_id::text,''),version_number,lifecycle,title,outline_text,COALESCE(restored_from_version_id::text,''),created_at`

func (s *SQLStore) ListOutlines(ctx context.Context, scope Scope, kind, id string) (out []OutlineVersion, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+outlineCols+` FROM outline_versions WHERE tenant_id=$1 AND project_id=$2 AND scope_type=$3 AND scope_id IS NOT DISTINCT FROM NULLIF($4,'')::uuid ORDER BY version_number DESC`, scope.TenantID, scope.ProjectID, kind, id)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanOutline(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return nil
	})
	return
}
func validOutlineScope(kind, id string) bool {
	return kind == "project" && id == "" || (kind == "chapter" || kind == "scene") && id != ""
}
func (s *SQLStore) CreateOutline(ctx context.Context, in CreateOutlineInput) (out OutlineVersion, err error) {
	if !validOutlineScope(in.ScopeType, in.ScopeID) || strings.TrimSpace(in.Title) == "" {
		return out, coded(CodeValidationFailed, "invalid outline scope or title")
	}
	if in.Lifecycle == "" {
		in.Lifecycle = "candidate"
	}
	err = s.tx(ctx, in.Scope, func(tx *sql.Tx) error {
		if in.Lifecycle == "active" {
			if _, e := tx.ExecContext(ctx, `UPDATE outline_versions SET lifecycle='superseded' WHERE tenant_id=$1 AND project_id=$2 AND scope_type=$3 AND scope_id IS NOT DISTINCT FROM NULLIF($4,'')::uuid AND lifecycle='active'`, in.Scope.TenantID, in.Scope.ProjectID, in.ScopeType, in.ScopeID); e != nil {
				return stableDBError()
			}
		}
		row := tx.QueryRowContext(ctx, `INSERT INTO outline_versions(tenant_id,project_id,scope_type,scope_id,version_number,lifecycle,title,outline_text,created_by) SELECT $1,$2,$3,NULLIF($4,'')::uuid,COALESCE(MAX(version_number),0)+1,$5,$6,$7,NULLIF($8,'')::uuid FROM outline_versions WHERE tenant_id=$1 AND project_id=$2 AND scope_type=$3 AND scope_id IS NOT DISTINCT FROM NULLIF($4,'')::uuid RETURNING `+outlineCols, in.Scope.TenantID, in.Scope.ProjectID, in.ScopeType, in.ScopeID, in.Lifecycle, in.Title, in.OutlineText, in.Scope.ActorUserID)
		var e error
		out, e = scanOutline(row)
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) RestoreOutline(ctx context.Context, scope Scope, id string) (out OutlineVersion, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		var src OutlineVersion
		var e error
		src, e = scanOutline(tx.QueryRowContext(ctx, `SELECT `+outlineCols+` FROM outline_versions WHERE tenant_id=$1 AND project_id=$2 AND outline_version_id=$3 FOR UPDATE`, scope.TenantID, scope.ProjectID, id))
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		var restored bool
		if e = tx.QueryRowContext(ctx, `SELECT EXISTS(SELECT 1 FROM outline_versions WHERE tenant_id=$1 AND project_id=$2 AND restored_from_version_id=$3)`, scope.TenantID, scope.ProjectID, id).Scan(&restored); e != nil {
			return stableDBError()
		}
		if restored {
			return conflict()
		}
		if _, e = tx.ExecContext(ctx, `UPDATE outline_versions SET lifecycle='superseded' WHERE tenant_id=$1 AND project_id=$2 AND scope_type=$3 AND scope_id IS NOT DISTINCT FROM NULLIF($4,'')::uuid AND lifecycle='active'`, scope.TenantID, scope.ProjectID, src.ScopeType, src.ScopeID); e != nil {
			return stableDBError()
		}
		row := tx.QueryRowContext(ctx, `INSERT INTO outline_versions(tenant_id,project_id,scope_type,scope_id,version_number,lifecycle,title,outline_text,restored_from_version_id,created_by) SELECT tenant_id,project_id,scope_type,scope_id,(SELECT COALESCE(MAX(v.version_number),0)+1 FROM outline_versions v WHERE v.tenant_id=$1 AND v.project_id=$2 AND v.scope_type=outline_versions.scope_type AND v.scope_id IS NOT DISTINCT FROM outline_versions.scope_id),'active',title,outline_text,outline_version_id,NULLIF($4,'')::uuid FROM outline_versions WHERE tenant_id=$1 AND project_id=$2 AND outline_version_id=$3 RETURNING `+outlineCols, scope.TenantID, scope.ProjectID, id, scope.ActorUserID)
		out, e = scanOutline(row)
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}

const planCols = `book_plan_id::text,project_id::text,title,status,COALESCE(premise,''),target_chapter_count,planning_jsonb::text,optimistic_version,COALESCE(last_run_id::text,''),COALESCE(last_run_status,''),created_at,updated_at`

func scanPlan(row interface{ Scan(...any) error }) (BookPlan, error) {
	var r BookPlan
	e := row.Scan(&r.BookPlanID, &r.ProjectID, &r.Title, &r.Status, &r.Premise, &r.TargetChapterCount, &r.PlanningJSON, &r.Version, &r.LastRunID, &r.LastRunStatus, &r.CreatedAt, &r.UpdatedAt)
	return r, e
}
func (s *SQLStore) ListBookPlans(ctx context.Context, scope Scope) (out []BookPlan, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+planCols+` FROM book_plans WHERE tenant_id=$1 AND project_id=$2 ORDER BY updated_at DESC`, scope.TenantID, scope.ProjectID)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanPlan(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return nil
	})
	return
}
func (s *SQLStore) GetBookPlan(ctx context.Context, scope Scope, id string) (out BookPlan, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		var e error
		out, e = scanPlan(tx.QueryRowContext(ctx, `SELECT `+planCols+` FROM book_plans WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3`, scope.TenantID, scope.ProjectID, id))
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func validJSON(raw string) string {
	if raw == "" {
		return `{}`
	}
	if json.Valid([]byte(raw)) {
		return raw
	}
	return ""
}
func (s *SQLStore) CreateBookPlan(ctx context.Context, scope Scope, p BookPlan) (out BookPlan, err error) {
	j := validJSON(p.PlanningJSON)
	if strings.TrimSpace(p.Title) == "" || j == "" {
		return out, coded(CodeValidationFailed, "book plan title and valid planning are required")
	}
	if p.Status == "" {
		p.Status = "draft"
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		row := tx.QueryRowContext(ctx, `INSERT INTO book_plans(tenant_id,project_id,title,status,premise,target_chapter_count,planning_jsonb,created_by,updated_by) VALUES($1,$2,$3,$4,NULLIF($5,''),$6,$7::jsonb,NULLIF($8,'')::uuid,NULLIF($8,'')::uuid) RETURNING `+planCols, scope.TenantID, scope.ProjectID, p.Title, p.Status, p.Premise, p.TargetChapterCount, j, scope.ActorUserID)
		var e error
		out, e = scanPlan(row)
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) UpdateBookPlan(ctx context.Context, scope Scope, id string, p BookPlanPatch) (out BookPlan, err error) {
	if p.ExpectedVersion <= 0 {
		return out, coded(CodeValidationFailed, "expected_version is required")
	}
	if p.PlanningJSON != nil && validJSON(*p.PlanningJSON) == "" {
		return out, coded(CodeValidationFailed, "planning must be valid JSON")
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		row := tx.QueryRowContext(ctx, `UPDATE book_plans SET title=COALESCE(NULLIF($5,''),title),status=COALESCE(NULLIF($6,''),status),premise=CASE WHEN $7::boolean THEN $8 ELSE premise END,target_chapter_count=CASE WHEN $9::boolean THEN $10 ELSE target_chapter_count END,planning_jsonb=CASE WHEN $11::boolean THEN $12::jsonb ELSE planning_jsonb END,optimistic_version=optimistic_version+1,updated_by=NULLIF($4,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 AND optimistic_version=$13 RETURNING `+planCols, scope.TenantID, scope.ProjectID, id, scope.ActorUserID, coalescePatch(p.Title), coalescePatch(p.Status), p.Premise != nil, coalescePatch(p.Premise), p.TargetChapterCount != nil, p.TargetChapterCount, p.PlanningJSON != nil, coalescePatch(p.PlanningJSON), p.ExpectedVersion)
		var e error
		out, e = scanPlan(row)
		if e == sql.ErrNoRows {
			return conflict()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) DeleteBookPlan(ctx context.Context, scope Scope, id string, expected int64) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error {
		res, e := tx.ExecContext(ctx, `DELETE FROM book_plans WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 AND optimistic_version=$4`, scope.TenantID, scope.ProjectID, id, expected)
		if e != nil {
			return stableDBError()
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return conflict()
		}
		return nil
	})
}
func (s *SQLStore) AdmitBookRun(ctx context.Context, scope Scope, id string, in AdmitBookRunInput) (out BookRunAdmission, err error) {
	if in.ExpectedVersion <= 0 || in.RunID == "" || in.Status == "" || in.ItemCount < 0 || in.WarningCount < 0 {
		return out, coded(CodeValidationFailed, "valid expected version and run metadata are required")
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		row := tx.QueryRowContext(ctx, `UPDATE book_plans SET last_run_id=$4,last_run_status=$5,optimistic_version=optimistic_version+1,updated_by=NULLIF($6,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 AND optimistic_version=$7 RETURNING `+planCols, scope.TenantID, scope.ProjectID, id, in.RunID, in.Status, scope.ActorUserID, in.ExpectedVersion)
		var e error
		out.Plan, e = scanPlan(row)
		if e == sql.ErrNoRows {
			return conflict()
		}
		if e != nil {
			return stableDBError()
		}
		eventRow := tx.QueryRowContext(ctx, `INSERT INTO book_run_events(tenant_id,project_id,book_plan_id,run_id,sequence,event_type,status,item_count,warning_count) SELECT $1,$2,$3,$4,COALESCE(MAX(sequence),0)+1,'planning.admitted',$5,$6,$7 FROM book_run_events WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 RETURNING `+eventCols, scope.TenantID, scope.ProjectID, id, in.RunID, in.Status, in.ItemCount, in.WarningCount)
		out.Event, e = scanEvent(eventRow)
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}

const eventCols = `book_run_event_id::text,book_plan_id::text,COALESCE(run_id::text,''),sequence,event_type,status,item_count,warning_count,created_at`

func scanEvent(row interface{ Scan(...any) error }) (BookRunEvent, error) {
	var r BookRunEvent
	e := row.Scan(&r.EventID, &r.BookPlanID, &r.RunID, &r.Sequence, &r.EventType, &r.Status, &r.ItemCount, &r.WarningCount, &r.CreatedAt)
	return r, e
}
func (s *SQLStore) AppendBookRunEvent(ctx context.Context, scope Scope, e BookRunEvent) (out BookRunEvent, err error) {
	if e.BookPlanID == "" || e.EventType == "" {
		return out, coded(CodeValidationFailed, "book plan and event type are required")
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		row := tx.QueryRowContext(ctx, `INSERT INTO book_run_events(tenant_id,project_id,book_plan_id,run_id,sequence,event_type,status,item_count,warning_count) SELECT $1,$2,$3,NULLIF($4,'')::uuid,COALESCE(MAX(sequence),0)+1,$5,$6,$7,$8 FROM book_run_events WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 RETURNING `+eventCols, scope.TenantID, scope.ProjectID, e.BookPlanID, e.RunID, e.EventType, e.Status, e.ItemCount, e.WarningCount)
		var x error
		out, x = scanEvent(row)
		if x != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) ListBookRunEvents(ctx context.Context, scope Scope, id string, after int) (out []BookRunEvent, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+eventCols+` FROM book_run_events WHERE tenant_id=$1 AND project_id=$2 AND book_plan_id=$3 AND sequence>$4 ORDER BY sequence LIMIT 200`, scope.TenantID, scope.ProjectID, id, after)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanEvent(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return nil
	})
	return
}

const presetCols = `writer_preset_id::text,COALESCE(project_id::text,''),name,COALESCE(description,''),settings_jsonb::text,enabled,created_at,updated_at`

func scanPreset(row interface{ Scan(...any) error }) (WriterPreset, error) {
	var r WriterPreset
	e := row.Scan(&r.PresetID, &r.ProjectID, &r.Name, &r.Description, &r.SettingsJSON, &r.Enabled, &r.CreatedAt, &r.UpdatedAt)
	if r.ProjectID == "" {
		r.Scope = "tenant"
	} else {
		r.Scope = "project"
	}
	return r, e
}
func (s *SQLStore) ListPresets(ctx context.Context, scope Scope) (out []WriterPreset, err error) {
	err = s.tenantTx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+presetCols+` FROM writer_presets WHERE tenant_id=$1 AND (project_id IS NULL OR project_id=NULLIF($2,'')::uuid) ORDER BY project_id NULLS FIRST,name`, scope.TenantID, scope.ProjectID)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanPreset(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return nil
	})
	return
}
func (s *SQLStore) GetPreset(ctx context.Context, scope Scope, id string) (out WriterPreset, err error) {
	err = s.tenantTx(ctx, scope, func(tx *sql.Tx) error {
		var e error
		out, e = scanPreset(tx.QueryRowContext(ctx, `SELECT `+presetCols+` FROM writer_presets WHERE tenant_id=$1 AND (project_id IS NULL OR project_id=NULLIF($2,'')::uuid) AND writer_preset_id=$3`, scope.TenantID, scope.ProjectID, id))
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func unsafePresetJSON(raw string) bool {
	var v any
	if !json.Valid([]byte(raw)) || json.Unmarshal([]byte(raw), &v) != nil {
		return true
	}
	var walk func(any) bool
	walk = func(x any) bool {
		switch y := x.(type) {
		case map[string]any:
			for k, v := range y {
				n := strings.ToLower(k)
				if strings.Contains(n, "provider") || strings.Contains(n, "credential") || strings.Contains(n, "api_key") || strings.Contains(n, "prompt") {
					return true
				}
				if walk(v) {
					return true
				}
			}
		case []any:
			for _, v := range y {
				if walk(v) {
					return true
				}
			}
		}
		return false
	}
	return walk(v)
}
func (s *SQLStore) UpsertPreset(ctx context.Context, scope Scope, p WriterPreset) (out WriterPreset, err error) {
	if p.Scope == "tenant" {
		p.ProjectID = ""
	} else {
		p.ProjectID = scope.ProjectID
		p.Scope = "project"
	}
	if p.SettingsJSON == "" {
		p.SettingsJSON = `{}`
	}
	if p.Name == "" || unsafePresetJSON(p.SettingsJSON) {
		return out, coded(CodeValidationFailed, "preset settings contain unsupported fields")
	}
	err = s.tenantTx(ctx, scope, func(tx *sql.Tx) error {
		if p.PresetID == "" {
			row := tx.QueryRowContext(ctx, `INSERT INTO writer_presets(tenant_id,project_id,name,description,settings_jsonb,enabled,created_by,updated_by) VALUES($1,NULLIF($2,'')::uuid,$3,NULLIF($4,''),$5::jsonb,$6,NULLIF($7,'')::uuid,NULLIF($7,'')::uuid) RETURNING `+presetCols, scope.TenantID, p.ProjectID, p.Name, p.Description, p.SettingsJSON, p.Enabled, scope.ActorUserID)
			var e error
			out, e = scanPreset(row)
			if e != nil {
				return stableDBError()
			}
			return nil
		}
		row := tx.QueryRowContext(ctx, `UPDATE writer_presets SET name=$4,description=NULLIF($5,''),settings_jsonb=$6::jsonb,enabled=$7,updated_by=NULLIF($8,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id IS NOT DISTINCT FROM NULLIF($2,'')::uuid AND writer_preset_id=$3 RETURNING `+presetCols, scope.TenantID, p.ProjectID, p.PresetID, p.Name, p.Description, p.SettingsJSON, p.Enabled, scope.ActorUserID)
		var e error
		out, e = scanPreset(row)
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) DeletePreset(ctx context.Context, scope Scope, id string) error {
	return s.tenantTx(ctx, scope, func(tx *sql.Tx) error {
		res, e := tx.ExecContext(ctx, `DELETE FROM writer_presets WHERE tenant_id=$1 AND (project_id IS NULL OR project_id=NULLIF($2,'')::uuid) AND writer_preset_id=$3`, scope.TenantID, scope.ProjectID, id)
		if e != nil {
			return stableDBError()
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return notFound()
		}
		return nil
	})
}

const lexCols = `lexicon_entry_id::text,project_id::text,term,category,severity,COALESCE(replacement_guidance,''),enabled,created_at,updated_at`

func scanLex(row interface{ Scan(...any) error }) (ForbiddenEntry, error) {
	var r ForbiddenEntry
	e := row.Scan(&r.EntryID, &r.ProjectID, &r.Term, &r.Category, &r.Severity, &r.ReplacementGuidance, &r.Enabled, &r.CreatedAt, &r.UpdatedAt)
	return r, e
}
func (s *SQLStore) ListLexicon(ctx context.Context, scope Scope) (out []ForbiddenEntry, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		rows, e := tx.QueryContext(ctx, `SELECT `+lexCols+` FROM forbidden_lexicon_entries WHERE tenant_id=$1 AND project_id=$2 ORDER BY category,term`, scope.TenantID, scope.ProjectID)
		if e != nil {
			return stableDBError()
		}
		defer rows.Close()
		for rows.Next() {
			r, e := scanLex(rows)
			if e != nil {
				return stableDBError()
			}
			out = append(out, r)
		}
		return nil
	})
	return
}
func (s *SQLStore) GetLexicon(ctx context.Context, scope Scope, id string) (out ForbiddenEntry, err error) {
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		var e error
		out, e = scanLex(tx.QueryRowContext(ctx, `SELECT `+lexCols+` FROM forbidden_lexicon_entries WHERE tenant_id=$1 AND project_id=$2 AND lexicon_entry_id=$3`, scope.TenantID, scope.ProjectID, id))
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) UpsertLexicon(ctx context.Context, scope Scope, p ForbiddenEntry) (out ForbiddenEntry, err error) {
	if p.Term == "" || p.Category == "" {
		return out, coded(CodeValidationFailed, "term and category are required")
	}
	if p.Severity == "" {
		p.Severity = "warning"
	}
	err = s.tx(ctx, scope, func(tx *sql.Tx) error {
		if p.EntryID == "" {
			row := tx.QueryRowContext(ctx, `INSERT INTO forbidden_lexicon_entries(tenant_id,project_id,term,category,severity,replacement_guidance,enabled,created_by,updated_by) VALUES($1,$2,$3,$4,$5,NULLIF($6,''),$7,NULLIF($8,'')::uuid,NULLIF($8,'')::uuid) RETURNING `+lexCols, scope.TenantID, scope.ProjectID, p.Term, p.Category, p.Severity, p.ReplacementGuidance, p.Enabled, scope.ActorUserID)
			var e error
			out, e = scanLex(row)
			if e != nil {
				return stableDBError()
			}
			return nil
		}
		row := tx.QueryRowContext(ctx, `UPDATE forbidden_lexicon_entries SET term=$4,category=$5,severity=$6,replacement_guidance=NULLIF($7,''),enabled=$8,updated_by=NULLIF($9,'')::uuid,updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND lexicon_entry_id=$3 RETURNING `+lexCols, scope.TenantID, scope.ProjectID, p.EntryID, p.Term, p.Category, p.Severity, p.ReplacementGuidance, p.Enabled, scope.ActorUserID)
		var e error
		out, e = scanLex(row)
		if e == sql.ErrNoRows {
			return notFound()
		}
		if e != nil {
			return stableDBError()
		}
		return nil
	})
	return
}
func (s *SQLStore) DeleteLexicon(ctx context.Context, scope Scope, id string) error {
	return deleteByID(ctx, s, scope, "forbidden_lexicon_entries", "lexicon_entry_id", id)
}
func deleteByID(ctx context.Context, s *SQLStore, scope Scope, table, col, id string) error {
	return s.tx(ctx, scope, func(tx *sql.Tx) error {
		res, e := tx.ExecContext(ctx, fmt.Sprintf(`DELETE FROM %s WHERE tenant_id=$1 AND project_id=$2 AND %s=$3`, table, col), scope.TenantID, scope.ProjectID, id)
		if e != nil {
			return stableDBError()
		}
		n, _ := res.RowsAffected()
		if n != 1 {
			return notFound()
		}
		return nil
	})
}
