package llm

import (
	"strings"
	"unicode"
)

// InferredModelCapabilities describes capability metadata the platform can
// assert for a model id when catalog rows still carry the FALSE column default.
//
// Catalog sync from OpenAI-compatible providers rarely publishes capability
// bits, so a false default previously blocked real DeepSeek / GPT / Claude
// chat models before any provider call. Inference is therefore permissive for
// chat models: only known non-chat or reasoning-only variants stay unsupported.
//
// Sync and resolve paths only OR these flags in; operators can still force
// capabilities on/off from Models settings.
type InferredModelCapabilities struct {
	SupportsJSON  bool
	SupportsTools bool
}

// InferModelCapabilities returns JSON / tool-calling support for a model id.
// OpenAI-compatible chat models (including official DeepSeek chat endpoints)
// are treated as capable; only known non-chat or reasoning-only ids stay false.
func InferModelCapabilities(modelID string) InferredModelCapabilities {
	normalized := normalizeModelID(modelID)
	if normalized == "" {
		return InferredModelCapabilities{}
	}
	if isNonChatModel(normalized) || isReasoningOnlyModel(normalized) {
		return InferredModelCapabilities{}
	}
	// Chat completions models: default capable. response_format json_object and
	// tools are standard on OpenAI-compatible chat APIs (DeepSeek V3/V4, GPT,
	// Claude via proxies, Gemini chat, Qwen, GLM, Kimi, ...).
	return InferredModelCapabilities{SupportsJSON: true, SupportsTools: true}
}

// EffectiveModelCapabilities ORs catalog column defaults with inference so a
// FALSE column default never reports "unsupported" for real chat models.
func EffectiveModelCapabilities(modelID string, storedJSON, storedTools bool) InferredModelCapabilities {
	caps := InferModelCapabilities(modelID)
	return InferredModelCapabilities{
		SupportsJSON:  storedJSON || caps.SupportsJSON,
		SupportsTools: storedTools || caps.SupportsTools,
	}
}

// inferModelCapabilities is the historical unexported alias used by sync paths.
func inferModelCapabilities(modelID string) InferredModelCapabilities {
	return InferModelCapabilities(modelID)
}

// normalizeModelID strips common proxy prefixes such as "[free]" / "[antig]"
// and lowercases the remainder so deepseek-v4-flash matches family rules.
func normalizeModelID(modelID string) string {
	trimmed := strings.TrimSpace(modelID)
	if trimmed == "" {
		return ""
	}
	// Drop leading bracket tags: [free]deepseek-v4-flash → deepseek-v4-flash
	for strings.HasPrefix(trimmed, "[") {
		end := strings.Index(trimmed, "]")
		if end <= 0 {
			break
		}
		trimmed = strings.TrimSpace(trimmed[end+1:])
	}
	// Drop trailing provider tags some gateways append.
	trimmed = strings.TrimSpace(trimmed)
	var b strings.Builder
	b.Grow(len(trimmed))
	for _, r := range strings.ToLower(trimmed) {
		if unicode.IsSpace(r) {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func isReasoningOnlyModel(normalized string) bool {
	if strings.Contains(normalized, "deepseek") &&
		(strings.Contains(normalized, "reasoner") ||
			strings.Contains(normalized, "-r1") ||
			strings.HasSuffix(normalized, "r1") ||
			strings.Contains(normalized, "r1-")) {
		// deepseek-reasoner / deepseek-r1; do not treat deepseek-v4 as r1.
		if strings.Contains(normalized, "reasoner") ||
			strings.Contains(normalized, "deepseek-r1") ||
			strings.Contains(normalized, "deepseek_r1") ||
			strings.Contains(normalized, "/r1") {
			return true
		}
	}
	if strings.HasPrefix(normalized, "qwq") || strings.Contains(normalized, "-qwq") {
		return true
	}
	return false
}

func isNonChatModel(normalized string) bool {
	// Image / audio / embedding / moderation endpoints do not accept chat JSON mode.
	tokens := []string{
		"embedding", "embed", "whisper", "tts", "dall-e", "dalle",
		"gpt-image", "image-", "-image", "moderation", "realtime",
		"audio", "speech", "transcribe", "asr",
	}
	for _, token := range tokens {
		if strings.Contains(normalized, token) {
			return true
		}
	}
	return false
}
