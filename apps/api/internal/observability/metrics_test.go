package observability

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func TestMetricsHandlerExposesAlertRuleSeriesWithoutSensitiveLabels(t *testing.T) {
	registry := NewRegistry()
	registry.RecordHTTPRequest(http.StatusOK)
	registry.RecordHTTPRequest(http.StatusInternalServerError)
	registry.RecordWorkflowTerminal("completed")
	registry.RecordWorkflowTerminal("failed")
	registry.SetProviderHealth("private-channel-id", true)
	registry.SetProviderHealth("other-private-channel-id", false)
	registry.RecordQuotaReconciliationFailure()
	registry.RecordAuthRecoveryDelivery("delivered")
	registry.RecordAuthRecoveryDelivery("retry")
	registry.RecordAuthRecoveryDelivery("private-id")

	response := httptest.NewRecorder()
	registry.Handler().ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	if response.Code != http.StatusOK || response.Header().Get("Content-Type") != prometheusContentType {
		t.Fatalf("metrics response mismatch: %d %#v", response.Code, response.Header())
	}
	body := response.Body.String()
	for _, expected := range []string{
		`mirofish_http_requests_total{status="200"} 1`,
		`mirofish_http_requests_total{status="500"} 1`,
		`mirofish_workflow_terminal_total{status="completed"} 1`,
		`mirofish_workflow_terminal_total{status="failed"} 1`,
		"mirofish_llm_provider_health 0",
		"mirofish_llm_quota_reconciliation_failures_total 1",
		"mirofish_auth_recovery_delivery_total{status=\"delivered\"} 1",
		"mirofish_auth_recovery_delivery_total{status=\"retry\"} 1",
	} {
		if !strings.Contains(body, expected) {
			t.Fatalf("metrics missing %q:\n%s", expected, body)
		}
	}
	if strings.Contains(body, "private-id") {
		t.Fatal("metrics exposed an unbounded recovery delivery label")
	}
	for _, forbidden := range []string{"private-channel-id", "tenant", "project", "api_key", "credential", "prompt", "response"} {
		if strings.Contains(strings.ToLower(body), forbidden) {
			t.Fatalf("metrics leaked forbidden text %q:\n%s", forbidden, body)
		}
	}
}

func TestHTTPMiddlewareRecordsFinalStatusAndSupportsResponseController(t *testing.T) {
	registry := NewRegistry()
	wrapped := registry.Middleware(http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		if err := http.NewResponseController(response).Flush(); err != nil {
			t.Fatalf("wrapped response lost flush support: %v", err)
		}
		response.WriteHeader(http.StatusCreated)
	}))
	wrapped.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(http.MethodPost, "/v1/projects/private-id", nil))
	body := registry.snapshot()
	if !strings.Contains(body, `mirofish_http_requests_total{status="200"} 1`) {
		t.Fatalf("middleware did not preserve the first committed status:\n%s", body)
	}
	if strings.Contains(body, "private-id") {
		t.Fatalf("middleware exposed request path: %s", body)
	}
}

func TestRegistryUpdatesAreConcurrencySafeAndMetricsMethodsAreBounded(t *testing.T) {
	registry := NewRegistry()
	var group sync.WaitGroup
	for index := 0; index < 100; index++ {
		group.Add(1)
		go func() {
			defer group.Done()
			registry.RecordHTTPRequest(http.StatusTooManyRequests)
			registry.RecordWorkflowTerminal("FAILED")
			registry.RecordQuotaReconciliationFailure()
		}()
	}
	group.Wait()
	registry.RecordHTTPRequest(999)
	registry.RecordWorkflowTerminal("running")
	body := registry.snapshot()
	for _, expected := range []string{
		`mirofish_http_requests_total{status="429"} 100`,
		`mirofish_workflow_terminal_total{status="failed"} 100`,
		"mirofish_llm_quota_reconciliation_failures_total 100",
	} {
		if !strings.Contains(body, expected) {
			t.Fatalf("concurrent metric mismatch %q:\n%s", expected, body)
		}
	}
}

func TestMetricsHandlerHEADAndMethodGuard(t *testing.T) {
	registry := NewRegistry()
	head := httptest.NewRecorder()
	registry.Handler().ServeHTTP(head, httptest.NewRequest(http.MethodHead, "/metrics", nil))
	if head.Code != http.StatusOK || head.Body.Len() != 0 || head.Header().Get("Content-Length") == "" {
		t.Fatalf("HEAD response mismatch: %d %#v %q", head.Code, head.Header(), head.Body.String())
	}
	post := httptest.NewRecorder()
	registry.Handler().ServeHTTP(post, httptest.NewRequest(http.MethodPost, "/metrics", nil))
	if post.Code != http.StatusMethodNotAllowed || post.Header().Get("Allow") != "GET, HEAD" {
		t.Fatalf("method guard mismatch: %d %#v", post.Code, post.Header())
	}
}
