package llm

import (
	"context"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestProviderHTTPExecutorRequiresExternalHTTPSOptIn(t *testing.T) {
	executor := configuredProviderExecutor(http.DefaultClient)
	request := providerHTTPRequest("https://api.example.test/v1", false)

	_, err := executor.Execute(context.Background(), request)
	if code := ErrorCode(err); code != "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED" {
		t.Fatalf("external provider without opt-in: code=%s err=%v", code, err)
	}
	request.BaseURL = "http://api.example.test/v1"
	request.ExternalProviderOptIn = true
	_, err = executor.Execute(context.Background(), request)
	if code := ErrorCode(err); code != "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED" {
		t.Fatalf("external HTTP provider: code=%s err=%v", code, err)
	}
}

func TestProviderHTTPExecutorTreatsPrivateAndLinkLocalTargetsAsExternal(t *testing.T) {
	executor := configuredProviderExecutor(http.DefaultClient)
	for _, baseURL := range []string{
		"http://10.0.0.8/v1",
		"http://192.168.1.8/v1",
		"http://169.254.169.254/latest",
		"http://metadata/v1",
	} {
		_, err := executor.Execute(context.Background(), providerHTTPRequest(baseURL, true))
		if code := ErrorCode(err); code != "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED" {
			t.Fatalf("SSRF-sensitive endpoint %q bypassed external HTTPS boundary: code=%s err=%v", baseURL, code, err)
		}
	}
}

func TestLiveExternalHTTPSProviderRequiresOptInAndSucceedsWhenEnabled(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":6}}`))
	}))
	defer server.Close()
	serverAddress := strings.TrimPrefix(server.URL, "https://")
	transport := server.Client().Transport.(*http.Transport).Clone()
	transport.TLSClientConfig = transport.TLSClientConfig.Clone()
	transport.TLSClientConfig.InsecureSkipVerify = true // Test server certificate is issued only for its loopback host.
	transport.DialContext = func(ctx context.Context, network, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, network, serverAddress)
	}
	executor := configuredProviderExecutor(&http.Client{Transport: transport})
	request := providerHTTPRequest("https://external.example.test/v1", false)
	_, err := executor.Execute(context.Background(), request)
	if code := ErrorCode(err); code != "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED" {
		t.Fatalf("external HTTPS call bypassed opt-in: code=%s err=%v", code, err)
	}
	request.ExternalProviderOptIn = true
	result, err := executor.Execute(context.Background(), request)
	if err != nil || result.PromptTokens != 4 || result.CompletionTokens != 6 {
		t.Fatalf("opted-in external HTTPS provider failed: result=%#v err=%v", result, err)
	}
}

func TestProviderHTTPExecutorRetriesOnlyConfiguredTransientFailures(t *testing.T) {
	var mu sync.Mutex
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		attempts++
		attempt := attempts
		mu.Unlock()
		if r.Header.Get("Idempotency-Key") != "provider-call-1" {
			t.Fatalf("missing stable idempotency key")
		}
		if attempt == 1 {
			http.Error(w, "api_key=secret prompt=private", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":7}}`))
	}))
	defer server.Close()
	executor := configuredProviderExecutor(server.Client())
	executor.config.MaxAttempts = 2
	request := providerHTTPRequest(server.URL, false)

	result, err := executor.Execute(context.Background(), request)
	if err != nil {
		t.Fatalf("execute provider request: %v", err)
	}
	if attempts != 2 || result.PromptTokens != 11 || result.CompletionTokens != 7 {
		t.Fatalf("unexpected retries/result: attempts=%d result=%#v", attempts, result)
	}
}

