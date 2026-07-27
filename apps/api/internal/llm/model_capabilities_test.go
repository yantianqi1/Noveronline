package llm

import "testing"

func TestInferModelCapabilities(t *testing.T) {
	cases := []struct {
		modelID   string
		wantJSON  bool
		wantTools bool
	}{
		{modelID: "deepseek-chat", wantJSON: true, wantTools: true},
		{modelID: "deepseek-v4-flash", wantJSON: true, wantTools: true},
		{modelID: "[free]deepseek-v4-flash", wantJSON: true, wantTools: true},
		{modelID: "DeepSeek-Coder", wantJSON: true, wantTools: true},
		{modelID: "deepseek-reasoner", wantJSON: false, wantTools: false},
		{modelID: "deepseek-r1", wantJSON: false, wantTools: false},
		{modelID: "gpt-4o-mini", wantJSON: true, wantTools: true},
		{modelID: "gpt-5.5", wantJSON: true, wantTools: true},
		{modelID: "[free]gpt-5.5", wantJSON: true, wantTools: true},
		{modelID: "o3-mini", wantJSON: true, wantTools: true},
		{modelID: "claude-sonnet-4-6", wantJSON: true, wantTools: true},
		{modelID: "gemini-2.5-pro", wantJSON: true, wantTools: true},
		{modelID: "qwen-plus", wantJSON: true, wantTools: true},
		{modelID: "qwq-32b", wantJSON: false, wantTools: false},
		{modelID: "glm-4-plus", wantJSON: true, wantTools: true},
		{modelID: "moonshot-v1-8k", wantJSON: true, wantTools: true},
		{modelID: "kimi-k2", wantJSON: true, wantTools: true},
		{modelID: "text-embedding-3-large", wantJSON: false, wantTools: false},
		{modelID: "gpt-image-2", wantJSON: false, wantTools: false},
		{modelID: "some-custom-chat-model", wantJSON: true, wantTools: true},
		{modelID: "   ", wantJSON: false, wantTools: false},
	}
	for _, tc := range cases {
		got := InferModelCapabilities(tc.modelID)
		if got.SupportsJSON != tc.wantJSON || got.SupportsTools != tc.wantTools {
			t.Fatalf("InferModelCapabilities(%q) = %+v, want json=%v tools=%v", tc.modelID, got, tc.wantJSON, tc.wantTools)
		}
	}
	if caps := EffectiveModelCapabilities("deepseek-v4-flash", true, false); !caps.SupportsJSON || caps.SupportsTools {
		t.Fatalf("explicit stored capability flags must be preserved, got %+v", caps)
	}
}

func TestEnrichProviderModelsPopulatesDocumentedCapabilities(t *testing.T) {
	enriched := enrichProviderModels([]ProviderModel{
		{ModelID: "deepseek-v4-flash", OwnedBy: "deepseek"},
		{ModelID: "deepseek-reasoner", OwnedBy: "deepseek"},
		{ModelID: "gpt-image-2", OwnedBy: "openai"},
		{ModelID: "", OwnedBy: "ignored"},
		{ModelID: "deepseek-v4-flash", OwnedBy: "duplicate"},
	})
	if len(enriched) != 3 {
		t.Fatalf("expected 3 sanitized enriched models, got %#v", enriched)
	}
	if enriched[0].ModelID != "deepseek-v4-flash" || !enriched[0].SupportsJSON || !enriched[0].SupportsTools {
		t.Fatalf("deepseek-v4-flash should be JSON/tool capable, got %#v", enriched[0])
	}
	if enriched[1].ModelID != "deepseek-reasoner" || enriched[1].SupportsJSON || enriched[1].SupportsTools {
		t.Fatalf("deepseek-reasoner should stay uncapable, got %#v", enriched[1])
	}
	if enriched[2].ModelID != "gpt-image-2" || enriched[2].SupportsJSON {
		t.Fatalf("gpt-image-2 should stay non-chat, got %#v", enriched[2])
	}
}
