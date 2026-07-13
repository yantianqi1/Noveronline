package assetcatalog

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type fakeStore struct {
	asset       Asset
	versions    []Version
	collections []Collection
	err         error
	called      string
	private     bool
}

func (f *fakeStore) GetAsset(_ context.Context, _ RequestScope, _ string, p bool) (Asset, error) {
	f.called = "get"
	f.private = p
	return f.asset, f.err
}
func (f *fakeStore) ListVersions(_ context.Context, _ RequestScope, _ string, p bool) ([]Version, error) {
	f.called = "versions"
	f.private = p
	return f.versions, f.err
}
func (f *fakeStore) UpdateAsset(_ context.Context, _ RequestScope, _ string, _ AssetPatch) (Asset, error) {
	f.called = "update"
	return f.asset, f.err
}
func (f *fakeStore) RestoreAsset(_ context.Context, _ RequestScope, _ string, _ RestoreInput) (Asset, error) {
	f.called = "restore"
	return f.asset, f.err
}
func (f *fakeStore) ListCollections(context.Context, RequestScope) ([]Collection, error) {
	f.called = "listCollections"
	return f.collections, f.err
}
func (f *fakeStore) CreateCollection(_ context.Context, _ RequestScope, _ CollectionInput) (Collection, error) {
	f.called = "createCollection"
	return Collection{}, f.err
}
func (f *fakeStore) UpdateCollection(_ context.Context, _ RequestScope, _ string, _ CollectionInput) (Collection, error) {
	f.called = "updateCollection"
	return Collection{}, f.err
}
func (f *fakeStore) DeleteCollection(_ context.Context, _ RequestScope, _ string) error {
	f.called = "deleteCollection"
	return f.err
}
func (f *fakeStore) AddMembership(_ context.Context, _ RequestScope, _, _ string, _ MembershipInput) (Collection, error) {
	f.called = "addMembership"
	return Collection{}, f.err
}
func (f *fakeStore) RemoveMembership(_ context.Context, _ RequestScope, _, _ string) (Collection, error) {
	f.called = "removeMembership"
	return Collection{}, f.err
}
func (f *fakeStore) ReorderMemberships(_ context.Context, _ RequestScope, _ string, _ ReorderInput) (Collection, error) {
	f.called = "reorder"
	return Collection{}, f.err
}

func request(t *testing.T, h http.Handler, method, path, body string, scope RequestScope) *httptest.ResponseRecorder {
	t.Helper()
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	if body != "" {
		r.Header.Set("Content-Type", "application/json")
	}
	r = r.WithContext(WithRequestScope(r.Context(), scope))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}
func ownerScope() RequestScope {
	return RequestScope{ActorID: "10000000-0000-0000-0000-000000000001", TenantID: "20000000-0000-0000-0000-000000000001", ProjectID: "30000000-0000-0000-0000-000000000001", Role: "owner", Permissions: map[Permission]bool{PermissionReadPrivate: true, PermissionMutate: true, PermissionCollections: true}}
}

func TestPublicDetailDoesNotRequestOrSerializePrivateContent(t *testing.T) {
	f := &fakeStore{asset: Asset{AssetID: "asset-1", Title: "Public title", Payload: nil, Private: nil}}
	scope := ownerScope()
	scope.Permissions[PermissionReadPrivate] = false
	w := request(t, NewHandler(f), http.MethodGet, "/v1/projects/"+scope.ProjectID+"/asset-catalog/assets/asset-1", "", scope)
	if w.Code != http.StatusOK {
		t.Fatalf("status %d: %s", w.Code, w.Body.String())
	}
	if f.private {
		t.Fatal("public detail requested private fields")
	}
	if strings.Contains(w.Body.String(), "content_text") || strings.Contains(w.Body.String(), `"private":`) || strings.Contains(w.Body.String(), `"payload":`) {
		t.Fatalf("private fields leaked: %s", w.Body.String())
	}
}

func TestPrivateVersionHistoryIsPermissionGated(t *testing.T) {
	f := &fakeStore{}
	scope := ownerScope()
	scope.Permissions[PermissionReadPrivate] = false
	w := request(t, NewHandler(f), http.MethodGet, "/v1/projects/"+scope.ProjectID+"/asset-catalog/assets/a/versions?include_private=true", "", scope)
	if w.Code != http.StatusForbidden {
		t.Fatalf("status %d", w.Code)
	}
	if f.called != "" {
		t.Fatalf("store called: %s", f.called)
	}
}

func TestViewerCannotMutateAndCrossProjectIsHidden(t *testing.T) {
	f := &fakeStore{}
	scope := ownerScope()
	scope.Permissions = map[Permission]bool{}
	w := request(t, NewHandler(f), http.MethodPatch, "/v1/projects/"+scope.ProjectID+"/asset-catalog/assets/a", `{"expected_version":1,"title":"x"}`, scope)
	if w.Code != http.StatusForbidden {
		t.Fatalf("viewer status %d", w.Code)
	}
	w = request(t, NewHandler(f), http.MethodGet, "/v1/projects/other/asset-catalog/assets/a", "", scope)
	if w.Code != http.StatusNotFound {
		t.Fatalf("cross-project status %d", w.Code)
	}
}

func TestStrictJSONAndConflictHaveStableErrors(t *testing.T) {
	scope := ownerScope()
	f := &fakeStore{}
	w := request(t, NewHandler(f), http.MethodPatch, "/v1/projects/"+scope.ProjectID+"/asset-catalog/assets/a", `{"expected_version":1,"unknown":true}`, scope)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("strict status %d", w.Code)
	}
	f.err = ErrConflict
	w = request(t, NewHandler(f), http.MethodPatch, "/v1/projects/"+scope.ProjectID+"/asset-catalog/assets/a", `{"expected_version":1,"title":"x"}`, scope)
	if w.Code != http.StatusConflict || !strings.Contains(w.Body.String(), "ASSET_VERSION_CONFLICT") {
		t.Fatalf("conflict response %d %s", w.Code, w.Body.String())
	}
}

func TestCollectionMembershipAndReorderRoutes(t *testing.T) {
	scope := ownerScope()
	f := &fakeStore{}
	base := "/v1/projects/" + scope.ProjectID + "/asset-catalog/collections/c"
	w := request(t, NewHandler(f), http.MethodPut, base+"/items/a", `{"position":0}`, scope)
	if w.Code != http.StatusOK || f.called != "addMembership" {
		t.Fatalf("add %d %s", w.Code, f.called)
	}
	w = request(t, NewHandler(f), http.MethodPut, base+"/order", `{"asset_ids":["a"]}`, scope)
	if w.Code != http.StatusOK || f.called != "reorder" {
		t.Fatalf("order %d %s", w.Code, f.called)
	}
	w = request(t, NewHandler(f), http.MethodDelete, base+"/items/a", "", scope)
	if w.Code != http.StatusOK || f.called != "removeMembership" {
		t.Fatalf("remove %d %s", w.Code, f.called)
	}
}

func TestOperationsPublishRBACMetadata(t *testing.T) {
	raw, _ := json.Marshal(Operations)
	text := string(raw)
	for _, permission := range []string{string(PermissionMutate), string(PermissionCollections)} {
		if !strings.Contains(text, permission) {
			t.Fatalf("missing operation metadata %s", permission)
		}
	}
}
