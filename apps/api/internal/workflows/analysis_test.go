package workflows

import (
	"strings"
	"testing"
)

func TestSanitizeAnalysisHintsStripsSecretsAndPrompts(t *testing.T) {
	t.Parallel()

	cleaned := sanitizeAnalysisHints(map[string]any{
		"focus":          "first 10 chapters",
		"api_key":        "sk-secret",
		"credential_ref": "cred-1",
		"prompt":         "system prompt body",
		"raw_body":       "full novel text",
		"nested": map[string]any{
			"ok":      true,
			"api_key": "nested-secret",
		},
	})

	if cleaned["focus"] != "first 10 chapters" {
		t.Fatalf("expected focus kept, got %#v", cleaned)
	}
	for _, banned := range []string{"api_key", "credential_ref", "prompt", "raw_body"} {
		if _, ok := cleaned[banned]; ok {
			t.Fatalf("expected %s stripped, got %#v", banned, cleaned)
		}
	}
	nested, ok := cleaned["nested"].(map[string]any)
	if !ok {
		t.Fatalf("expected nested map, got %#v", cleaned["nested"])
	}
	if nested["ok"] != true {
		t.Fatalf("expected nested ok kept, got %#v", nested)
	}
	if _, ok := nested["api_key"]; ok {
		t.Fatalf("expected nested api_key stripped, got %#v", nested)
	}
}

func TestSanitizeAnalysisOptionsDefaultsModuleKey(t *testing.T) {
	t.Parallel()

	cleaned := sanitizeAnalysisOptions(map[string]any{
		"thinking_level": "medium",
		"api_key":        "sk-secret",
	})
	if cleaned["module_key"] != "analysis_planner" {
		t.Fatalf("expected default module_key, got %#v", cleaned)
	}
	if cleaned["thinking_level"] != "medium" {
		t.Fatalf("expected thinking_level kept, got %#v", cleaned)
	}
	if _, ok := cleaned["api_key"]; ok {
		t.Fatalf("expected api_key stripped, got %#v", cleaned)
	}
}

func TestIsUntrustedAnalysisField(t *testing.T) {
	t.Parallel()

	for _, field := range []string{"api_key", "API_KEY", "credential_ref", "prompt", "raw_body", "object_key"} {
		if !isUntrustedAnalysisField(strings.ToLower(field)) {
			t.Fatalf("expected %s untrusted", field)
		}
	}
	if isUntrustedAnalysisField("focus") {
		t.Fatalf("focus should be trusted")
	}
}
