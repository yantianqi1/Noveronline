package httpapi

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/llm"
	"mirofish-novel/apps/api/internal/workflows"
)

type recordingAnalysisStarter struct {
	input workflows.StartAnalysisRunInput
	run   workflows.AnalysisRun
	err   error
	calls int
}

func (s *recordingAnalysisStarter) StartAnalysisRun(_ context.Context, input workflows.StartAnalysisRunInput) (workflows.AnalysisRun, error) {
	s.calls += 1
	s.input = input
	if s.err != nil {
		return workflows.AnalysisRun{}, s.err
	}
	if s.run.RunID != "" {
		return s.run, nil
	}
	return workflows.AnalysisRun{
		RunID:        "analysis-run-1",
		ProjectID:    input.ProjectID,
		WorkflowType: workflows.AnalysisWorkflowType,
		Status:       "queued",
		Mode:         input.Mode,
	}, nil
}

func TestStartAnalysisRunFailsClosedWhenAnalysisModulesUnbound(t *testing.T) {
	starter := &recordingAnalysisStarter{}
	server := newDevelopmentServer(Config{
		Authorizer:        &recordingAuthorizer{},
		AnalysisStarter:   starter,
		SourceFileStore:   &recordingSourceFileStore{},
		LLMResolver:       llm.NewStaticResolver(nil),
		LLMBindingStore:   &recordingLLMBindingStore{},
	})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/analysis-runs",
		strings.NewReader(`{"upload_id":"upload-123","mode":"full"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable && response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected unbound analysis modules to fail closed, got %d: %s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), "LLM_MODULE_UNBOUND") {
		t.Fatalf("expected LLM_MODULE_UNBOUND, got %s", response.Body.String())
	}
	if starter.calls != 0 {
		t.Fatalf("analysis run must not admit without bindings: calls=%d input=%#v", starter.calls, starter.input)
	}
}

func TestStartAnalysisRunDoesNotBorrowWriterBinding(t *testing.T) {
	starter := &recordingAnalysisStarter{}
	bindingStore := &appendingLLMBindingStore{
		bindings: []llm.ModuleBindingRecord{{
			ModuleKey:     "writer_composer",
			Scope:         "project",
			ChannelID:     "channel-1",
			ModelID:       "deepseek-v4-flash",
			SupportsTools: true,
			SupportsJSON:  true,
			Settings:      map[string]any{"max_tokens": 2048},
		}},
	}
	resolver := &ensureAwareHTTPResolver{store: bindingStore}
	server := newDevelopmentServer(Config{
		Authorizer:      &recordingAuthorizer{},
		AnalysisStarter: starter,
		SourceFileStore: &recordingSourceFileStore{},
		LLMResolver:     resolver,
		LLMBindingStore: bindingStore,
	})
	request := httptest.NewRequest(
		http.MethodPost,
		"/v1/projects/project-123/analysis-runs",
		strings.NewReader(`{"upload_id":"upload-123","mode":"full","instruction":"Analyze carefully"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Tenant-Id", "tenant-123")
	request.Header.Set("X-User-Id", "user-123")
	response := httptest.NewRecorder()

	server.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable || !strings.Contains(response.Body.String(), "LLM_MODULE_UNBOUND") {
		t.Fatalf("expected explicit analysis binding failure, got %d: %s", response.Code, response.Body.String())
	}
	if starter.calls != 0 {
		t.Fatalf("analysis must not start by borrowing writer binding, got %d calls", starter.calls)
	}
	if bindingStore.upsertCount != 0 {
		t.Fatalf("unbound analysis path mutated bindings: %d", bindingStore.upsertCount)
	}
}

type appendingLLMBindingStore struct {
	bindings    []llm.ModuleBindingRecord
	upsertCount int
}

func (s *appendingLLMBindingStore) ListModuleBindings(context.Context, llm.ListModuleBindingsInput) ([]llm.ModuleBindingRecord, error) {
	return append([]llm.ModuleBindingRecord(nil), s.bindings...), nil
}

func (s *appendingLLMBindingStore) UpsertProjectModuleBinding(_ context.Context, input llm.UpsertProjectModuleBindingInput) (llm.ModuleBindingRecord, error) {
	s.upsertCount += 1
	record := llm.ModuleBindingRecord{
		ModuleKey:     input.ModuleKey,
		Scope:         "project",
		ChannelID:     input.ChannelID,
		ModelID:       input.ModelID,
		SupportsTools: true,
		SupportsJSON:  true,
		Settings:      input.Settings,
	}
	replaced := false
	for index := range s.bindings {
		if s.bindings[index].ModuleKey == input.ModuleKey && s.bindings[index].Scope == "project" {
			s.bindings[index] = record
			replaced = true
			break
		}
	}
	if !replaced {
		s.bindings = append(s.bindings, record)
	}
	return record, nil
}

func (s *appendingLLMBindingStore) DeleteProjectModuleBinding(context.Context, llm.DeleteProjectModuleBindingInput) (llm.ModuleBindingRecord, error) {
	return llm.ModuleBindingRecord{}, &llm.AppError{Code: "NOT_FOUND", Message: "not found"}
}

type ensureAwareHTTPResolver struct {
	store interface {
		ListModuleBindings(context.Context, llm.ListModuleBindingsInput) ([]llm.ModuleBindingRecord, error)
	}
}

func (r *ensureAwareHTTPResolver) ResolveModuleBinding(ctx context.Context, input llm.ResolveModuleInput) (llm.ModuleResolution, error) {
	bindings, err := r.store.ListModuleBindings(ctx, llm.ListModuleBindingsInput{
		TenantID:  input.TenantID,
		ProjectID: input.ProjectID,
	})
	if err != nil {
		return llm.ModuleResolution{}, err
	}
	for _, binding := range bindings {
		if binding.ModuleKey != input.ModuleKey {
			continue
		}
		return llm.ModuleResolution{
			TenantID:      input.TenantID,
			ProjectID:     input.ProjectID,
			ModuleKey:     binding.ModuleKey,
			ChannelID:     binding.ChannelID,
			ModelID:       binding.ModelID,
			SupportsTools: binding.SupportsTools,
			SupportsJSON:  binding.SupportsJSON,
			Settings:      binding.Settings,
		}, nil
	}
	return llm.ModuleResolution{}, &llm.AppError{
		Code:    "LLM_MODULE_UNBOUND",
		Message: input.ModuleKey + " module is not bound",
	}
}
