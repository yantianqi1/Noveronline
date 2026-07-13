package writerworkspace

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/writerplanning"
)

type staticActors struct{ actor Actor }

func (a staticActors) ResolveActor(context.Context, *http.Request) (Actor, error) {
	return a.actor, nil
}

type testBookPlanningStarter struct {
	input writerplanning.StartInput
	calls int
}

func (s *testBookPlanningStarter) Start(_ context.Context, input writerplanning.StartInput) (writerplanning.Admission, error) {
	s.calls++
	s.input = input
	return writerplanning.Admission{RunID: "run-1", ProjectID: input.ProjectID, WorkflowType: writerplanning.WorkflowType(input.Kind), ModuleKey: writerplanning.BookPlanModuleKey, Status: "queued", BookPlanID: input.BookPlanID}, nil
}

func TestBookPlanGenerationCreatesServerOwnedRunFromPersistedPlan(t *testing.T) {
	planning := &testBookPlanningStarter{}
	h := NewHandler(HandlerConfig{Store: &testStore{}, Actors: staticActors{Actor{UserID: "user-1", TenantID: "tenant-1", ProjectID: "project-1", RequestID: "request-1"}}, Authorizer: &testAuthorizer{}, Planning: planning})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/book-plans/plan-1/generations", strings.NewReader(`{"expected_version":3}`)))
	if w.Code != http.StatusAccepted || planning.calls != 1 || planning.input.Kind != writerplanning.KindBookPlan || planning.input.BookPlanID != "plan-1" || planning.input.ExpectedVersion != 3 || planning.input.RequestID != "request-1" {
		t.Fatalf("unexpected generation: status=%d input=%#v body=%s", w.Code, planning.input, w.Body.String())
	}
}

func TestBookPlanGenerationRejectsCallerRunAndStatus(t *testing.T) {
	planning := &testBookPlanningStarter{}
	h := NewHandler(HandlerConfig{Store: &testStore{}, Actors: staticActors{Actor{UserID: "user-1", TenantID: "tenant-1"}}, Authorizer: &testAuthorizer{}, Planning: planning})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/book-plans/plan-1/generations", strings.NewReader(`{"expected_version":3,"run_id":"fake","status":"completed"}`)))
	if w.Code != http.StatusBadRequest || planning.calls != 0 {
		t.Fatalf("caller-owned run accepted: status=%d calls=%d", w.Code, planning.calls)
	}
}

type testAuthorizer struct {
	inputs []AuthorizeInput
	err    error
}

func (a *testAuthorizer) Authorize(_ context.Context, in AuthorizeInput) error {
	a.inputs = append(a.inputs, in)
	return a.err
}

type testStore struct {
	Store
	listCalls   int
	createCalls int
	presetCalls int
}

func (s *testStore) GetPreset(context.Context, Scope, string) (WriterPreset, error) {
	s.presetCalls++
	return WriterPreset{PresetID: "preset-1", Scope: "tenant", Name: "Tenant preset"}, nil
}

type testOwnerLookup struct {
	owner  ResourceOwner
	err    error
	inputs []OwnerLookupInput
}

func (l *testOwnerLookup) LookupResourceOwner(_ context.Context, input OwnerLookupInput) (ResourceOwner, error) {
	l.inputs = append(l.inputs, input)
	return l.owner, l.err
}

func (s *testStore) ListChapters(context.Context, Scope) ([]Chapter, error) {
	s.listCalls++
	return []Chapter{{ChapterID: "chapter-1", Title: "Public title"}}, nil
}
func (s *testStore) GetChapter(context.Context, Scope, string, bool) (Chapter, error) {
	return Chapter{ChapterID: "chapter-1", Title: "Public title", Private: &PrivateFields{Content: "private"}}, nil
}
func (s *testStore) CreateChapter(context.Context, CreateChapterInput) (Chapter, error) {
	s.createCalls++
	return Chapter{ChapterID: "chapter-1"}, nil
}

func TestHandlerUsesTenantScopedOwnerLookupForGlobalPrivateRead(t *testing.T) {
	store := &testStore{}
	authz := &testAuthorizer{}
	owners := &testOwnerLookup{owner: ResourceOwner{ProjectID: "owner-project"}}
	h := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: "user-1", TenantID: "tenant-1", ProjectID: "untrusted-project"}}, Authorizer: authz, OwnerLookup: owners})
	r := httptest.NewRequest(http.MethodGet, "/v1/chapters/chapter-1?include_private=true", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK || len(authz.inputs) != 1 || authz.inputs[0].Operation != OperationPrivateRead || authz.inputs[0].ProjectID != "owner-project" {
		t.Fatalf("unexpected private read contract: status=%d auth=%#v", w.Code, authz.inputs)
	}
	if len(owners.inputs) != 1 || owners.inputs[0].TenantID != "tenant-1" || owners.inputs[0].Kind != ResourceChapter || owners.inputs[0].ResourceID != "chapter-1" {
		t.Fatalf("unexpected owner lookup: %#v", owners.inputs)
	}
}

