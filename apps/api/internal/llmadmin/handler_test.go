package llmadmin

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type staticActor struct{ id string }

func (a staticActor) ResolveActor(context.Context, *http.Request) (string, error) { return a.id, nil }

type roleAccess struct {
	role  string
	calls []AccessInput
}

func (a *roleAccess) Authorize(_ context.Context, input AccessInput) error {
	a.calls = append(a.calls, input)
	if !roleAllows(a.role, input.Operation) {
		return &AppError{Code: "AUTH_ACCESS_DENIED", Message: "api_key=secret prompt=private body=private"}
	}
	return nil
}

type fakeStore struct {
	policies       []Policy
	created        PolicyWrite
	updated        PolicyWrite
	deletedVersion string
	tenantID       string
	preview        ResolutionPreview
	reservations   []Reservation
	reconciliation []Reconciliation
	calls          int
}

func (s *fakeStore) ListPolicies(_ context.Context, tenantID, _ string) ([]Policy, error) {
	s.calls++
	s.tenantID = tenantID
	return s.policies, nil
}
func (s *fakeStore) CreatePolicy(_ context.Context, tenantID, _ string, input PolicyWrite) (Policy, error) {
	s.calls++
	s.tenantID = tenantID
	s.created = input
	return Policy{PolicyID: "policy-1", ScopeType: input.ScopeType}, nil
}
func (s *fakeStore) UpdatePolicy(_ context.Context, tenantID, _, _ string, input PolicyWrite) (Policy, error) {
	s.calls++
	s.tenantID = tenantID
	s.updated = input
	return Policy{PolicyID: "policy-1", Version: "v2"}, nil
}
func (s *fakeStore) DeletePolicy(_ context.Context, tenantID, _, _, version string) error {
	s.calls++
	s.tenantID = tenantID
	s.deletedVersion = version
	return nil
}
func (s *fakeStore) PreviewResolution(context.Context, string, string, string) (ResolutionPreview, error) {
	s.calls++
	return s.preview, nil
}
func (s *fakeStore) ListReservations(context.Context, string, string, string, int) ([]Reservation, error) {
	s.calls++
	return s.reservations, nil
}
func (s *fakeStore) Reconcile(context.Context, string, string, string, int) ([]Reconciliation, error) {
	s.calls++
	return s.reconciliation, nil
}

func TestOperationMetadataSeparatesReadWriteAndHealthRoles(t *testing.T) {
	operations := Operations()
	if len(operations) != 6 {
		t.Fatalf("unexpected operations: %#v", operations)
	}
	for _, operation := range operations {
		joined := strings.Join(operation.AllowedRoles, ",")
		if (operation.Operation == OperationPolicyWrite || operation.Operation == OperationProviderHealth) && strings.Contains(joined, "billing") {
			t.Fatalf("billing gained mutation: %#v", operation)
		}
		if operation.Operation != OperationPolicyWrite && operation.Operation != OperationProviderHealth && !strings.Contains(joined, "billing") {
			t.Fatalf("billing lost diagnostics: %#v", operation)
		}
	}
}

func TestHandlerRBACDeniesViewerBeforeStoreAndAllowsBillingReadOnly(t *testing.T) {
	store := &fakeStore{}
	viewer := &roleAccess{role: "viewer"}
	handler := NewHandler(Config{Store: store, Access: viewer, ActorResolver: staticActor{id: "user-1"}})
	response := perform(handler, http.MethodGet, "/v1/llm-admin/policies?project_id=project-1", "tenant-1", nil)
	if response.Code != http.StatusForbidden || store.calls != 0 {
		t.Fatalf("viewer reached store: status=%d calls=%d", response.Code, store.calls)
	}
	assertPrivate(response.Body.String(), t)

	billing := &roleAccess{role: "billing"}
	handler = NewHandler(Config{Store: store, Access: billing, ActorResolver: staticActor{id: "user-2"}})
	response = perform(handler, http.MethodGet, "/v1/llm-admin/reservations?project_id=project-1", "tenant-1", nil)
	if response.Code != http.StatusOK || store.calls != 1 {
		t.Fatalf("billing read failed: status=%d body=%s", response.Code, response.Body.String())
	}
	response = perform(handler, http.MethodPost, "/v1/llm-admin/policies", "tenant-1", []byte(`{"scope_type":"tenant","token_limit":10,"period_seconds":60}`))
	if response.Code != http.StatusForbidden || store.calls != 1 {
		t.Fatalf("billing mutation reached store: status=%d calls=%d", response.Code, store.calls)
	}
}

