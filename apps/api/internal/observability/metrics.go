package observability

import (
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
)

const prometheusContentType = "text/plain; version=0.0.4; charset=utf-8"

type Registry struct {
	mu                          sync.RWMutex
	httpRequests                map[int]uint64
	workflowTerminals           map[string]uint64
	providerHealth              map[string]bool
	authRecoveryDelivery        map[string]uint64
	quotaReconciliationFailures uint64
}

func NewRegistry() *Registry {
	return &Registry{
		httpRequests:         make(map[int]uint64),
		workflowTerminals:    make(map[string]uint64),
		providerHealth:       make(map[string]bool),
		authRecoveryDelivery: make(map[string]uint64),
	}
}

func (r *Registry) Handler() http.Handler { return http.HandlerFunc(r.serveMetrics) }

func (r *Registry) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if next == nil {
			http.Error(response, "service is unavailable", http.StatusServiceUnavailable)
			r.RecordHTTPRequest(http.StatusServiceUnavailable)
			return
		}
		tracked := &statusWriter{ResponseWriter: response, status: http.StatusOK}
		next.ServeHTTP(tracked, request)
		r.RecordHTTPRequest(tracked.status)
	})
}

func (r *Registry) RecordHTTPRequest(status int) {
	if r == nil || status < 100 || status > 599 {
		return
	}
	r.mu.Lock()
	r.httpRequests[status]++
	r.mu.Unlock()
}

func (r *Registry) RecordWorkflowTerminal(status string) {
	if r == nil {
		return
	}
	status = strings.ToLower(strings.TrimSpace(status))
	if status != "completed" && status != "failed" && status != "cancelled" {
		return
	}
	r.mu.Lock()
	r.workflowTerminals[status]++
	r.mu.Unlock()
}

func (r *Registry) SetProviderHealth(channelID string, healthy bool) {
	if r == nil || strings.TrimSpace(channelID) == "" {
		return
	}
	r.mu.Lock()
	r.providerHealth[channelID] = healthy
	r.mu.Unlock()
}

func (r *Registry) RecordQuotaReconciliationFailure() {
	if r == nil {
		return
	}
	r.mu.Lock()
	r.quotaReconciliationFailures++
	r.mu.Unlock()
}

func (r *Registry) RecordAuthRecoveryDelivery(status string) {
	if r == nil {
		return
	}
	status = strings.ToLower(strings.TrimSpace(status))
	if status != "delivered" && status != "retry" && status != "dead" && status != "backend_error" {
		return
	}
	r.mu.Lock()
	r.authRecoveryDelivery[status]++
	r.mu.Unlock()
}

func (r *Registry) serveMetrics(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Cache-Control", "no-store")
	response.Header().Set("Content-Type", prometheusContentType)
	if request.Method != http.MethodGet && request.Method != http.MethodHead {
		response.Header().Set("Allow", "GET, HEAD")
		response.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	body := r.snapshot()
	response.Header().Set("Content-Length", strconv.Itoa(len(body)))
	if request.Method == http.MethodHead {
		return
	}
	_, _ = response.Write([]byte(body))
}

func (r *Registry) snapshot() string {
	if r == nil {
		return ""
	}
	r.mu.RLock()
	statuses := make([]int, 0, len(r.httpRequests))
	for status := range r.httpRequests {
		statuses = append(statuses, status)
	}
	sort.Ints(statuses)
	workflow := make(map[string]uint64, len(r.workflowTerminals))
	for status, count := range r.workflowTerminals {
		workflow[status] = count
	}
	providerConfigured := len(r.providerHealth) > 0
	providersHealthy := true
	for _, healthy := range r.providerHealth {
		providersHealthy = providersHealthy && healthy
	}
	quotaFailures := r.quotaReconciliationFailures
	recoveryDelivery := make(map[string]uint64, len(r.authRecoveryDelivery))
	for status, count := range r.authRecoveryDelivery {
		recoveryDelivery[status] = count
	}
	httpCounts := make(map[int]uint64, len(r.httpRequests))
	for status, count := range r.httpRequests {
		httpCounts[status] = count
	}
	r.mu.RUnlock()

	var output strings.Builder
	output.WriteString("# HELP mirofish_http_requests_total HTTP requests completed by status code.\n")
	output.WriteString("# TYPE mirofish_http_requests_total counter\n")
	for _, status := range statuses {
		fmt.Fprintf(&output, "mirofish_http_requests_total{status=\"%d\"} %d\n", status, httpCounts[status])
	}
	output.WriteString("# HELP mirofish_workflow_terminal_total Workflows entering a terminal state.\n")
	output.WriteString("# TYPE mirofish_workflow_terminal_total counter\n")
	for _, status := range []string{"cancelled", "completed", "failed"} {
		if count, ok := workflow[status]; ok {
			fmt.Fprintf(&output, "mirofish_workflow_terminal_total{status=\"%s\"} %d\n", status, count)
		}
	}
	output.WriteString("# HELP mirofish_llm_provider_health Whether every checked enabled LLM provider is healthy.\n")
	output.WriteString("# TYPE mirofish_llm_provider_health gauge\n")
	if providerConfigured {
		value := 0
		if providersHealthy {
			value = 1
		}
		fmt.Fprintf(&output, "mirofish_llm_provider_health %d\n", value)
	}
	output.WriteString("# HELP mirofish_llm_quota_reconciliation_failures_total LLM quota reconciliation backend failures.\n")
	output.WriteString("# TYPE mirofish_llm_quota_reconciliation_failures_total counter\n")
	fmt.Fprintf(&output, "mirofish_llm_quota_reconciliation_failures_total %d\n", quotaFailures)
	output.WriteString("# HELP mirofish_auth_recovery_delivery_total Password recovery delivery outcomes.\n")
	output.WriteString("# TYPE mirofish_auth_recovery_delivery_total counter\n")
	for _, status := range []string{"backend_error", "dead", "delivered", "retry"} {
		if count, ok := recoveryDelivery[status]; ok {
			fmt.Fprintf(&output, "mirofish_auth_recovery_delivery_total{status=\"%s\"} %d\n", status, count)
		}
	}
	return output.String()
}

type statusWriter struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (w *statusWriter) WriteHeader(status int) {
	if w.wroteHeader {
		return
	}
	w.wroteHeader = true
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

func (w *statusWriter) Write(body []byte) (int, error) {
	if !w.wroteHeader {
		w.WriteHeader(http.StatusOK)
	}
	return w.ResponseWriter.Write(body)
}

func (w *statusWriter) FlushError() error {
	if !w.wroteHeader {
		w.WriteHeader(http.StatusOK)
	}
	return http.NewResponseController(w.ResponseWriter).Flush()
}

func (w *statusWriter) Unwrap() http.ResponseWriter { return w.ResponseWriter }