func TestGlobalResourceOwnerLookupFailsClosedBeforeAuthorizationOrStore(t *testing.T) {
	for _, test := range []struct {
		name  string
		owner ResourceOwner
		err   error
	}{
		{name: "blank owner"},
		{name: "lookup failure", err: errors.New("private lookup failure")},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := &testStore{}
			authz := &testAuthorizer{}
			h := NewHandler(HandlerConfig{
				Store: store, Actors: staticActors{Actor{UserID: "user-1", TenantID: "tenant-1", ProjectID: "client-project"}},
				Authorizer: authz, OwnerLookup: &testOwnerLookup{owner: test.owner, err: test.err},
			})
			w := httptest.NewRecorder()
			h.ServeHTTP(w, httptest.NewRequest(http.MethodGet, "/v1/scenes/scene-1", nil))
			if w.Code != http.StatusForbidden || len(authz.inputs) != 0 || store.listCalls != 0 {
				t.Fatalf("owner lookup did not fail closed: status=%d auth=%#v", w.Code, authz.inputs)
			}
		})
	}
}

func TestTenantPresetMutationUsesTenantAdminOperationBeforeDecode(t *testing.T) {
	store := &testStore{}
	authz := &testAuthorizer{err: errors.New("tenant writer denied")}
	h := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: "writer", TenantID: "tenant-1", ProjectID: "project-1"}}, Authorizer: authz})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/v1/tenants/tenant-1/writer-presets", strings.NewReader(`{"api_key":"secret"}`)))
	if w.Code != http.StatusForbidden || len(authz.inputs) != 1 || authz.inputs[0].Operation != OperationTenantPresetManage || authz.inputs[0].ProjectID != "" || store.presetCalls != 0 {
		t.Fatalf("unexpected tenant preset authority: status=%d auth=%#v calls=%d", w.Code, authz.inputs, store.presetCalls)
	}
}

func TestGlobalTenantPresetMutationUsesLookupScopeAndTenantAdminOperation(t *testing.T) {
	store := &testStore{}
	authz := &testAuthorizer{err: errors.New("tenant writer denied")}
	owners := &testOwnerLookup{owner: ResourceOwner{TenantScoped: true}}
	h := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: "writer", TenantID: "tenant-1", ProjectID: "project-1"}}, Authorizer: authz, OwnerLookup: owners})
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPatch, "/v1/writer-presets/preset-1", strings.NewReader(`{"name":"changed"}`)))
	if w.Code != http.StatusForbidden || len(authz.inputs) != 1 || authz.inputs[0].Operation != OperationTenantPresetManage || authz.inputs[0].ProjectID != "" || store.presetCalls != 0 {
		t.Fatalf("global tenant preset did not require tenant admin: status=%d auth=%#v calls=%d", w.Code, authz.inputs, store.presetCalls)
	}
}
func TestHandlerAuthorizesBeforeDecodeOrMutation(t *testing.T) {
	store := &testStore{}
	authz := &testAuthorizer{err: errors.New("driver prompt api_key=secret")}
	h := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: "viewer", TenantID: "tenant-1", ProjectID: "project-1"}}, Authorizer: authz})
	r := httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/chapters", strings.NewReader(`{"unknown_secret":"prompt"}`))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusForbidden || store.createCalls != 0 {
		t.Fatalf("denied viewer reached mutation: status=%d calls=%d", w.Code, store.createCalls)
	}
	for _, secret := range []string{"api_key", "prompt", "driver"} {
		if strings.Contains(w.Body.String(), secret) {
			t.Fatalf("public denial leaked %q: %s", secret, w.Body.String())
		}
	}
}
func TestHandlerRejectsBodyTenantAndUnknownFields(t *testing.T) {
	store := &testStore{}
	h := NewHandler(HandlerConfig{Store: store, Actors: staticActors{Actor{UserID: "writer", TenantID: "tenant-1", ProjectID: "project-1"}}, Authorizer: &testAuthorizer{}})
	r := httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/chapters", strings.NewReader(`{"title":"x","tenant_id":"tenant-2"}`))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusBadRequest || store.createCalls != 0 {
		t.Fatalf("body tenant was trusted: status=%d calls=%d body=%s", w.Code, store.createCalls, w.Body.String())
	}
}