func TestProviderHTTPExecutorTimeoutAndCancellationAreStableAndNotRetried(t *testing.T) {
	attempts := 0
	client := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		attempts++
		<-request.Context().Done()
		return nil, request.Context().Err()
	})}
	executor := configuredProviderExecutor(client)
	executor.config.Timeout = 10 * time.Millisecond
	executor.config.MaxAttempts = 4
	_, err := executor.Execute(context.Background(), providerHTTPRequest("http://localhost:9999", false))
	if code := ErrorCode(err); code != "LLM_PROVIDER_TIMEOUT" || attempts != 1 {
		t.Fatalf("timeout must be stable and terminal: code=%s attempts=%d err=%v", code, attempts, err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = executor.Execute(ctx, providerHTTPRequest("http://localhost:9999", false))
	if code := ErrorCode(err); code != "LLM_PROVIDER_CANCELLED" {
		t.Fatalf("cancel must be stable: code=%s err=%v", code, err)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

func TestProductionProviderCallServiceFinalizesSuccessAndReleasesFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}`))
	}))
	defer server.Close()
	quota := &recordingProviderQuotaStore{}
	leases := &recordingProviderLeaseManager{lease: ProviderCallLease{LeaseID: "lease-1", ExpiresAt: time.Now().Add(time.Minute)}}
	service := NewProductionProviderCallService(quota, leases, configuredProviderExecutor(server.Client()))
	input := productionProviderInput(server.URL)
	inputRate, outputRate := int64(2), int64(4)
	input.InputMicrosPerToken, input.OutputMicrosPerToken = &inputRate, &outputRate

	_, err := service.Execute(context.Background(), input)
	if err != nil {
		t.Fatalf("production provider call: %v", err)
	}
	if quota.finalizeCalls != 1 || quota.releaseCalls != 0 || quota.finalize.CostMicros == nil || *quota.finalize.CostMicros != 14 {
		t.Fatalf("success did not finalize measured usage exactly: %#v", quota)
	}

	quota = &recordingProviderQuotaStore{}
	service = NewProductionProviderCallService(quota, leases, configuredProviderExecutor(&http.Client{Transport: failingRoundTripper{}}))
	_, err = service.Execute(context.Background(), productionProviderInput("http://localhost:9"))
	if code := ErrorCode(err); code != "LLM_PROVIDER_UNAVAILABLE" || quota.finalizeCalls != 0 || quota.releaseCalls != 1 {
		t.Fatalf("failed call must release without usage: code=%s quota=%#v", code, quota)
	}
}

func TestProductionProviderCallServiceFinalizesSuccessfulUsageBeforeSurfacingLeaseReleaseFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"usage":{"prompt_tokens":2,"completion_tokens":3}}`))
	}))
	defer server.Close()
	quota := &recordingProviderQuotaStore{}
	leases := &recordingProviderLeaseManager{
		lease:      ProviderCallLease{LeaseID: "lease-1", ExpiresAt: time.Now().Add(time.Minute)},
		releaseErr: errors.New("credential=private"),
	}
	service := NewProductionProviderCallService(quota, leases, configuredProviderExecutor(server.Client()))

	_, err := service.Execute(context.Background(), productionProviderInput(server.URL))
	if code := ErrorCode(err); code != "LLM_CONCURRENCY_RELEASE_FAILED" || quota.finalizeCalls != 1 || quota.releaseCalls != 0 {
		t.Fatalf("successful provider usage was lost: code=%s quota=%#v err=%v", code, quota, err)
	}
}

func TestSensitiveFieldScannerFindsNestedSecretsWithoutPrintingValues(t *testing.T) {
	if !ContainsSensitiveFields(map[string]any{"safe": []any{map[string]any{"response_body": "private"}}}) {
		t.Fatal("nested sensitive field was not detected")
	}
	if ContainsSensitiveFields(map[string]any{"provider_call_id": "call-1", "model_id": "gpt-test", "tokens": 3}) {
		t.Fatal("public billing metadata was incorrectly marked sensitive")
	}
	err := stableProviderCallError(errors.New("authorization: Bearer secret prompt=private"))
	if strings.Contains(strings.ToLower(err.Error()), "secret") || strings.Contains(strings.ToLower(err.Error()), "prompt") {
		t.Fatalf("stable provider error leaked sensitive fields: %v", err)
	}
}

func TestQuotaAndCostArithmeticFailClosedOnIntegerOverflow(t *testing.T) {
	if !exceedsQuotaLimit(1<<63-1, 1<<63-2, 1<<63-2, 2) {
		t.Fatal("quota arithmetic overflow was not rejected")
	}
	rate := int64(1)
	_, err := actualCostMicros(ProviderHTTPResult{PromptTokens: 1<<63 - 2, CompletionTokens: 2}, &rate, &rate)
	if code := ErrorCode(err); code != "LLM_MODEL_PRICING_INVALID" {
		t.Fatalf("cost arithmetic overflow: code=%s err=%v", code, err)
	}
}

func configuredProviderExecutor(client *http.Client) *ProviderHTTPExecutor {
	return NewProviderHTTPExecutor(ProviderHTTPConfig{
		Client: client, Timeout: time.Second, MaxAttempts: 1, RetryDelay: 0, MaxResponseBytes: 1 << 20,
	})
}

func providerHTTPRequest(baseURL string, external bool) ProviderHTTPRequest {
	return ProviderHTTPRequest{
		BaseURL: baseURL, Path: "/chat/completions", APIKey: "test-only-key",
		ProviderCallID: "provider-call-1", ExternalProviderOptIn: external, Body: []byte(`{"model":"test"}`),
	}
}

func productionProviderInput(baseURL string) ProductionProviderCallInput {
	return ProductionProviderCallInput{
		Lease:   ProviderCallLeaseInput{TenantID: "tenant-1", ProjectID: "project-1", RunID: "run-1", ModuleKey: "writer_composer", ChannelID: "channel-1"},
		ModelID: "model-1", ProviderCallID: "provider-call-1", ReservedTokens: 20,
		ReservedCostMicros: 100, ReservationTTL: time.Minute, HTTP: providerHTTPRequest(baseURL, false),
	}
}

type recordingProviderQuotaStore struct {
	reserveCalls  int
	finalizeCalls int
	releaseCalls  int
	finalize      QuotaFinalizeInput
}

func (s *recordingProviderQuotaStore) Reserve(context.Context, QuotaReservationInput) (QuotaReservation, error) {
	s.reserveCalls++
	return QuotaReservation{ReservationID: "reservation-1", ProviderCallID: "provider-call-1", ExpiresAt: time.Now().Add(time.Minute)}, nil
}

func (s *recordingProviderQuotaStore) Finalize(_ context.Context, input QuotaFinalizeInput) error {
	s.finalizeCalls++
	s.finalize = input
	return nil
}

func (s *recordingProviderQuotaStore) Release(context.Context, string, string) error {
	s.releaseCalls++
	return nil
}

type failingRoundTripper struct{}

func (failingRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	return nil, errors.New("api_key=secret prompt=private")
}
