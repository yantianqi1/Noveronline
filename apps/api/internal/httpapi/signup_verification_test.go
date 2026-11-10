package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/registration"
)

type verificationRegistrationService struct {
	result       registration.Result
	challenge    registration.EmailVerificationChallenge
	startCalled  bool
	verifyCalled bool
}

func (s *verificationRegistrationService) Register(context.Context, registration.RegisterInput) (registration.Result, error) {
	return registration.Result{}, &registration.AppError{Code: registration.CodeBackendUnconfigured, Message: "legacy path must not be called"}
}

func (s *verificationRegistrationService) StartEmailVerification(_ context.Context, input registration.EmailVerificationStartInput) (registration.EmailVerificationChallenge, error) {
	s.startCalled = true
	if strings.ToLower(strings.TrimSpace(input.Email)) != "lin.yan@example.com" {
		return registration.EmailVerificationChallenge{}, &registration.AppError{Code: registration.CodeValidationFailed, Message: "unexpected email", Field: "email"}
	}
	return s.challenge, nil
}

func (s *verificationRegistrationService) VerifyEmail(_ context.Context, input registration.EmailVerificationInput) (registration.Result, error) {
	s.verifyCalled = true
	if input.Token != "verification-token" {
		return registration.Result{}, &registration.AppError{Code: registration.CodeVerificationInvalid, Message: "invalid token"}
	}
	if _, err := input.InitialSessionFactory(s.result.User.UserID); err != nil {
		return registration.Result{}, err
	}
	return s.result, nil
}

func TestSignupRequiresEmailVerificationBeforeIssuingSession(t *testing.T) {
	service := &verificationRegistrationService{challenge: registration.EmailVerificationChallenge{
		Email: "lin.yan@example.com", Token: "verification-token",
	}}
	var delivered registration.EmailVerificationChallenge
	server := NewServer(Config{
		RegistrationService: service,
		EmailVerificationSender: func(_ context.Context, challenge registration.EmailVerificationChallenge) error {
			delivered = challenge
			return nil
		},
		RequireEmailVerification: true,
		AllowSelfSignup:          true,
		SessionAuthSecret:        "signup-verification-secret",
	})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, validSignupRequest())

	if response.Code != http.StatusAccepted || !service.startCalled || service.verifyCalled || len(response.Result().Cookies()) != 0 {
		t.Fatalf("verification signup status=%d start=%v verify=%v cookies=%#v body=%s", response.Code, service.startCalled, service.verifyCalled, response.Result().Cookies(), response.Body.String())
	}
	if delivered.Token != "verification-token" || delivered.Email != "lin.yan@example.com" {
		t.Fatalf("unexpected delivery challenge: %#v", delivered)
	}
	if strings.Contains(response.Body.String(), delivered.Email) || strings.Contains(response.Body.String(), delivered.Token) {
		t.Fatalf("signup response disclosed verification details: %s", response.Body.String())
	}
}

func TestSignupVerificationConsumesChallengeAndCreatesSession(t *testing.T) {
	service := &verificationRegistrationService{result: signupRegistrationResult()}
	server := NewServer(Config{
		RegistrationService:       service,
		RequireEmailVerification:  true,
		AllowSelfSignup:           true,
		SessionAuthSecret:         "signup-verification-secret",
		ForceSecureSessionCookies: true,
	})
	request := httptest.NewRequest(http.MethodPost, "/v1/auth/signup/verify", strings.NewReader(`{"token":"verification-token"}`))
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)

	if response.Code != http.StatusCreated || !service.verifyCalled {
		t.Fatalf("verification status=%d called=%v body=%s", response.Code, service.verifyCalled, response.Body.String())
	}
	cookies := response.Result().Cookies()
	if len(cookies) != 1 || cookies[0].Name != sessionCookieName || !cookies[0].Secure || !cookies[0].HttpOnly {
		t.Fatalf("unexpected verification cookie: %#v", cookies)
	}
}

func TestSignupRequiresConfiguredSenderWhenVerificationIsEnabled(t *testing.T) {
	service := &verificationRegistrationService{}
	server := NewServer(Config{
		RegistrationService:      service,
		RequireEmailVerification: true,
		AllowSelfSignup:          true,
		SessionAuthSecret:        "signup-verification-secret",
	})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, validSignupRequest())

	if response.Code != http.StatusServiceUnavailable || service.startCalled || len(response.Result().Cookies()) != 0 {
		t.Fatalf("missing sender status=%d start=%v cookies=%#v body=%s", response.Code, service.startCalled, response.Result().Cookies(), response.Body.String())
	}
	assertSignupErrorCode(t, response, registration.CodeBackendUnconfigured)
}
