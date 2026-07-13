package assetdistillation

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.temporal.io/sdk/client"
)

type fakeTemporalClient struct {
	started []string
	err     error
}

func (f *fakeTemporalClient) ExecuteWorkflow(_ context.Context, options client.StartWorkflowOptions, workflow any, args ...any) (client.WorkflowRun, error) {
	f.started = append(f.started, options.ID)
	if f.err != nil {
		return nil, f.err
	}
	return nil, nil
}

type fakeStore struct {
	admitted   Admission
	replay     bool
	err        error
	dispatched []string
}

func (f *fakeStore) GetSettings(context.Context, Scope) (Settings, error) {
	return Settings{ProjectID: "p1", TriggerMode: "manual"}, nil
}
func (f *fakeStore) PatchSettings(context.Context, Scope, SettingsPatch) (Settings, error) {
	return Settings{}, nil
}
func (f *fakeStore) AdmitManual(context.Context, StartManualInput) (Admission, bool, error) {
	return f.admitted, f.replay, f.err
}
func (f *fakeStore) EnqueueFromSources(context.Context, Scope, string, []SourceBlock) (Admission, bool, error) {
	return Admission{}, false, nil
}
func (f *fakeStore) MarkDispatched(_ context.Context, _, requestID string) error {
	f.dispatched = append(f.dispatched, requestID)
	return nil
}
func (f *fakeStore) MarkDispatchRetry(context.Context, string, string, string, int, time.Time) error {
	return nil
}
func (f *fakeStore) ClaimPendingDispatch(context.Context, int) ([]OutboxItem, error) {
	return nil, nil
}
func (f *fakeStore) ListProposals(context.Context, Scope, string) ([]ProposalSummary, error) {
	return nil, nil
}
func (f *fakeStore) GetProposal(context.Context, Scope, string, bool) (ProposalDetail, error) {
	return ProposalDetail{}, nil
}
func (f *fakeStore) Decide(context.Context, DecisionInput) (DecisionResult, error) {
	return DecisionResult{}, nil
}
func (f *fakeStore) StaleProposalsForBlock(context.Context, Scope, string) error { return nil }
func (f *fakeStore) LookupProposalProject(context.Context, string, string) (string, error) {
	return "", nil
}

func TestTemporalStarterStartsManualDistillation(t *testing.T) {
	store := &fakeStore{admitted: Admission{
		RunID:     "11111111-1111-4111-8111-111111111111",
		RequestID: "22222222-2222-4222-8222-222222222222",
		ProjectID: "project-1", WorkflowType: WorkflowType, ModuleKey: ModuleKey, Status: "queued", TriggerKind: "manual",
	}}
	client := &fakeTemporalClient{}
	starter := NewTemporalStarter(client, store, "writer-planning")
	result, err := starter.StartManual(context.Background(), StartManualInput{
		Scope:            Scope{TenantID: "t1", ProjectID: "project-1", ActorUserID: "u1", RequestID: "req-1"},
		BlockIDs:         []string{"b1"},
		ExpectedVersions: map[string]int{"b1": 1},
	})
	if err != nil {
		t.Fatalf("start manual: %v", err)
	}
	if result.RunID == "" || result.Replay {
		t.Fatalf("unexpected admission: %#v", result)
	}
	if len(client.started) != 1 || !strings.HasPrefix(client.started[0], WorkflowType+"_") {
		t.Fatalf("temporal id missing: %#v", client.started)
	}
	if len(store.dispatched) != 1 {
		t.Fatalf("expected dispatch mark: %#v", store.dispatched)
	}
}

func TestTemporalStarterReplaysWithoutStarting(t *testing.T) {
	store := &fakeStore{
		admitted: Admission{RunID: "run-1", RequestID: "req-1", ProjectID: "p1", WorkflowType: WorkflowType, ModuleKey: ModuleKey, Status: "queued"},
		replay:   true,
	}
	client := &fakeTemporalClient{}
	starter := NewTemporalStarter(client, store, "")
	result, err := starter.StartManual(context.Background(), StartManualInput{
		Scope:    Scope{TenantID: "t1", ProjectID: "p1", ActorUserID: "u1", RequestID: "req-1"},
		BlockIDs: []string{"b1"},
	})
	if err != nil || !result.Replay || len(client.started) != 0 {
		t.Fatalf("replay should not start temporal: %#v err=%v started=%#v", result, err, client.started)
	}
}

func TestIsRouteShapes(t *testing.T) {
	if !IsRoute("GET", "/v1/projects/p1/asset-distillation-settings") {
		t.Fatal("settings get route")
	}
	if !IsRoute("POST", "/v1/projects/p1/manuscript-asset-distillations") {
		t.Fatal("manual start route")
	}
	if !IsRoute("GET", "/v1/projects/p1/asset-proposals") {
		t.Fatal("proposal list route")
	}
	if !IsRoute("POST", "/v1/asset-proposals/c1/decisions") {
		t.Fatal("decision route")
	}
	if IsRoute("GET", "/v1/projects/p1/chapters") {
		t.Fatal("unrelated route matched")
	}
}
