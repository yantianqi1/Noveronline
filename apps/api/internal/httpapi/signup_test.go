package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/platformratelimit"
	"mirofish-novel/apps/api/internal/registration"
)

func TestSignupCreatesPersonalWorkspaceProjectAndAtomicSession(t *testing.T) {
	service := &recordingRegistrationService{result: signupRegistrationResult()}
	legacySessionStore := &recordingAuthSessionStore{createErr: &auth.AppError{Code: auth.CodeLookupFailed, Message: "must not be called"}}
	server := NewServer(Config{
		RegistrationService:       service,
		AuthSessionStore:          legacySessionStore,
		SessionAuthSecret:         "signup-test-secret",
		ForceSecureSessionCookies: true,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/auth/signup", strings.NewReader(`{
		"display_name":" Lin Yan ",
		"email":" LIN.YAN@EXAMPLE.COM ",
		"password":"correct horse battery staple",
		"project_title":"First Novel"
	}`))
	request.Header.Set("X-Request-Id", "req-signup-success")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated {
		t.Fatalf("signup status=%d body=%s", response.Code, response.Body.String())
	}
	if !service.called || service.input.Email != "lin.yan@example.com" || service.input.DisplayName != " Lin Yan " ||
		service.input.Password != "correct horse battery staple" || service.input.ProjectTitle != "First Novel" {
		t.Fatalf("registration input was not preserved and normalized at the expected boundary: %#v", service.input)
	}
	if legacySessionStore.createCalled {
		t.Fatalf("signup persisted a second, post-commit session: %#v", legacySessionStore.createInput)
	}
	cookies := response.Result().Cookies()
	if len(cookies) != 1 || cookies[0].Name != sessionCookieName || !cookies[0].HttpOnly || !cookies[0].Secure || cookies[0].SameSite != http.SameSiteLaxMode {
		t.Fatalf("unexpected signup cookie: %#v", cookies)
	}
	userID, tokenHash, ok := server.verifySignedSessionToken(cookies[0].Value)
	if !ok || userID != service.result.User.UserID || tokenHash != service.initialSession.TokenHash {
		t.Fatalf("signup cookie does not match the transaction session: user=%q hash=%q session=%#v ok=%v", userID, tokenHash, service.initialSession, ok)
	}
	if !service.initialSession.ExpiresAt.After(time.Now().UTC().Add(6 * 24 * time.Hour)) {
		t.Fatalf("initial session expiry was not issued for the normal session TTL: %s", service.initialSession.ExpiresAt)
	}

	var currentUser auth.CurrentUser
	if err := json.NewDecoder(response.Body).Decode(&currentUser); err != nil {
		t.Fatalf("decode signup response: %v", err)
	}
	if currentUser.User.UserID != service.result.User.UserID || len(currentUser.ActiveTenants) != 1 || len(currentUser.ActiveProjects) != 1 ||
		currentUser.ActiveTenants[0].TenantID != service.result.Workspace.TenantID ||
		currentUser.ActiveProjects[0].ProjectID != service.result.Project.ProjectID {
		t.Fatalf("unexpected signup response: %#v", currentUser)
	}
	if strings.Contains(response.Body.String(), "correct horse battery staple") || strings.Contains(response.Body.String(), service.initialSession.TokenHash) {
		t.Fatalf("signup response leaked credential material: %s", response.Body.String())
	}
}

func TestSignupRejectsDuplicateEmail(t *testing.T) {
	service := &recordingRegistrationService{err: &registration.AppError{
		Code: registration.CodeEmailConflict, Message: "private duplicate detail", Field: "email",
	}}
	server := NewServer(Config{RegistrationService: service, SessionAuthSecret: "signup-test-secret"})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, validSignupRequest())

	if response.Code != http.StatusConflict || len(response.Result().Cookies()) != 0 {
		t.Fatalf("duplicate signup status=%d cookies=%#v body=%s", response.Code, response.Result().Cookies(), response.Body.String())
	}
	assertSignupErrorCode(t, response, registration.CodeEmailConflict)
	if strings.Contains(response.Body.String(), "private duplicate detail") {
		t.Fatalf("duplicate signup leaked private error detail: %s", response.Body.String())
	}
}

func TestSignupRejectsUnknownFieldsAndTrailingJSONBeforeSideEffects(t *testing.T) {
	for _, testCase := range []struct {
		name string
		body string
	}{
		{name: "unknown field", body: `{"display_name":"Lin","email":"lin@example.com","password":"correct horse battery staple","project_title":"Novel","tenant_id":"foreign"}`},
		{name: "trailing object", body: `{"display_name":"Lin","email":"lin@example.com","password":"correct horse battery staple","project_title":"Novel"}{}`},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			service := &recordingRegistrationService{result: signupRegistrationResult()}
			server := NewServer(Config{RegistrationService: service, SessionAuthSecret: "signup-test-secret"})
			response := httptest.NewRecorder()
			server.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/v1/auth/signup", strings.NewReader(testCase.body)))

			if response.Code != http.StatusBadRequest || service.called || len(response.Result().Cookies()) != 0 {
				t.Fatalf("malformed signup status=%d called=%v cookies=%#v body=%s", response.Code, service.called, response.Result().Cookies(), response.Body.String())
			}
			assertSignupErrorCode(t, response, registration.CodeValidationFailed)
		})
	}
}

func TestSignupRateLimitUsesTrustedClientAndNormalizedEmail(t *testing.T) {
	service := &recordingRegistrationService{result: signupRegistrationResult()}
	limiter := &recordingPlatformRateLimiter{decision: platformratelimit.Decision{Allowed: false, RetryAfter: 75 * time.Second}}
	server := NewServer(Config{
		RegistrationService:        service,
		SessionAuthSecret:          "signup-test-secret",
		RateLimiter:                limiter,
		TrustedClientProofVerifier: recordingTrustedClientProofVerifier{result: "trusted-client-hash"},
	})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, validSignupRequest())

	if response.Code != http.StatusTooManyRequests || response.Header().Get("Retry-After") != "75" || service.called {
		t.Fatalf("rate-limited signup status=%d retry=%q called=%v body=%s", response.Code, response.Header().Get("Retry-After"), service.called, response.Body.String())
	}
	if !limiter.called || limiter.input.Class != platformratelimit.ClassAuthSignup || limiter.input.Cost != 1 ||
		len(limiter.input.KeyParts) != 2 || limiter.input.KeyParts[0] != "trusted-client-hash" || limiter.input.KeyParts[1] != "lin.yan@example.com" {
		t.Fatalf("unexpected signup rate-limit input: %#v", limiter.input)
	}
	assertSignupErrorCode(t, response, "RATE_LIMITED")
}

func TestSignupInitialSessionPersistenceFailureReturnsNoCookie(t *testing.T) {
	service := &recordingRegistrationService{
		result: signupRegistrationResult(),
		afterSessionErr: &registration.AppError{
			Code: registration.CodeRegistrationFailed, Message: "private session insert failure",
		},
	}
	server := NewServer(Config{RegistrationService: service, SessionAuthSecret: "signup-test-secret"})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, validSignupRequest())

	if response.Code != http.StatusServiceUnavailable || len(response.Result().Cookies()) != 0 || service.initialSession.TokenHash == "" {
		t.Fatalf("failed initial session status=%d cookies=%#v session=%#v body=%s", response.Code, response.Result().Cookies(), service.initialSession, response.Body.String())
	}
	assertSignupErrorCode(t, response, registration.CodeRegistrationFailed)
	if strings.Contains(response.Body.String(), "private session insert failure") {
		t.Fatalf("session persistence error leaked private detail: %s", response.Body.String())
	}
}

type recordingRegistrationService struct {
	input            registration.RegisterInput
	result           registration.Result
	err              error
	afterSessionErr  error
	initialSession   registration.InitialSession
	called           bool
	skipSessionIssue bool
}

func (s *recordingRegistrationService) Register(_ context.Context, input registration.RegisterInput) (registration.Result, error) {
	s.called = true
	s.input = input
	if s.err != nil {
		return registration.Result{}, s.err
	}
	if !s.skipSessionIssue {
		if input.InitialSessionFactory == nil {
			return registration.Result{}, &registration.AppError{Code: registration.CodeBackendUnconfigured, Message: "missing initial session factory"}
		}
		initialSession, err := input.InitialSessionFactory(s.result.User.UserID)
		if err != nil {
			return registration.Result{}, &registration.AppError{Code: registration.CodeRegistrationFailed, Message: "initial session issuance failed"}
		}
		s.initialSession = initialSession
	}
	if s.afterSessionErr != nil {
		return registration.Result{}, s.afterSessionErr
	}
	return s.result, nil
}

func signupRegistrationResult() registration.Result {
	return registration.Result{
		User: registration.UserSummary{
			UserID: "11111111-1111-4111-8111-111111111111", Email: "lin.yan@example.com", DisplayName: "Lin Yan",
		},
		Workspace: registration.WorkspaceSummary{
			TenantID: "22222222-2222-4222-8222-222222222222", Slug: "workspace-2222", Name: "Lin Yan Workspace", Type: "personal", Role: "owner", Status: "active",
		},
		Project: registration.ProjectSummary{
			TenantID: "22222222-2222-4222-8222-222222222222", ProjectID: "33333333-3333-4333-8333-333333333333", Title: "First Novel", Role: "project_owner", Status: "active",
		},
	}
}

func validSignupRequest() *http.Request {
	return httptest.NewRequest(http.MethodPost, "/v1/auth/signup", strings.NewReader(`{
		"display_name":"Lin Yan",
		"email":" LIN.YAN@EXAMPLE.COM ",
		"password":"correct horse battery staple",
		"project_title":"First Novel"
	}`))
}

func assertSignupErrorCode(t *testing.T, response *httptest.ResponseRecorder, expected string) {
	t.Helper()
	var envelope errorEnvelope
	if err := json.NewDecoder(response.Body).Decode(&envelope); err != nil {
		t.Fatalf("decode signup error: %v", err)
	}
	if envelope.Error.Code != expected {
		t.Fatalf("signup error code=%q want=%q body=%s", envelope.Error.Code, expected, response.Body.String())
	}
}
