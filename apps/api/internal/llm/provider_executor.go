package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type ProviderHTTPConfig struct {
	Client           *http.Client
	Timeout          time.Duration
	MaxAttempts      int
	RetryDelay       time.Duration
	MaxResponseBytes int64
}

type ProviderHTTPRequest struct {
	BaseURL               string
	Path                  string
	APIKey                string
	ProviderCallID        string
	ExternalProviderOptIn bool
	Body                  []byte
}

type ProviderHTTPResult struct {
	StatusCode       int
	Body             []byte
	PromptTokens     int64
	CompletionTokens int64
}

type ProviderHTTPExecutor struct {
	config ProviderHTTPConfig
	sleep  func(context.Context, time.Duration) error
}

func NewProviderHTTPExecutor(config ProviderHTTPConfig) *ProviderHTTPExecutor {
	return &ProviderHTTPExecutor{config: config, sleep: sleepWithContext}
}

func (e *ProviderHTTPExecutor) Execute(ctx context.Context, input ProviderHTTPRequest) (ProviderHTTPResult, error) {
	if err := validateProviderHTTPConfig(e); err != nil {
		return ProviderHTTPResult{}, err
	}
	endpoint, err := validateProviderEndpoint(input.BaseURL, input.Path, input.ExternalProviderOptIn)
	if err != nil {
		return ProviderHTTPResult{}, err
	}
	if strings.TrimSpace(input.APIKey) == "" || strings.TrimSpace(input.ProviderCallID) == "" || len(input.Body) == 0 {
		return ProviderHTTPResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "LLM provider request is incomplete"}
	}
	for attempt := 1; attempt <= e.config.MaxAttempts; attempt++ {
		result, callErr := e.executeAttempt(ctx, endpoint, input)
		if callErr == nil {
			return result, nil
		}
		if !providerAttemptRetryable(callErr) || attempt == e.config.MaxAttempts {
			return ProviderHTTPResult{}, callErr
		}
		if err := e.sleep(ctx, e.config.RetryDelay); err != nil {
			return ProviderHTTPResult{}, stableProviderContextError(err)
		}
	}
	return ProviderHTTPResult{}, &AppError{Code: "LLM_PROVIDER_ERROR", Message: "LLM provider call failed"}
}

