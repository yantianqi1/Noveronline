package httpapi

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/auth"
)

func TestDevelopmentActorHeaderIsDisabledByDefault(t *testing.T) {
	reader := &recordingAuthReader{result: auth.CurrentUser{
		User: auth.UserSummary{UserID: "target-user"},
	}}
	server := NewServer(Config{AuthReader: reader})
	request := httptest.NewRequest(http.MethodGet, "/v1/me", nil)
	request.Header.Set("X-User-Id", "target-user")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("expected disabled development actor header to return 401, got %d: %s", response.Code, response.Body.String())
	}
	if reader.called {
		t.Fatal("disabled development actor header reached the auth reader")
	}
}

func TestDevelopmentSessionRouteIsDisabledByDefault(t *testing.T) {
	reader := &recordingAuthReader{result: auth.CurrentUser{
		User: auth.UserSummary{UserID: "target-user"},
	}}
	sessionStore := &recordingAuthSessionStore{}
	server := NewServer(Config{
		AuthReader:        reader,
		AuthSessionStore:  sessionStore,
		SessionAuthSecret: "test-secret",
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/auth/dev-sessions", strings.NewReader(`{"user_id":"target-user"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusNotFound {
		t.Fatalf("expected disabled development session route to return 404, got %d: %s", response.Code, response.Body.String())
	}
	if reader.called || sessionStore.createCalled {
		t.Fatalf("disabled development session route caused side effects: reader=%v store=%v", reader.called, sessionStore.createCalled)
	}
}

func TestDevelopmentAuthRequiresExplicitEnablement(t *testing.T) {
	reader := &recordingAuthReader{result: auth.CurrentUser{
		User: auth.UserSummary{UserID: "target-user"},
	}}
	server := NewServer(Config{AuthReader: reader, AllowDevelopmentAuth: true})
	request := httptest.NewRequest(http.MethodGet, "/v1/me", nil)
	request.Header.Set("X-User-Id", "target-user")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected explicitly enabled development actor header to return 200, got %d: %s", response.Code, response.Body.String())
	}
	if !reader.called {
		t.Fatal("explicitly enabled development actor header did not reach the auth reader")
	}
}
