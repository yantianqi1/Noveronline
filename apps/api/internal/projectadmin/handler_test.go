package projectadmin

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestIsRoute(t *testing.T) {
	cases := []struct {
		method string
		path   string
		want   bool
	}{
		{http.MethodPost, "/v1/tenants/abc/projects", true},
		{http.MethodPatch, "/v1/tenants/abc/projects/def", true},
		{http.MethodGet, "/v1/tenants/abc/projects", false},
		{http.MethodPost, "/v1/tenants/abc/projects/def", false},
		{http.MethodGet, "/v1/tenants/abc/projects/def/members", false},
		{http.MethodPost, "/v1/tenants/abc/invitations", false},
		{http.MethodPost, "/v1/projects/abc", false},
	}
	for _, c := range cases {
		if got := IsRoute(c.method, c.path); got != c.want {
			t.Fatalf("IsRoute(%s, %s) = %v, want %v", c.method, c.path, got, c.want)
		}
	}
}

func TestHandlerCreateProject(t *testing.T) {
	tx := &recordingTx{managerAllowed: true, returnedProject: []string{testTenantID, testProjectID, "Second Novel", "active"}}
	handler := newTestHandler(tx, testActorID, true)

	response := doRequest(handler, http.MethodPost, "/v1/tenants/"+testTenantID+"/projects", `{"title":"Second Novel"}`)
	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	var body struct {
		OK      bool    `json:"ok"`
		Project Project `json:"project"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !body.OK || body.Project.ProjectID != testProjectID || body.Project.Role != "project_owner" {
		t.Fatalf("unexpected body: %#v", body)
	}
}

func TestHandlerRenameProject(t *testing.T) {
	tx := &recordingTx{managerAllowed: true, returnedProject: []string{testTenantID, testProjectID, "Renamed", "active"}}
	handler := newTestHandler(tx, testActorID, true)

	response := doRequest(handler, http.MethodPatch, "/v1/tenants/"+testTenantID+"/projects/"+testProjectID, `{"title":"Renamed"}`)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerRejectsUnauthenticated(t *testing.T) {
	handler := newTestHandler(&recordingTx{managerAllowed: true}, "", true)
	response := doRequest(handler, http.MethodPost, "/v1/tenants/"+testTenantID+"/projects", `{"title":"Second Novel"}`)
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerRejectsMissingCSRF(t *testing.T) {
	handler := newTestHandler(&recordingTx{managerAllowed: true}, testActorID, false)
	response := doRequest(handler, http.MethodPost, "/v1/tenants/"+testTenantID+"/projects", `{"title":"Second Novel"}`)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerMapsValidationError(t *testing.T) {
	handler := newTestHandler(&recordingTx{managerAllowed: true}, testActorID, true)
	response := doRequest(handler, http.MethodPost, "/v1/tenants/"+testTenantID+"/projects", `{"title":"   "}`)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "\"field\":\"title\"") {
		t.Fatalf("expected field detail, got %s", response.Body.String())
	}
}

func TestHandlerRejectsUnknownBodyFields(t *testing.T) {
	handler := newTestHandler(&recordingTx{managerAllowed: true}, testActorID, true)
	response := doRequest(handler, http.MethodPost, "/v1/tenants/"+testTenantID+"/projects", `{"title":"Novel","extra":true}`)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerMethodNotAllowed(t *testing.T) {
	handler := newTestHandler(&recordingTx{managerAllowed: true}, testActorID, true)
	response := doRequest(handler, http.MethodGet, "/v1/tenants/"+testTenantID+"/projects", "")
	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d body = %s", response.Code, response.Body.String())
	}
}

func newTestHandler(tx transaction, actor string, csrfOK bool) *Handler {
	return NewHandler(HandlerConfig{
		Service:       testService(tx),
		ActorResolver: stubActorResolver{actor: actor},
		CSRFVerifier:  stubCSRFVerifier{ok: csrfOK},
	})
}

func doRequest(handler *Handler, method, path, body string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

type stubActorResolver struct{ actor string }

func (s stubActorResolver) ResolveActor(context.Context, *http.Request) (string, error) {
	if strings.TrimSpace(s.actor) == "" {
		return "", nil
	}
	return s.actor, nil
}

type stubCSRFVerifier struct{ ok bool }

func (s stubCSRFVerifier) VerifyCSRF(context.Context, *http.Request) error {
	if s.ok {
		return nil
	}
	return errContext
}

var errContext = &AppError{Code: "CSRF", Message: "csrf failed"}
