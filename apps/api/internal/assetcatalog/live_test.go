package assetcatalog

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const (
	liveCatalogTenantA  = "a1000000-0000-4000-8000-000000000001"
	liveCatalogTenantB  = "a1000000-0000-4000-8000-000000000002"
	liveCatalogProjectA = "a2000000-0000-4000-8000-000000000001"
	liveCatalogProjectB = "a2000000-0000-4000-8000-000000000002"
	liveCatalogUser     = "a3000000-0000-4000-8000-000000000001"
	liveCatalogAssetA   = "a4000000-0000-4000-8000-000000000001"
	liveCatalogAssetA2  = "a4000000-0000-4000-8000-000000000002"
	liveCatalogAssetB   = "a4000000-0000-4000-8000-000000000003"
)

func TestLiveAppRoleHandlerVersionRestoreCollectionIsolation(t *testing.T) {
	adminURL := strings.TrimSpace(os.Getenv("MIROFISH_ASSET_CATALOG_LIVE_ADMIN_DATABASE_URL"))
	appURL := strings.TrimSpace(os.Getenv("MIROFISH_ASSET_CATALOG_LIVE_DATABASE_URL"))
	if adminURL == "" || appURL == "" {
		t.Skip("set asset catalog admin/app live database URLs")
	}
	admin, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()
	app, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatal(err)
	}
	defer app.Close()
	cleanupCatalog(t, admin)
	defer cleanupCatalog(t, admin)
	seedCatalog(t, admin)
	h := NewHandler(NewSQLStore(app))
	owner := ownerLiveScope()
	viewer := owner
	viewer.Permissions = map[Permission]bool{}

	public := liveRequestAs(h, http.MethodGet, livePath("/assets/"+liveCatalogAssetA), "", viewer)
	if public.Code != 200 || strings.Contains(public.Body.String(), "private body v1") || strings.Contains(public.Body.String(), `"payload":`) {
		t.Fatalf("public privacy status=%d body=%s", public.Code, public.Body.String())
	}
	private := liveRequestAs(h, http.MethodGet, livePath("/assets/"+liveCatalogAssetA), "", owner)
	if private.Code != 200 || !strings.Contains(private.Body.String(), "private body v1") {
		t.Fatalf("private detail status=%d body=%s", private.Code, private.Body.String())
	}
	denied := liveRequestAs(h, http.MethodPatch, livePath("/assets/"+liveCatalogAssetA), `{"expected_version":1,"title":"denied"}`, viewer)
	if denied.Code != 403 {
		t.Fatalf("viewer mutation status=%d", denied.Code)
	}

	updated := liveRequest(h, http.MethodPatch, livePath("/assets/"+liveCatalogAssetA), `{"expected_version":1,"title":"Rule v2","summary":"second","content_text":"private body v2","tags":["v2"],"pinned":true}`)
	if updated.Code != 200 {
		t.Fatalf("update status=%d body=%s", updated.Code, updated.Body.String())
	}
	conflict := liveRequest(h, http.MethodPatch, livePath("/assets/"+liveCatalogAssetA), `{"expected_version":1,"title":"stale"}`)
	if conflict.Code != 409 {
		t.Fatalf("concurrent conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	var before string
	if err = admin.QueryRow(`SELECT payload_jsonb::text FROM asset_versions WHERE asset_id=$1 AND version_number=1`, liveCatalogAssetA).Scan(&before); err != nil {
		t.Fatal(err)
	}
	restored := liveRequest(h, http.MethodPost, livePath("/assets/"+liveCatalogAssetA+"/restore"), `{"expected_version":2,"version_number":1}`)
	if restored.Code != 200 || !strings.Contains(restored.Body.String(), "Rule v1") || !strings.Contains(restored.Body.String(), `"lifecycle":"canon"`) {
		t.Fatalf("restore status=%d body=%s", restored.Code, restored.Body.String())
	}
	var after string
	if err = admin.QueryRow(`SELECT payload_jsonb::text FROM asset_versions WHERE asset_id=$1 AND version_number=1`, liveCatalogAssetA).Scan(&after); err != nil || before != after {
		t.Fatalf("historical version mutated: err=%v", err)
	}

	created := liveRequest(h, http.MethodPost, livePath("/collections"), `{"title":"Canon Set","lifecycle":"material","metadata":{}}`)
	if created.Code != 201 {
		t.Fatalf("create collection status=%d body=%s", created.Code, created.Body.String())
	}
	var collection Collection
	if err = json.Unmarshal(created.Body.Bytes(), &collection); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{liveCatalogAssetA, liveCatalogAssetA2} {
		response := liveRequest(h, http.MethodPut, livePath("/collections/"+collection.CollectionID+"/items/"+id), `{}`)
		if response.Code != 200 {
			t.Fatalf("add %s: %d %s", id, response.Code, response.Body.String())
		}
	}
	idempotent := liveRequest(h, http.MethodPut, livePath("/collections/"+collection.CollectionID+"/items/"+liveCatalogAssetA), `{}`)
	if idempotent.Code != 200 || strings.Count(idempotent.Body.String(), liveCatalogAssetA) != 1 {
		t.Fatalf("membership not idempotent: %s", idempotent.Body.String())
	}
	reordered := liveRequest(h, http.MethodPut, livePath("/collections/"+collection.CollectionID+"/order"), `{"asset_ids":["`+liveCatalogAssetA2+`","`+liveCatalogAssetA+`"]}`)
	if reordered.Code != 200 || strings.Index(reordered.Body.String(), liveCatalogAssetA2) > strings.Index(reordered.Body.String(), liveCatalogAssetA) {
		t.Fatalf("reorder failed: %s", reordered.Body.String())
	}
	removed := liveRequest(h, http.MethodDelete, livePath("/collections/"+collection.CollectionID+"/items/"+liveCatalogAssetA), "")
	if removed.Code != 200 || strings.Contains(removed.Body.String(), liveCatalogAssetA+`"`) {
		t.Fatalf("remove failed: %s", removed.Body.String())
	}
	deleted := liveRequest(h, http.MethodDelete, livePath("/collections/"+collection.CollectionID), "")
	if deleted.Code != 204 {
		t.Fatalf("delete collection status=%d", deleted.Code)
	}
	var assets int
	if err = admin.QueryRow(`SELECT count(*) FROM assets WHERE asset_id IN ($1,$2)`, liveCatalogAssetA, liveCatalogAssetA2).Scan(&assets); err != nil || assets != 2 {
		t.Fatalf("collection delete affected assets: %d %v", assets, err)
	}

	foreignScope := owner
	foreignScope.ProjectID = liveCatalogProjectB
	hidden := liveRequestAs(h, http.MethodGet, "/v1/projects/"+liveCatalogProjectB+"/asset-catalog/assets/"+liveCatalogAssetA, "", foreignScope)
	if hidden.Code != 404 {
		t.Fatalf("cross-tenant/project asset visible: %d %s", hidden.Code, hidden.Body.String())
	}
}

func ownerLiveScope() RequestScope {
	return RequestScope{ActorID: liveCatalogUser, TenantID: liveCatalogTenantA, ProjectID: liveCatalogProjectA, Permissions: map[Permission]bool{PermissionReadPrivate: true, PermissionMutate: true, PermissionCollections: true}}
}
func livePath(s string) string { return "/v1/projects/" + liveCatalogProjectA + "/asset-catalog" + s }
func liveRequest(h http.Handler, method, path, body string) *httptest.ResponseRecorder {
	return liveRequestAs(h, method, path, body, ownerLiveScope())
}
func liveRequestAs(h http.Handler, method, path, body string, scope RequestScope) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		r.Header.Set("Content-Type", "application/json")
	}
	r = r.WithContext(WithRequestScope(r.Context(), scope))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func cleanupCatalog(t *testing.T, db *sql.DB) {
	t.Helper()
	_, _ = db.Exec(`DELETE FROM tenants WHERE tenant_id IN ($1,$2)`, liveCatalogTenantA, liveCatalogTenantB)
	_, _ = db.Exec(`DELETE FROM users WHERE user_id=$1`, liveCatalogUser)
}
func seedCatalog(t *testing.T, db *sql.DB) {
	t.Helper()
	tx, err := db.Begin()
	if err != nil {
		t.Fatal(err)
	}
	defer tx.Rollback()
	statements := []struct {
		q string
		a []any
	}{
		{`INSERT INTO users(user_id,email,display_name) VALUES($1,'asset-catalog-live@example.invalid','Asset Catalog Live')`, []any{liveCatalogUser}},
		{`INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES($1,'asset-catalog-a','A','organization'),($2,'asset-catalog-b','B','organization')`, []any{liveCatalogTenantA, liveCatalogTenantB}},
		{`INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES($1,$2,'A',$3),($4,$5,'B',$3)`, []any{liveCatalogTenantA, liveCatalogProjectA, liveCatalogUser, liveCatalogTenantB, liveCatalogProjectB}},
		{`INSERT INTO assets(tenant_id,asset_id,project_id,scope,asset_type,category,lifecycle,title,summary,content_text,payload_jsonb,tags_jsonb,source_kind,source_ref,created_by) VALUES($1,$2,$3,'project','world_rule','world','canon','Rule v1','first','private body v1','{"secret":"payload"}','["v1"]','manual','live-a',$4),($1,$5,$3,'project','note','notes','material','Note','second asset','private note','{}','[]','manual','live-a2',$4),($6,$7,$8,'project','note','notes','material','Foreign','foreign','foreign private','{}','[]','manual','live-b',$4)`, []any{liveCatalogTenantA, liveCatalogAssetA, liveCatalogProjectA, liveCatalogUser, liveCatalogAssetA2, liveCatalogTenantB, liveCatalogAssetB, liveCatalogProjectB}},
	}
	for _, s := range statements {
		if _, err = tx.Exec(s.q, s.a...); err != nil {
			t.Fatalf("seed: %v", err)
		}
	}
	if err = tx.Commit(); err != nil {
		t.Fatal(err)
	}
}
