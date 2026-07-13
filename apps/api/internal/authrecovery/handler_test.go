package authrecovery

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"
)

type clientScopeLimiter struct {
	inputs []AbuseLimitInput
}

func (l *clientScopeLimiter) Allow(_ context.Context, input AbuseLimitInput) (AbuseLimitDecision, error) {
	l.inputs = append(l.inputs, input)
	return AbuseLimitDecision{Allowed: len(l.inputs) == 1}, nil
}

func signedClientProof(secret []byte, now time.Time, clientHash string) string {
	message := "v1:" + strconv.FormatInt(now.Unix(), 10) + ":" + clientHash
	mac := hmac.New(sha256.New, secret)
	_, _ = mac.Write([]byte(message))
	return message + ":" + hex.EncodeToString(mac.Sum(nil))
}

func TestRequestUsesSignedClientHashInsteadOfProxyRemoteAddress(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	now := time.Date(2026, 7, 11, 2, 0, 0, 0, time.UTC)
	verifier, _ := NewClientProofVerifier(secret, func() time.Time { return now }, time.Minute)
	limiter := &clientScopeLimiter{}
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{AbuseLimiter: limiter}), ClientProofVerifier: verifier})
	request := httptest.NewRequest(http.MethodPost, "/v1/auth/recovery/request", bytes.NewBufferString(`{"email":"user@example.test"}`))
	request.RemoteAddr = "web-container:43210"
	clientHash := hashToken("203.0.113.7")
	request.Header.Set(RecoveryClientProofHeader, signedClientProof(secret, now, clientHash))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if len(limiter.inputs) != 2 || limiter.inputs[0].ScopeKey != "user@example.test" || limiter.inputs[1].ScopeKey != clientHash {
		t.Fatalf("limiter inputs=%+v", limiter.inputs)
	}
	verified, err := verifier.Verify(request.Header.Get(RecoveryClientProofHeader))
	if err != nil || verified != clientHash || verified == request.RemoteAddr {
		t.Fatalf("verified=%q remote=%q err=%v", verified, request.RemoteAddr, err)
	}
}

func TestRequestRejectsBareForwardedHeadersWithoutSignedProof(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	verifier, _ := NewClientProofVerifier(secret, time.Now, time.Minute)
	limiter := &denyingLimiter{}
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{AbuseLimiter: limiter}), ClientProofVerifier: verifier})
	request := httptest.NewRequest(http.MethodPost, "/v1/auth/recovery/request", bytes.NewBufferString(`{"email":"user@example.test"}`))
	request.Header.Set("X-Forwarded-For", "203.0.113.7")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusForbidden || limiter.calls != 0 {
		t.Fatalf("status=%d limiter_calls=%d", recorder.Code, limiter.calls)
	}
}

func TestRequestVerifiesClientProofBeforeDecodingJSON(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	verifier, _ := NewClientProofVerifier(secret, time.Now, time.Minute)
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{AbuseLimiter: &denyingLimiter{}}), ClientProofVerifier: verifier})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/v1/auth/recovery/request", bytes.NewBufferString(`{"email":`)))
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("invalid proof must win before JSON decode: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func TestResetVerifiesClientProofBeforeDecodingJSON(t *testing.T) {
	secret := []byte("0123456789abcdef0123456789abcdef")
	verifier, _ := NewClientProofVerifier(secret, time.Now, time.Minute)
	handler := NewHandler(HandlerConfig{Service: NewService(ServiceConfig{}), ClientProofVerifier: verifier})
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodPost, "/v1/auth/recovery/reset", bytes.NewBufferString(`{"token":`)))
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("invalid proof must win before reset JSON decode: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}