func TestHandlerPolicyCRUDUsesHeaderTenantAndOptimisticVersion(t *testing.T) {
	store := &fakeStore{}
	handler := NewHandler(Config{Store: store, Access: &roleAccess{role: "admin"}, ActorResolver: staticActor{id: "user-1"}, RateLimiter: allowingLimiter{}})
	body := []byte(`{"scope_type":"module","project_id":"project-1","module_key":"writer_composer","token_limit":100,"period_seconds":3600,"enabled":true,"expected_version":"2026-07-10 00:00:00+00"}`)
	response := perform(handler, http.MethodPut, "/v1/llm-admin/policies/policy-1", "tenant-safe", body)
	if response.Code != http.StatusOK || store.tenantID != "tenant-safe" || store.updated.ExpectedVersion != "2026-07-10 00:00:00+00" {
		t.Fatalf("optimistic update lost context: %#v status=%d", store, response.Code)
	}
	response = perform(handler, http.MethodDelete, "/v1/llm-admin/policies/policy-1?expected_version=v2", "tenant-safe", nil)
	if response.Code != http.StatusOK || store.deletedVersion != "v2" {
		t.Fatalf("optimistic delete failed: %#v", store)
	}
}

func TestHandlerRejectsUnknownSensitiveFieldsWithoutEcho(t *testing.T) {
	store := &fakeStore{}
	handler := NewHandler(Config{Store: store, Access: &roleAccess{role: "owner"}, ActorResolver: staticActor{id: "user-1"}})
	response := perform(handler, http.MethodPost, "/v1/llm-admin/policies", "tenant-1", []byte(`{"scope_type":"tenant","token_limit":1,"period_seconds":60,"api_key":"secret","prompt":"private"}`))
	if response.Code != http.StatusBadRequest || store.calls != 0 {
		t.Fatalf("invalid JSON reached store: %d %s", response.Code, response.Body.String())
	}
	assertPrivate(response.Body.String(), t)
}

type healthResolver struct {
	target HealthTarget
	err    error
}

func (r healthResolver) ResolveHealthTarget(context.Context, string, string, string, string) (HealthTarget, error) {
	return r.target, r.err
}

type healthExecutor struct {
	request HealthRequest
	result  HealthExecution
	err     error
}

func (e *healthExecutor) ExecuteHealth(_ context.Context, request HealthRequest) (HealthExecution, error) {
	e.request = request
	return e.result, e.err
}

type healthRecorder struct {
	audit HealthAudit
	calls int
}

func (r *healthRecorder) RecordHealth(_ context.Context, audit HealthAudit) error {
	r.calls++
	r.audit = audit
	return nil
}

func TestProviderHealthSendsMinimalRequestAndRecordsOnlySanitizedMetadata(t *testing.T) {
	target := HealthTarget{ChannelID: "channel-1", ModelID: "model-1", BaseURL: "http://127.0.0.1:9999/v1", APIKey: "super-secret", SupportsTools: true, SupportsJSON: true}
	executor := &healthExecutor{result: HealthExecution{StatusCode: 200}}
	recorder := &healthRecorder{}
	service := NewHealthService(healthResolver{target: target}, executor, recorder)
	times := []time.Time{time.Unix(100, 0), time.Unix(100, 15_000_000)}
	service.now = func() time.Time { value := times[0]; times = times[1:]; return value }
	handler := NewHandler(Config{Store: &fakeStore{}, Access: &roleAccess{role: "owner"}, ActorResolver: staticActor{id: "user-1"}, Health: service, RateLimiter: allowingLimiter{}})
	response := perform(handler, http.MethodPost, "/v1/llm-admin/provider-health", "tenant-1", []byte(`{"project_id":"project-1","channel_id":"channel-1","model_id":"model-1"}`))
	if response.Code != http.StatusOK {
		t.Fatalf("health failed: %d %s", response.Code, response.Body.String())
	}
	if executor.request.APIKey != "super-secret" || !bytes.Contains(executor.request.Body, []byte(`"max_tokens":1`)) || bytes.Contains(executor.request.Body, []byte("novel")) {
		t.Fatalf("health request is not minimal: %#v %s", executor.request, executor.request.Body)
	}
	if recorder.calls != 1 || recorder.audit.LatencyMS != 15 || !recorder.audit.SupportsTools {
		t.Fatalf("unsafe/incomplete audit: %#v", recorder.audit)
	}
	assertPrivate(response.Body.String(), t)
	encoded, _ := json.Marshal(recorder.audit)
	assertPrivate(string(encoded), t)
}

func TestProviderHealthRequiresHTTPSAndExplicitExternalOptIn(t *testing.T) {
	for _, test := range []struct {
		name, url string
		optIn     bool
		code      string
	}{
		{name: "http", url: "http://provider.example/v1", optIn: true, code: "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED"},
		{name: "opt-in", url: "https://provider.example/v1", optIn: false, code: "LLM_EXTERNAL_PROVIDER_OPT_IN_REQUIRED"},
	} {
		t.Run(test.name, func(t *testing.T) {
			executor := &healthExecutor{}
			service := NewHealthService(healthResolver{target: HealthTarget{ChannelID: "c", ModelID: "m", BaseURL: test.url, APIKey: "secret", ExternalProviderOptIn: test.optIn}}, executor, nil)
			_, err := service.Check(context.Background(), "tenant", "user", "project", "c", "m", "request")
			if ErrorCode(err) != test.code || executor.request.BaseURL != "" {
				t.Fatalf("external guard failed: code=%s request=%#v", ErrorCode(err), executor.request)
			}
		})
	}
}

