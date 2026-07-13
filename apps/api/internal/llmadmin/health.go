package llmadmin

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type HealthAudit struct {
	TenantID      string
	ActorUserID   string
	ChannelID     string
	ModelID       string
	Status        string
	StatusCode    int
	LatencyMS     int64
	SupportsTools bool
	SupportsJSON  bool
	CheckedAt     time.Time
	RequestID     string
}

type HealthRecorder interface {
	RecordHealth(context.Context, HealthAudit) error
}

type HealthMetrics interface {
	SetProviderHealth(channelID string, healthy bool)
}

type HTTPHealthExecutor struct {
	client           *http.Client
	timeout          time.Duration
	maxResponseBytes int64
	resolver         healthDNSResolver
	dialContext      func(context.Context, string, string) (net.Conn, error)
}

type healthDNSResolver interface {
	LookupIPAddr(context.Context, string) ([]net.IPAddr, error)
}

func NewHTTPHealthExecutor(client *http.Client, timeout time.Duration, maxResponseBytes int64) *HTTPHealthExecutor {
	return &HTTPHealthExecutor{
		client: client, timeout: timeout, maxResponseBytes: maxResponseBytes,
		resolver: net.DefaultResolver, dialContext: (&net.Dialer{}).DialContext,
	}
}

func (e *HTTPHealthExecutor) ExecuteHealth(ctx context.Context, input HealthRequest) (HealthExecution, error) {
	if e == nil || e.client == nil || e.timeout <= 0 || e.maxResponseBytes <= 0 || strings.TrimSpace(input.APIKey) == "" || len(input.Body) == 0 {
		return HealthExecution{}, &AppError{Code: "LLM_PROVIDER_HEALTH_UNCONFIGURED", Message: "LLM provider health check is not configured"}
	}
	if err := validateHealthEndpoint(input.BaseURL, input.ExternalProviderOptIn); err != nil {
		return HealthExecution{}, err
	}
	endpoint, err := url.JoinPath(strings.TrimRight(input.BaseURL, "/"), "chat/completions")
	if err != nil {
		return HealthExecution{}, &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
	}
	callCtx, cancel := context.WithTimeout(ctx, e.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(callCtx, http.MethodPost, endpoint, bytes.NewReader(input.Body))
	if err != nil {
		return HealthExecution{}, &AppError{Code: "LLM_PROVIDER_HEALTH_FAILED", Message: "LLM provider health check failed"}
	}
	request.Header.Set("Authorization", "Bearer "+input.APIKey)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", input.ProviderCallID)
	client, err := e.clientForEndpoint(callCtx, endpoint)
	if err != nil {
		return HealthExecution{}, err
	}
	response, err := client.Do(request)
	if err != nil {
		return HealthExecution{}, &AppError{Code: "LLM_PROVIDER_HEALTH_FAILED", Message: "LLM provider health check failed"}
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, e.maxResponseBytes+1))
	if err != nil || int64(len(body)) > e.maxResponseBytes {
		return HealthExecution{}, &AppError{Code: "LLM_PROVIDER_HEALTH_FAILED", Message: "LLM provider health check failed"}
	}
	return HealthExecution{StatusCode: response.StatusCode}, nil
}

func (e *HTTPHealthExecutor) clientForEndpoint(ctx context.Context, endpoint string) (*http.Client, error) {
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Hostname() == "" || e.resolver == nil || e.dialContext == nil {
		return nil, networkTargetForbidden()
	}
	baseTransport := e.client.Transport
	if baseTransport == nil {
		baseTransport = http.DefaultTransport
	}
	transport, ok := baseTransport.(*http.Transport)
	if !ok {
		return nil, networkTargetForbidden()
	}
	pinnedIP, err := e.resolvePinnedIP(ctx, parsed.Hostname())
	if err != nil {
		return nil, err
	}
	port := parsed.Port()
	if port == "" {
		port = "443"
		if parsed.Scheme == "http" {
			port = "80"
		}
	}
	expectedHost := strings.ToLower(parsed.Hostname())
	clone := transport.Clone()
	clone.Proxy = nil
	clone.DialContext = func(callCtx context.Context, network, address string) (net.Conn, error) {
		host, requestedPort, err := net.SplitHostPort(address)
		if err != nil || !strings.EqualFold(strings.Trim(host, "[]"), expectedHost) || requestedPort != port {
			return nil, networkTargetForbidden()
		}
		return e.dialContext(callCtx, network, net.JoinHostPort(pinnedIP.String(), port))
	}
	client := *e.client
	client.Transport = clone
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return &client, nil
}

