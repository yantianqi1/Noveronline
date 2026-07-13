package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/worldline"
)

type recordingLLMQuotaStore struct {
	listInput   llm.QuotaPolicyQuery
	upsertInput llm.UpsertQuotaPolicyInput
	policies    []llm.PersistentQuotaPolicy
	policy      llm.PersistentQuotaPolicy
	err         error
}

func (s *recordingLLMQuotaStore) ListPolicies(_ context.Context, input llm.QuotaPolicyQuery) ([]llm.PersistentQuotaPolicy, error) {
	s.listInput = input
	if s.err != nil {
		return nil, s.err
	}
	return s.policies, nil
}

func (s *recordingLLMQuotaStore) UpsertPolicy(_ context.Context, input llm.UpsertQuotaPolicyInput) (llm.PersistentQuotaPolicy, error) {
	s.upsertInput = input
	if s.err != nil {
		return llm.PersistentQuotaPolicy{}, s.err
	}
	return s.policy, nil
}

func TestListLLMQuotaPoliciesReturnsTenantProjectScopedRows(t *testing.T) {
	tokenLimit := int64(5000000)
	store := &recordingLLMQuotaStore{
		policies: []llm.PersistentQuotaPolicy{{
			PolicyID:   "policy-1",
			TenantID:   "tenant-123",
			ScopeType:  llm.QuotaScopeTenant,
			TokenLimit: &tokenLimit,
			Enabled:    true,
			UpdatedAt:  "2026-07-07T00:00:00Z",
		}},
	}
	server := newDevelopmentServer(projectReadAllowedConfig(Config{
		WriterStarter: &recordingStarter{},
		LLMQuotaStore: store,
	}))
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/llm/quota-policies?module_key=writer_composer", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.listInput.TenantID != "tenant-123" || store.listInput.ProjectID != "project-123" || store.listInput.ModuleKey != "writer_composer" {
		t.Fatalf("store lost query context: %#v", store.listInput)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	items := body["items"].([]any)
	if len(items) != 1 {
		t.Fatalf("unexpected items: %#v", body)
	}
}

func TestUpsertLLMQuotaPolicyRequiresLLMManagePermission(t *testing.T) {
	store := &recordingLLMQuotaStore{}
	authorizer := &recordingAuthorizer{err: &auth.AppError{Code: auth.CodeAccessDenied, Message: "access denied"}}
	server := newDevelopmentServer(Config{
		WriterStarter: &recordingStarter{},
		Authorizer:    authorizer,
		LLMQuotaStore: store,
	})
	request := httptest.NewRequest(http.MethodPut, "/v1/projects/project-123/llm/quota-policies", strings.NewReader(`{
		"scope_type":"module",
		"module_key":"writer_composer",
		"token_limit":1000,
		"period_seconds":2592000,
		"enabled":true
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden {
		t.Fatalf("expected status %d, got %d: %s", http.StatusForbidden, response.Code, response.Body.String())
	}
	if authorizer.inputs[0].Permission != auth.PermissionLLMModuleBindingManage {
		t.Fatalf("expected llm manage permission, got %#v", authorizer.inputs)
	}
	if store.upsertInput.TenantID != "" {
		t.Fatalf("upsert ran before authorization: %#v", store.upsertInput)
	}
}

func TestUpsertLLMQuotaPolicyPersistsPolicyForProjectScope(t *testing.T) {
	tokenLimit := int64(250000)
	store := &recordingLLMQuotaStore{
		policy: llm.PersistentQuotaPolicy{
			PolicyID:   "policy-2",
			TenantID:   "tenant-123",
			ScopeType:  llm.QuotaScopeProject,
			ProjectID:  "project-123",
			TokenLimit: &tokenLimit,
			Enabled:    true,
			UpdatedAt:  "2026-07-07T01:00:00Z",
		},
	}
	server := newDevelopmentServer(projectReadAllowedConfig(Config{
		WriterStarter: &recordingStarter{},
		LLMQuotaStore: store,
	}))
	request := httptest.NewRequest(http.MethodPut, "/v1/projects/project-123/llm/quota-policies", strings.NewReader(`{
		"scope_type":"project",
		"token_limit":250000,
		"period_seconds":2592000,
		"enabled":true
	}`))
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.upsertInput.TenantID != "tenant-123" || store.upsertInput.ProjectID != "project-123" || store.upsertInput.ScopeType != llm.QuotaScopeProject {
		t.Fatalf("unexpected upsert input: %#v", store.upsertInput)
	}
}

func TestListWorldlinePreparationsReturnsProjectScopedRows(t *testing.T) {
	store := &recordingWorldlinePreparationStore{
		preparations: []worldline.PreparationRecord{{
			PrepareID:    "prepare-1",
			RunID:        "run-1",
			ProjectID:    "project-123",
			WorkflowType: "worldline_preparation",
			Status:       "queued",
			Lifecycle:    "preparing",
			GoalSummary:  "Prepare council agents",
		}},
	}
	server := newDevelopmentServer(projectReadAllowedConfig(Config{
		WriterStarter:             &recordingStarter{},
		WorldlinePreparationStore: store,
	}))
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-123/worldlines/preparations", nil)
	request.Header.Set("X-Tenant-Id", "tenant-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d: %s", http.StatusOK, response.Code, response.Body.String())
	}
	if store.listInput.TenantID != "tenant-123" || store.listInput.ProjectID != "project-123" {
		t.Fatalf("store lost list context: %#v", store.listInput)
	}
}