func (e *ProviderHTTPExecutor) executeAttempt(ctx context.Context, endpoint string, input ProviderHTTPRequest) (ProviderHTTPResult, error) {
	callCtx, cancel := context.WithTimeout(ctx, e.config.Timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(callCtx, http.MethodPost, endpoint, bytes.NewReader(input.Body))
	if err != nil {
		return ProviderHTTPResult{}, &AppError{Code: "LLM_PROVIDER_REQUEST_INVALID", Message: "LLM provider request is invalid"}
	}
	req.Header.Set("Authorization", "Bearer "+input.APIKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", input.ProviderCallID)
	response, err := e.config.Client.Do(req)
	if err != nil {
		return ProviderHTTPResult{}, stableProviderContextError(err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, e.config.MaxResponseBytes+1))
	if err != nil {
		return ProviderHTTPResult{}, &AppError{Code: "LLM_PROVIDER_UNAVAILABLE", Message: "LLM provider is unavailable"}
	}
	if int64(len(body)) > e.config.MaxResponseBytes {
		return ProviderHTTPResult{}, &AppError{Code: "LLM_PROVIDER_RESPONSE_TOO_LARGE", Message: "LLM provider response exceeded the configured limit"}
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return ProviderHTTPResult{}, providerStatusError(response.StatusCode)
	}
	promptTokens, completionTokens, err := decodeOpenAIUsage(body)
	if err != nil {
		return ProviderHTTPResult{}, err
	}
	return ProviderHTTPResult{
		StatusCode: response.StatusCode, Body: body,
		PromptTokens: promptTokens, CompletionTokens: completionTokens,
	}, nil
}

func validateProviderHTTPConfig(executor *ProviderHTTPExecutor) error {
	if executor == nil || executor.config.Client == nil || executor.config.Timeout <= 0 ||
		executor.config.MaxAttempts <= 0 || executor.config.RetryDelay < 0 || executor.config.MaxResponseBytes <= 0 {
		return &AppError{Code: "LLM_PROVIDER_CONFIG_INVALID", Message: "LLM provider execution policy is invalid"}
	}
	return nil
}

func validateProviderEndpoint(baseURL, path string, externalOptIn bool) (string, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
	}
	host := parsed.Hostname()
	local := localOrClusterHost(host)
	if local {
		if parsed.Scheme != "http" && parsed.Scheme != "https" {
			return "", &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
		}
	} else if parsed.Scheme != "https" {
		return "", &AppError{Code: "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED", Message: "External LLM providers require HTTPS"}
	} else if !externalOptIn {
		return "", &AppError{Code: "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED", Message: "External LLM provider access is not enabled"}
	}
	joined, err := url.JoinPath(strings.TrimRight(parsed.String(), "/"), strings.TrimLeft(path, "/"))
	if err != nil {
		return "", &AppError{Code: "LLM_PROVIDER_URL_INVALID", Message: "LLM provider URL is invalid"}
	}
	return joined, nil
}

func localOrClusterHost(host string) bool {
	host = strings.TrimSpace(strings.ToLower(host))
	if host == "localhost" || host == "host.docker.internal" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func providerStatusError(status int) error {
	switch status {
	case http.StatusTooManyRequests:
		return &AppError{Code: "LLM_PROVIDER_RATE_LIMITED", Message: "LLM provider rate limit reached"}
	case http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return &AppError{Code: "LLM_PROVIDER_UNAVAILABLE", Message: "LLM provider is unavailable"}
	case http.StatusRequestTimeout:
		return &AppError{Code: "LLM_PROVIDER_TIMEOUT", Message: "LLM provider request timed out"}
	default:
		return &AppError{Code: "LLM_PROVIDER_REJECTED", Message: fmt.Sprintf("LLM provider rejected the request with status %d", status)}
	}
}

func providerAttemptRetryable(err error) bool {
	code := ErrorCode(err)
	return code == "LLM_PROVIDER_RATE_LIMITED" || code == "LLM_PROVIDER_UNAVAILABLE"
}

func stableProviderContextError(err error) error {
	if errors.Is(err, context.Canceled) {
		return &AppError{Code: "LLM_PROVIDER_CANCELLED", Message: "LLM provider request was cancelled"}
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return &AppError{Code: "LLM_PROVIDER_TIMEOUT", Message: "LLM provider request timed out"}
	}
	return &AppError{Code: "LLM_PROVIDER_UNAVAILABLE", Message: "LLM provider is unavailable"}
}

func sleepWithContext(ctx context.Context, delay time.Duration) error {
	if delay == 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func decodeOpenAIUsage(body []byte) (int64, int64, error) {
	var envelope struct {
		Usage *struct {
			PromptTokens     int64 `json:"prompt_tokens"`
			CompletionTokens int64 `json:"completion_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil || envelope.Usage == nil ||
		envelope.Usage.PromptTokens < 0 || envelope.Usage.CompletionTokens < 0 {
		return 0, 0, &AppError{Code: "LLM_PROVIDER_USAGE_MISSING", Message: "LLM provider did not return valid usage"}
	}
	return envelope.Usage.PromptTokens, envelope.Usage.CompletionTokens, nil
}

type ProviderQuotaStore interface {
	Reserve(context.Context, QuotaReservationInput) (QuotaReservation, error)
	Finalize(context.Context, QuotaFinalizeInput) error
	Release(context.Context, string, string) error
}

type ProductionProviderCallInput struct {
	Lease                ProviderCallLeaseInput
	ModelID              string
	ProviderCallID       string
	ReservedTokens       int64
	ReservedCostMicros   int64
	ReservationTTL       time.Duration
	HTTP                 ProviderHTTPRequest
	InputMicrosPerToken  *int64
	OutputMicrosPerToken *int64
}

type ProductionProviderCallService struct {
	quota    ProviderQuotaStore
	leases   ProviderCallLeaseManager
	executor *ProviderHTTPExecutor
}

func NewProductionProviderCallService(quota ProviderQuotaStore, leases ProviderCallLeaseManager, executor *ProviderHTTPExecutor) *ProductionProviderCallService {
	return &ProductionProviderCallService{quota: quota, leases: leases, executor: executor}
}

func (s *ProductionProviderCallService) Execute(ctx context.Context, input ProductionProviderCallInput) (ProviderHTTPResult, error) {
	if s == nil || s.quota == nil || s.leases == nil || s.executor == nil {
		return ProviderHTTPResult{}, &AppError{Code: "LLM_PROVIDER_GATE_UNCONFIGURED", Message: "LLM provider gate is not configured"}
	}
	if err := validateProviderCallGateInput(input.Lease, func(context.Context) error { return nil }); err != nil ||
		strings.TrimSpace(input.ModelID) == "" || strings.TrimSpace(input.ProviderCallID) == "" ||
		strings.TrimSpace(input.HTTP.ProviderCallID) != strings.TrimSpace(input.ProviderCallID) {
		return ProviderHTTPResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "provider call context is incomplete"}
	}
	reservation, err := s.quota.Reserve(ctx, QuotaReservationInput{
		TenantID: input.Lease.TenantID, ProjectID: input.Lease.ProjectID, RunID: input.Lease.RunID,
		ModuleKey: input.Lease.ModuleKey, ChannelID: input.Lease.ChannelID, ModelID: input.ModelID,
		ProviderCallID: input.ProviderCallID, ReservedTokens: input.ReservedTokens,
		ReservedCostMicros: input.ReservedCostMicros, TTL: input.ReservationTTL,
	})
	if err != nil {
		return ProviderHTTPResult{}, err
	}
	lease, err := s.leases.Acquire(ctx, input.Lease)
	if err != nil {
		return ProviderHTTPResult{}, combineReleaseError(stableLeaseAcquireError(err), s.releaseReservation(input, reservation))
	}
	if strings.TrimSpace(lease.LeaseID) == "" || lease.ExpiresAt.IsZero() || !lease.ExpiresAt.After(time.Now()) {
		var leaseErr error
		if strings.TrimSpace(lease.LeaseID) != "" {
			releaseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
			leaseErr = s.leases.Release(releaseCtx, input.Lease, lease)
			cancel()
		}
		quotaErr := s.releaseReservation(input, reservation)
		if quotaErr != nil {
			return ProviderHTTPResult{}, combineReleaseError(nil, quotaErr)
		}
		if leaseErr != nil {
			return ProviderHTTPResult{}, &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
		}
		return ProviderHTTPResult{}, &AppError{Code: "LLM_CONCURRENCY_LEASE_EXPIRED", Message: "LLM concurrency lease expired before provider call"}
	}
	result, callErr := s.executor.Execute(ctx, input.HTTP)
	releaseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	leaseErr := s.leases.Release(releaseCtx, input.Lease, lease)
	if callErr != nil {
		quotaErr := s.releaseReservation(input, reservation)
		if quotaErr != nil {
			return ProviderHTTPResult{}, combineReleaseError(callErr, quotaErr)
		}
		if leaseErr != nil {
			return ProviderHTTPResult{}, &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
		}
		return ProviderHTTPResult{}, callErr
	}
	cost, err := actualCostMicros(result, input.InputMicrosPerToken, input.OutputMicrosPerToken)
	if err != nil {
		return ProviderHTTPResult{}, err
	}
	if err := s.quota.Finalize(ctx, QuotaFinalizeInput{
		TenantID: input.Lease.TenantID, ReservationID: reservation.ReservationID,
		PromptTokens: result.PromptTokens, CompletionTokens: result.CompletionTokens, CostMicros: cost,
	}); err != nil {
		return ProviderHTTPResult{}, err
	}
	if leaseErr != nil {
		return ProviderHTTPResult{}, &AppError{Code: "LLM_CONCURRENCY_RELEASE_FAILED", Message: "LLM concurrency lease release failed"}
	}
	return result, nil
}

func (s *ProductionProviderCallService) releaseReservation(input ProductionProviderCallInput, reservation QuotaReservation) error {
	releaseCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	return s.quota.Release(releaseCtx, input.Lease.TenantID, reservation.ReservationID)
}

func combineReleaseError(primary, releaseErr error) error {
	if releaseErr != nil {
		return &AppError{Code: "LLM_QUOTA_RELEASE_FAILED", Message: "LLM quota reservation release failed"}
	}
	return primary
}

func actualCostMicros(result ProviderHTTPResult, inputRate, outputRate *int64) (*int64, error) {
	if inputRate == nil || outputRate == nil {
		return nil, nil
	}
	if *inputRate < 0 || *outputRate < 0 {
		return nil, &AppError{Code: "LLM_MODEL_PRICING_INVALID", Message: "LLM model pricing is invalid"}
	}
	if result.PromptTokens > (1<<63-1)/maxInt64(1, *inputRate) ||
		result.CompletionTokens > (1<<63-1)/maxInt64(1, *outputRate) {
		return nil, &AppError{Code: "LLM_MODEL_PRICING_INVALID", Message: "LLM model pricing is invalid"}
	}
	inputCost := result.PromptTokens * *inputRate
	outputCost := result.CompletionTokens * *outputRate
	cost, ok := checkedNonNegativeSum(inputCost, outputCost)
	if !ok {
		return nil, &AppError{Code: "LLM_MODEL_PRICING_INVALID", Message: "LLM model pricing is invalid"}
	}
	return &cost, nil
}

func maxInt64(left, right int64) int64 {
	if left > right {
		return left
	}
	return right
}

var sensitiveFieldFragments = []string{
	"api_key", "apikey", "authorization", "credential", "encrypted_api_key", "prompt", "response", "source_text",
}

func ContainsSensitiveFields(value any) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			lower := strings.ToLower(key)
			for _, fragment := range sensitiveFieldFragments {
				if strings.Contains(lower, fragment) {
					return true
				}
			}
			if ContainsSensitiveFields(child) {
				return true
			}
		}
	case []any:
		for _, child := range typed {
			if ContainsSensitiveFields(child) {
				return true
			}
		}
	case string:
		lower := strings.ToLower(typed)
		for _, fragment := range sensitiveFieldFragments {
			if strings.Contains(lower, fragment+"=") || strings.Contains(lower, fragment+":") {
				return true
			}
		}
	}
	return false
}