func TestProviderHealthTreatsPrivateAndLinkLocalTargetsAsExternal(t *testing.T) {
	for _, baseURL := range []string{
		"http://10.0.0.8/v1",
		"http://192.168.1.8/v1",
		"http://169.254.169.254/latest",
		"http://metadata/v1",
	} {
		executor := &healthExecutor{}
		service := NewHealthService(healthResolver{target: HealthTarget{
			ChannelID: "c", ModelID: "m", BaseURL: baseURL, APIKey: "secret", ExternalProviderOptIn: true,
		}}, executor, nil)
		_, err := service.Check(context.Background(), "tenant", "user", "project", "c", "m", "request")
		if ErrorCode(err) != "LLM_EXTERNAL_PROVIDER_HTTPS_REQUIRED" || executor.request.BaseURL != "" {
			t.Fatalf("SSRF-sensitive endpoint %q reached executor: code=%s request=%#v", baseURL, ErrorCode(err), executor.request)
		}
	}
}

func TestProviderHealthMissingOwnedEnabledTargetIsExplicitlyUnavailable(t *testing.T) {
	service := NewHealthService(healthResolver{err: errors.New("database api_key=private")}, &healthExecutor{}, nil)
	handler := NewHandler(Config{
		Store: &fakeStore{}, Access: &roleAccess{role: "owner"}, ActorResolver: staticActor{id: "user-1"}, Health: service,
		RateLimiter: allowingLimiter{},
	})
	response := perform(handler, http.MethodPost, "/v1/llm-admin/provider-health", "tenant-1", []byte(`{"project_id":"project-1","channel_id":"channel-1","model_id":"model-1"}`))
	if response.Code != http.StatusServiceUnavailable || !strings.Contains(response.Body.String(), "LLM_PROVIDER_HEALTH_TARGET_UNAVAILABLE") {
		t.Fatalf("unavailable health target was not explicit: %d %s", response.Code, response.Body.String())
	}
	assertPrivate(response.Body.String(), t)
}

func TestReconciliationNeverInventsZeroPricing(t *testing.T) {
	actual, usage := int64(12), int64(12)
	item := Reconciliation{ReservationID: "reservation-1", ReservationStatus: "finalized", ActivityStatus: "completed", ActualTokens: &actual, UsageTokens: &usage}
	reconcileStatuses(&item, true, true)
	if item.PricingStatus != "unavailable" || item.BillingStatus != "pricing_unavailable" || item.ActualCostMicros != nil {
		t.Fatalf("pricing was invented: %#v", item)
	}
	usageCost := int64(9)
	item.UsageCostMicros = &usageCost
	reconcileStatuses(&item, true, true)
	if item.PricingStatus != "available" || item.BillingStatus != "reconciled" {
		t.Fatalf("priced call did not reconcile: %#v", item)
	}
}

func TestResolutionMarksTheTightestScopeForEachQuotaDimension(t *testing.T) {
	moduleTokens, projectCost, tenantConcurrency := int64(20), int64(30), 1
	otherTokens, otherCost, otherConcurrency := int64(40), int64(50), 2
	items := []PolicyUsage{
		{Policy: Policy{ScopeType: "module"}, RemainingTokens: &moduleTokens, RemainingCostMicros: &otherCost, RemainingConcurrency: intPointer(3)},
		{Policy: Policy{ScopeType: "project"}, RemainingTokens: &otherTokens, RemainingCostMicros: &projectCost, RemainingConcurrency: &otherConcurrency},
		{Policy: Policy{ScopeType: "tenant"}, RemainingTokens: int64Pointer(60), RemainingCostMicros: int64Pointer(70), RemainingConcurrency: intPointer(int(tenantConcurrency))},
	}
	got := strings.Join(limitingScopes(items), ",")
	if got != "module,project,tenant" {
		t.Fatalf("unexpected limiting scopes: %s", got)
	}
}

func intPointer(value int) *int       { return &value }
func int64Pointer(value int64) *int64 { return &value }

func perform(handler http.Handler, method, path, tenant string, body []byte) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, bytes.NewReader(body))
	request.Header.Set("X-Tenant-Id", tenant)
	request.Header.Set("X-Request-Id", "request-1")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func assertPrivate(value string, t *testing.T) {
	t.Helper()
	lower := strings.ToLower(value)
	for _, forbidden := range []string{"super-secret", "api_key", "prompt", "request_body", "novel", "manuscript"} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("sensitive value %q leaked: %s", forbidden, value)
		}
	}
}

var _ = errors.New