func (e *HTTPHealthExecutor) resolvePinnedIP(ctx context.Context, host string) (net.IP, error) {
	local := healthLocalHost(host)
	addresses := []net.IPAddr{}
	if parsed := net.ParseIP(host); parsed != nil {
		addresses = append(addresses, net.IPAddr{IP: parsed})
	} else {
		resolved, err := e.resolver.LookupIPAddr(ctx, host)
		if err != nil {
			return nil, networkTargetForbidden()
		}
		addresses = resolved
	}
	if len(addresses) == 0 {
		return nil, networkTargetForbidden()
	}
	for _, address := range addresses {
		if !allowedHealthIP(address.IP, local) {
			return nil, networkTargetForbidden()
		}
	}
	return addresses[0].IP, nil
}

func allowedHealthIP(ip net.IP, local bool) bool {
	if ip == nil {
		return false
	}
	if local {
		return ip.IsLoopback()
	}
	return ip.IsGlobalUnicast() && !ip.IsLoopback() && !ip.IsPrivate() &&
		!ip.IsLinkLocalUnicast() && !ip.IsLinkLocalMulticast() && !ip.IsUnspecified() && !ip.IsMulticast()
}

func networkTargetForbidden() error {
	return &AppError{Code: "LLM_PROVIDER_NETWORK_TARGET_FORBIDDEN", Message: "LLM provider network target is not allowed"}
}

type SQLHealthRecorder struct{ db *sql.DB }

func NewSQLHealthRecorder(db *sql.DB) *SQLHealthRecorder { return &SQLHealthRecorder{db: db} }

func (r *SQLHealthRecorder) RecordHealth(ctx context.Context, audit HealthAudit) error {
	if r == nil || r.db == nil || strings.TrimSpace(audit.TenantID) == "" || strings.TrimSpace(audit.ChannelID) == "" {
		return backendError()
	}
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return backendError()
	}
	defer tx.Rollback()
	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)", audit.TenantID, audit.ActorUserID); err != nil {
		return backendError()
	}
	metadata, err := json.Marshal(map[string]any{
		"model_id": audit.ModelID, "status": audit.Status, "status_code": audit.StatusCode,
		"latency_ms": audit.LatencyMS, "supports_tools": audit.SupportsTools, "supports_json": audit.SupportsJSON,
	})
	if err != nil {
		return backendError()
	}
	_, err = tx.ExecContext(ctx, `INSERT INTO audit_logs (
 tenant_id, actor_user_id, action, resource_type, resource_id, request_id, metadata_jsonb
) VALUES ($1, NULLIF($2, '')::uuid, 'llm.provider_health.checked', 'llm_channel', $3::uuid, $4, $5::jsonb)`,
		audit.TenantID, audit.ActorUserID, audit.ChannelID, audit.RequestID, metadata)
	if err != nil {
		return backendError()
	}
	if err := tx.Commit(); err != nil {
		return backendError()
	}
	return nil
}

type HealthService struct {
	resolver HealthCredentialResolver
	executor HealthExecutor
	recorder HealthRecorder
	metrics  HealthMetrics
	now      func() time.Time
}

func NewHealthService(resolver HealthCredentialResolver, executor HealthExecutor, recorder HealthRecorder) *HealthService {
	return &HealthService{resolver: resolver, executor: executor, recorder: recorder, now: time.Now}
}

func (s *HealthService) WithMetrics(metrics HealthMetrics) *HealthService {
	if s != nil {
		s.metrics = metrics
	}
	return s
}

