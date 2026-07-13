package manuscriptworkspace

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/writerplanning"
)

type testResolver struct {
	scope Scope
	err   error
	calls int
}

type testPlanningStarter struct {
	input writerplanning.StartInput
	calls int
}

func (s *testPlanningStarter) Start(_ context.Context, input writerplanning.StartInput) (writerplanning.Admission, error) {
	s.calls++
	s.input = input
	return writerplanning.Admission{RunID: "run-1", ProjectID: input.ProjectID, WorkflowType: writerplanning.WorkflowType(input.Kind), ModuleKey: writerplanning.DedupModuleKey, Status: "queued"}, nil
}

func TestDedupExtractionUsesExplicitSelectionWithoutAcceptingContent(t *testing.T) {
	planning := &testPlanningStarter{}
	handler := NewHandler(HandlerConfig{Planning: planning, Resolver: &testResolver{scope: Scope{TenantID: "tenant-1", ActorUserID: "user-1", RequestID: "request-1"}}, Authorizer: &testAuthorizer{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/manuscript-workspace/dedup-extractions", strings.NewReader(`{"block_ids":["block-1"],"chapter_id":"chapter-1"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusAccepted || planning.calls != 1 || planning.input.Kind != writerplanning.KindDedup || len(planning.input.BlockIDs) != 1 || planning.input.RequestID != "request-1" {
		t.Fatalf("unexpected extraction admission: status=%d input=%#v", response.Code, planning.input)
	}
	if strings.Contains(response.Body.String(), "content_text") {
		t.Fatalf("public response exposed content field: %s", response.Body.String())
	}
}

func TestDedupExtractionRejectsBodyContentBeforeStarter(t *testing.T) {
	planning := &testPlanningStarter{}
	handler := NewHandler(HandlerConfig{Planning: planning, Resolver: &testResolver{scope: Scope{TenantID: "tenant-1", ActorUserID: "user-1", RequestID: "request-1"}}, Authorizer: &testAuthorizer{}})
	request := httptest.NewRequest(http.MethodPost, "/v1/projects/project-1/manuscript-workspace/dedup-extractions", strings.NewReader(`{"block_ids":["block-1"],"content_text":"private manuscript"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest || planning.calls != 0 || strings.Contains(response.Body.String(), "private manuscript") {
		t.Fatalf("private body reached starter: status=%d calls=%d body=%s", response.Code, planning.calls, response.Body.String())
	}
}

func (r *testResolver) ResolveManuscriptContext(context.Context, *http.Request, string) (Scope, error) {
	r.calls++
	return r.scope, r.err
}

type testAuthorizer struct {
	permission string
	err        error
	calls      int
}

func (a *testAuthorizer) AuthorizeManuscript(_ context.Context, _ Scope, permission string) error {
	a.calls++
	a.permission = permission
	return a.err
}

type testStore struct {
	Store
	private     PrivateBlock
	getCalls    int
	updateCalls int
	updateInput UpdateBlockInput
}

func (s *testStore) GetPrivateBlock(context.Context, Scope, string) (PrivateBlock, error) {
	s.getCalls++
	return s.private, nil
}

func (s *testStore) UpdateBlock(_ context.Context, input UpdateBlockInput) (PrivateBlock, error) {
	s.updateCalls++
	s.updateInput = input
	return s.private, nil
}

func TestHandlerAuthorizesBeforeDecodingOrStoreMutation(t *testing.T) {
	resolver := &testResolver{scope: Scope{TenantID: "tenant-1", ActorUserID: "user-1", RequestID: "request-1"}}
	authorizer := &testAuthorizer{err: errors.New("denied private prompt api_key")}
	store := &testStore{}
	handler := NewHandler(HandlerConfig{Store: store, Resolver: resolver, Authorizer: authorizer})
	request := httptest.NewRequest(http.MethodPatch,
		"/v1/projects/project-1/manuscript-workspace/blocks/block-1",
		strings.NewReader(`{"content_text":"private manuscript","expected_version":1}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || authorizer.permission != PermissionWrite || store.updateCalls != 0 {
		t.Fatalf("status=%d permission=%q writes=%d", response.Code, authorizer.permission, store.updateCalls)
	}
	for _, forbidden := range []string{"private manuscript", "api_key", "prompt", "user-1"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("public authorization error leaked %q", forbidden)
		}
	}
}

func TestHandlerPrivateReadRequiresReadPermissionAndReturnsContent(t *testing.T) {
	resolver := &testResolver{scope: Scope{TenantID: "tenant-1", ActorUserID: "user-1"}}
	authorizer := &testAuthorizer{}
	store := &testStore{private: PrivateBlock{
		BlockMetadata: BlockMetadata{BlockID: "block-1", ProjectID: "project-1", Status: "active", Version: 2},
		ContentText:   "authorized private content",
	}}
	handler := NewHandler(HandlerConfig{Store: store, Resolver: resolver, Authorizer: authorizer})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript-workspace/blocks/block-1", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK || authorizer.permission != PermissionRead || store.getCalls != 1 {
		t.Fatalf("status=%d permission=%q reads=%d", response.Code, authorizer.permission, store.getCalls)
	}
	if !strings.Contains(response.Body.String(), "authorized private content") {
		t.Fatalf("authorized private response omitted content: %s", response.Body.String())
	}
}

func TestHandlerRejectsUnknownPrivateFieldsWithStableError(t *testing.T) {
	resolver := &testResolver{scope: Scope{TenantID: "tenant-1", ActorUserID: "user-1", RequestID: "request-1"}}
	authorizer := &testAuthorizer{}
	store := &testStore{}
	handler := NewHandler(HandlerConfig{Store: store, Resolver: resolver, Authorizer: authorizer})
	request := httptest.NewRequest(http.MethodPatch,
		"/v1/projects/project-1/manuscript-workspace/blocks/block-1",
		strings.NewReader(`{"expected_version":1,"api_key":"secret","content_text":"private"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest || store.updateCalls != 0 {
		t.Fatalf("status=%d writes=%d", response.Code, store.updateCalls)
	}
	for _, forbidden := range []string{"api_key", "secret", "private"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("decode error leaked %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestMalformedPathHasNoAuthenticationSideEffects(t *testing.T) {
	resolver := &testResolver{}
	handler := NewHandler(HandlerConfig{Resolver: resolver, Authorizer: &testAuthorizer{}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript-workspace//blocks", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusNotFound || resolver.calls != 0 {
		t.Fatalf("status=%d resolver calls=%d", response.Code, resolver.calls)
	}
}
