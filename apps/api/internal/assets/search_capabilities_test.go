package assets

import (
	"context"
	"testing"
)

type recordingSearchCapabilityResolver struct {
	binding QueryEmbeddingBinding
	err     error
	input   struct {
		tenantID  string
		projectID string
	}
}

func (r *recordingSearchCapabilityResolver) ResolveQueryEmbedding(_ context.Context, tenantID, projectID string) (QueryEmbeddingBinding, error) {
	r.input.tenantID = tenantID
	r.input.projectID = projectID
	if r.err != nil {
		return QueryEmbeddingBinding{}, r.err
	}
	return r.binding, nil
}

func TestGetSearchCapabilitiesAlwaysEnablesKeyword(t *testing.T) {
	capabilities, err := GetSearchCapabilities(context.Background(), "tenant-1", "project-1", nil, nil)
	if err != nil {
		t.Fatalf("get search capabilities: %v", err)
	}
	if !capabilities.Keyword || capabilities.Vector || capabilities.Hybrid {
		t.Fatalf("expected keyword-only capabilities, got %#v", capabilities)
	}
	if capabilities.Reason != "asset_search_embedding module is not bound" {
		t.Fatalf("unexpected reason: %#v", capabilities)
	}
	if capabilities.ConfigHref != "/projects/project-1/llm-facility?module=asset_search_embedding" {
		t.Fatalf("unexpected config href: %#v", capabilities)
	}
}

func TestGetSearchCapabilitiesEnablesVectorWhenBindingAndIndexReady(t *testing.T) {
	resolver := &recordingSearchCapabilityResolver{binding: validQueryEmbeddingBinding()}
	index := &recordingSearchIndexChecker{exists: true}
	capabilities, err := GetSearchCapabilities(context.Background(), "tenant-1", "project-1", resolver, index)
	if err != nil {
		t.Fatalf("get search capabilities: %v", err)
	}
	if !capabilities.Keyword || !capabilities.Vector || !capabilities.Hybrid || capabilities.Reason != "" {
		t.Fatalf("expected full search capabilities, got %#v", capabilities)
	}
	if index.input.EmbeddingModel != "embedding-model-1" || index.input.Dimensions != 3 {
		t.Fatalf("unexpected index probe: %#v", index.input)
	}
}

func TestGetSearchCapabilitiesKeepsVectorDisabledWithoutIndex(t *testing.T) {
	resolver := &recordingSearchCapabilityResolver{binding: validQueryEmbeddingBinding()}
	capabilities, err := GetSearchCapabilities(context.Background(), "tenant-1", "project-1", resolver, &recordingSearchIndexChecker{exists: false})
	if err != nil {
		t.Fatalf("get search capabilities: %v", err)
	}
	if capabilities.Vector || capabilities.Hybrid || capabilities.Reason != "asset vector search index is not available" {
		t.Fatalf("unexpected capabilities: %#v", capabilities)
	}
}