func (s *HealthService) Check(ctx context.Context, tenantID, actorID, projectID, channelID, modelID, requestID string) (HealthResult, error) {
	if s == nil || s.resolver == nil || s.executor == nil {
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_UNCONFIGURED", Message: "LLM provider health check is not configured"}
	}
	if strings.TrimSpace(channelID) == "" || strings.TrimSpace(modelID) == "" {
		return HealthResult{}, validationError()
	}
	target, err := s.resolver.ResolveHealthTarget(ctx, tenantID, projectID, channelID, modelID)
	if err != nil {
		s.setProviderHealth(channelID, false)
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE", Message: "LLM provider health target is unavailable"}
	}
	if target.ChannelID != channelID || target.ModelID != modelID || strings.TrimSpace(target.APIKey) == "" {
		s.setProviderHealth(channelID, false)
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_TARGET_INVALID", Message: "LLM provider health target is invalid"}
	}
	if err := validateHealthEndpoint(target.BaseURL, target.ExternalProviderOptIn); err != nil {
		s.setProviderHealth(channelID, false)
		return HealthResult{}, err
	}
	body, err := json.Marshal(map[string]any{
		"model":      target.ModelID,
		"messages":   []map[string]string{{"role": "user", "content": "health"}},
		"max_tokens": 1,
		"stream":     false,
	})
	if err != nil {
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_REQUEST_FAILED", Message: "LLM provider health request failed"}
	}
	started := s.currentTime()
	execution, err := s.executor.ExecuteHealth(ctx, HealthRequest{
		BaseURL: target.BaseURL, APIKey: target.APIKey, ModelID: target.ModelID,
		ExternalProviderOptIn: target.ExternalProviderOptIn, ProviderCallID: requestID, Body: body,
	})
	checkedAt := s.currentTime()
	result := HealthResult{ChannelID: channelID, ModelID: modelID, Status: "healthy", StatusCode: execution.StatusCode,
		LatencyMS: checkedAt.Sub(started).Milliseconds(), SupportsTools: target.SupportsTools,
		SupportsJSON: target.SupportsJSON, CheckedAt: checkedAt}
	if err != nil {
		result.Status = "unhealthy"
		result.StatusCode = 0
		s.setProviderHealth(channelID, false)
		_ = s.record(ctx, tenantID, actorID, requestID, result)
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_FAILED", Message: "LLM provider health check failed"}
	}
	if result.StatusCode < 200 || result.StatusCode >= 300 {
		result.Status = "unhealthy"
		s.setProviderHealth(channelID, false)
		_ = s.record(ctx, tenantID, actorID, requestID, result)
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_FAILED", Message: "LLM provider health check failed"}
	}
	s.setProviderHealth(channelID, true)
	if err := s.record(ctx, tenantID, actorID, requestID, result); err != nil {
		return HealthResult{}, &AppError{Code: "LLM_PROVIDER_HEALTH_AUDIT_FAILED", Message: "LLM provider health audit failed"}
	}
	return result, nil
}

func (s *HealthService) setProviderHealth(channelID string, healthy bool) {
	if s.metrics != nil {
		s.metrics.SetProviderHealth(channelID, healthy)
	}
}

func (s *HealthService) record(ctx context.Context, tenantID, actorID, requestID string, result HealthResult) error {
	if s.recorder == nil {
		return nil
	}
	return s.recorder.RecordHealth(ctx, HealthAudit{TenantID: tenantID, ActorUserID: actorID, ChannelID: result.ChannelID,
		ModelID: result.ModelID, Status: result.Status, StatusCode: result.StatusCode, LatencyMS: result.LatencyMS,
		SupportsTools: result.SupportsTools, SupportsJSON: result.SupportsJSON, CheckedAt: result.CheckedAt, RequestID: requestID})
}

func (s *HealthService) currentTime() time.Time {
	if s.now != nil {
		return s.now().UTC()
	}
	return time.Now().UTC()
}

func validateHealthEndpoint(raw string, externalOptIn bool) error {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
	}
	local := healthLocalHost(parsed.Hostname())
	if local {
		if parsed.Scheme != "http" && parsed.Scheme != "https" {
			return &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
		}
		return nil
	}
	if parsed.Scheme != "https" {
		return &AppError{Code: "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED", Message: "External LLM providers require HTTPS"}
	}
	if !externalOptIn {
		return &AppError{Code: "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED", Message: "External LLM provider access is not enabled"}
	}
	return nil
}

func healthLocalHost(host string) bool {
	host = strings.TrimSpace(strings.ToLower(host))
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
