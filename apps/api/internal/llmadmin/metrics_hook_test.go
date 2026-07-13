package llmadmin

import (
	"context"
	"errors"
	"net/http"
	"testing"
)

type metricsProbe struct {
	channelID             string
	health                bool
	healthCalls           int
	reconciliationFailure int
}

func (m *metricsProbe) SetProviderHealth(channelID string, healthy bool) {
	m.channelID = channelID
	m.health = healthy
	m.healthCalls++
}

func (m *metricsProbe) RecordQuotaReconciliationFailure() { m.reconciliationFailure++ }

func TestHealthServicePublishesProviderOutcomeToProductionMetrics(t *testing.T) {
	metrics := &metricsProbe{}
	target := HealthTarget{
		ChannelID: "channel-1", ModelID: "model-1", BaseURL: "http://127.0.0.1:8080/v1", APIKey: "secret",
	}
	executor := &healthExecutor{result: HealthExecution{StatusCode: http.StatusOK}}
	service := NewHealthService(healthResolver{target: target}, executor, nil).WithMetrics(metrics)
	if _, err := service.Check(context.Background(), "tenant-1", "actor-1", "project-1", "channel-1", "model-1", "request-1"); err != nil {
		t.Fatalf("healthy provider failed: %v", err)
	}
	if metrics.healthCalls != 1 || metrics.channelID != "channel-1" || !metrics.health {
		t.Fatalf("healthy outcome was not published: %#v", metrics)
	}

	executor.err = errors.New("provider unavailable")
	if _, err := service.Check(context.Background(), "tenant-1", "actor-1", "project-1", "channel-1", "model-1", "request-2"); ErrorCode(err) != "LLM_PROVIDER_HEALTH_FAILED" {
		t.Fatalf("provider failure code mismatch: %v", err)
	}
	if metrics.healthCalls != 2 || metrics.health {
		t.Fatalf("unhealthy outcome was not published: %#v", metrics)
	}
}

type failingReconciliationStore struct{ *fakeStore }

func (s failingReconciliationStore) Reconcile(context.Context, string, string, string, int) ([]Reconciliation, error) {
	return nil, errors.New("credential_ref=private prompt=private")
}

func TestReconciliationBackendFailureIncrementsMetricWithoutLeakingError(t *testing.T) {
	metrics := &metricsProbe{}
	handler := NewHandler(Config{
		Store: failingReconciliationStore{fakeStore: &fakeStore{}}, Access: &roleAccess{role: "billing"},
		ActorResolver: staticActor{id: "user-1"}, Metrics: metrics,
	})
	response := perform(handler, http.MethodGet, "/v1/llm-admin/reconciliation?project_id=project-1", "tenant-1", nil)
	if response.Code != http.StatusInternalServerError || metrics.reconciliationFailure != 1 {
		t.Fatalf("failure metric mismatch: status=%d metrics=%#v", response.Code, metrics)
	}
	assertPrivate(response.Body.String(), t)
}
