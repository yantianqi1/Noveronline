package assets

import (
	"context"
	"fmt"
	"strings"
)

type SearchCapabilities struct {
	Keyword    bool   `json:"keyword"`
	Vector     bool   `json:"vector"`
	Hybrid     bool   `json:"hybrid"`
	Reason     string `json:"reason,omitempty"`
	ConfigHref string `json:"config_href,omitempty"`
}

func GetSearchCapabilities(
	ctx context.Context,
	tenantID string,
	projectID string,
	resolver QueryEmbeddingResolver,
	indexChecker SearchIndexChecker,
) (SearchCapabilities, error) {
	tenantID = strings.TrimSpace(tenantID)
	projectID = strings.TrimSpace(projectID)
	if tenantID == "" || projectID == "" {
		return SearchCapabilities{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id and project_id are required"}
	}
	capabilities := SearchCapabilities{
		Keyword:    true,
		Vector:     false,
		Hybrid:     false,
		ConfigHref: fmt.Sprintf("/projects/%s/llm-facility?module=asset_search_embedding", projectID),
	}
	if resolver == nil {
		capabilities.Reason = "asset_search_embedding module is not bound"
		return capabilities, nil
	}
	binding, err := resolver.ResolveQueryEmbedding(ctx, tenantID, projectID)
	if err != nil {
		if code := ErrorCode(err); code == "LLM_MODULE_UNBOUND" || code == "LLM_BINDING_BACKEND_UNCONFIGURED" {
			capabilities.Reason = "asset_search_embedding module is not bound"
			return capabilities, nil
		}
		return SearchCapabilities{}, err
	}
	if err := validateQueryEmbeddingBinding(binding); err != nil {
		if code := ErrorCode(err); code == "LLM_MODULE_UNBOUND" || code == "LLM_CREDENTIAL_UNAVAILABLE" || code == "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED" || code == "ASSET_QUERY_EMBEDDING_PROVIDER_UNSUPPORTED" {
			capabilities.Reason = publicSearchCapabilityReason(code)
			return capabilities, nil
		}
		return SearchCapabilities{}, err
	}
	dimensions, ok := positiveSettingInt(binding.Settings["embedding_dimensions"])
	if !ok {
		capabilities.Reason = "asset search embedding dimensions are not configured"
		return capabilities, nil
	}
	if indexChecker == nil {
		capabilities.Reason = "asset vector search index is not available"
		return capabilities, nil
	}
	hasIndex, err := indexChecker.HasSearchIndex(ctx, SearchIndexInput{
		TenantID:       tenantID,
		ProjectID:      projectID,
		EmbeddingModel: binding.ModelID,
		Dimensions:     dimensions,
	})
	if err != nil {
		return SearchCapabilities{}, err
	}
	if !hasIndex {
		capabilities.Reason = "asset vector search index is not available"
		return capabilities, nil
	}
	capabilities.Vector = true
	capabilities.Hybrid = true
	capabilities.Reason = ""
	return capabilities, nil
}

func publicSearchCapabilityReason(code string) string {
	switch code {
	case "LLM_MODULE_UNBOUND":
		return "asset_search_embedding module is not bound"
	case "LLM_CREDENTIAL_UNAVAILABLE":
		return "asset query embedding credential is unavailable"
	case "ASSET_QUERY_EMBEDDING_PROVIDER_UNCONFIGURED":
		return "asset query embedding provider is incomplete"
	case "ASSET_QUERY_EMBEDDING_PROVIDER_UNSUPPORTED":
		return "asset query embedding provider is unsupported"
	default:
		return "asset vector search is unavailable"
	}
}
