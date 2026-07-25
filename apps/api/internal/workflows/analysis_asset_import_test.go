package workflows

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestMapAnalysisCandidateToAssetCharacter(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary": "主角之一",
		"tags":    []any{"主线", "pi_analysis"},
	})
	mapped := mapAnalysisCandidateToAsset("character", "林深", "30-candidates/characters.json", payload)
	if mapped.assetType != "character" {
		t.Fatalf("assetType=%q", mapped.assetType)
	}
	if mapped.category != "characters" {
		t.Fatalf("category=%q", mapped.category)
	}
	if mapped.title != "林深" {
		t.Fatalf("title=%q", mapped.title)
	}
	if mapped.summary != "主角之一" {
		t.Fatalf("summary=%q", mapped.summary)
	}
	var tags []string
	if err := json.Unmarshal(mapped.tagsJSON, &tags); err != nil {
		t.Fatal(err)
	}
	if !containsString(tags, "pi_analysis") || !containsString(tags, "character") {
		t.Fatalf("tags=%v", tags)
	}
	var body map[string]any
	if err := json.Unmarshal(mapped.payloadJSON, &body); err != nil {
		t.Fatal(err)
	}
	if body["auto_imported"] != true {
		t.Fatalf("auto_imported=%v", body["auto_imported"])
	}
}

func TestMapAnalysisCandidateToAssetNoteSummary(t *testing.T) {
	mapped := mapAnalysisCandidateToAsset("note_summary", "", "", nil)
	if mapped.assetType != "note" {
		t.Fatalf("assetType=%q", mapped.assetType)
	}
	// With no payload to draw from, the title must still not be the bare
	// machine placeholder repeated verbatim as content.
	if isTypeKeyTitle(mapped.title) && mapped.title == "note_summary" {
		t.Fatalf("title fell back to placeholder %q", mapped.title)
	}
	if mapped.category != "analysis" {
		t.Fatalf("category=%q", mapped.category)
	}
}

func TestMapAnalysisCandidateToAssetPlotEvent(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary":      "沈翠花夜探青山医院，发现冰流异动",
		"timeframe":    "第1天·夜",
		"world":        "modern",
		"participants": []any{"沈翠花", "青山医院"},
	})
	mapped := mapAnalysisCandidateToAsset("plot_event", "plot_event", "30-candidates/timeline.json", payload)
	if mapped.assetType != "plot_event" {
		t.Fatalf("assetType=%q", mapped.assetType)
	}
	if mapped.category != "plot" {
		t.Fatalf("category=%q", mapped.category)
	}
	// Placeholder name "plot_event" must not win; the Chinese summary composes the title.
	if mapped.title == "plot_event" || isTypeKeyTitle(mapped.title) {
		t.Fatalf("title fell back to placeholder %q", mapped.title)
	}
	if !strings.Contains(mapped.title, "沈翠花夜探青山医院") {
		t.Fatalf("title=%q", mapped.title)
	}
	var body map[string]any
	if err := json.Unmarshal(mapped.payloadJSON, &body); err != nil {
		t.Fatal(err)
	}
	if body["analysis_candidate_type"] != "plot_event" {
		t.Fatalf("analysis_candidate_type=%v", body["analysis_candidate_type"])
	}
}

func TestMapAnalysisCandidateToAssetPlotEventTimeframeFallback(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{"timeframe": "第2天·晨"})
	mapped := mapAnalysisCandidateToAsset("plot_event", "", "", payload)
	if !strings.Contains(mapped.title, "未命名事件") {
		t.Fatalf("expected readable untitled tag, got %q", mapped.title)
	}
	if isTypeKeyTitle(mapped.title) {
		t.Fatalf("title fell back to type key %q", mapped.title)
	}
}

func TestMapAnalysisCandidateToAssetNoteSummaryFromPayload(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary": "第一章揭示了林深身世与山海界入口",
	})
	mapped := mapAnalysisCandidateToAsset("note_summary", "note_summary", "", payload)
	if mapped.assetType != "note" {
		t.Fatalf("assetType=%q", mapped.assetType)
	}
	if mapped.title == "note_summary" {
		t.Fatalf("expected composed title, got %q", mapped.title)
	}
	if !strings.Contains(mapped.title, "第一章揭示了林深身世") {
		t.Fatalf("title=%q", mapped.title)
	}
}

func TestMapAnalysisCandidateToAssetRelationshipComposedTitle(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"source":            "林深",
		"target":            "静妃",
		"relationship_type": "师徒",
		"description":       "静妃指点林深修炼",
	})
	mapped := mapAnalysisCandidateToAsset("relationship", "relationship", "", payload)
	want := "林深 → 静妃 / 师徒"
	if mapped.title != want {
		t.Fatalf("title=%q want %q", mapped.title, want)
	}
	if mapped.summary != "静妃指点林深修炼" {
		t.Fatalf("summary=%q", mapped.summary)
	}
	if !strings.Contains(mapped.contentText, "林深 → 静妃") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
}

func TestMapAnalysisCandidateToAssetRelationshipFromToAliases(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"from": "A",
		"to":   "B",
		"kind": "盟友",
	})
	mapped := mapAnalysisCandidateToAsset("relationship", "", "", payload)
	if mapped.title != "A → B / 盟友" {
		t.Fatalf("title=%q", mapped.title)
	}
}

func TestMapAnalysisCandidateToAssetOntology(t *testing.T) {
	mapped := mapAnalysisCandidateToAsset("ontology", strings.Repeat("x", 300), "", []byte(`{"description":"世界设定"}`))
	if mapped.assetType != "story_ontology" {
		t.Fatalf("assetType=%q", mapped.assetType)
	}
	if len(mapped.title) != 240 {
		t.Fatalf("title len=%d", len(mapped.title))
	}
	if mapped.summary != "世界设定" {
		t.Fatalf("summary=%q", mapped.summary)
	}
}

func TestMapAnalysisCandidateToAssetCharacterRichBody(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary":     "军情司新人",
		"description": "陈迹，舅舅陈守一培养的刀客，性格隐忍，为查父案潜入京城。",
	})
	mapped := mapAnalysisCandidateToAsset("character", "陈迹", "30-candidates/characters.json", payload)
	if mapped.summary != "军情司新人" {
		t.Fatalf("summary=%q", mapped.summary)
	}
	if !strings.Contains(mapped.contentText, "陈迹，舅舅陈守一培养的刀客") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
	if !strings.Contains(mapped.contentText, "军情司新人") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
}

func TestMapAnalysisCandidateToAssetCharacterBodyPreferred(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary": "短摘要",
		"body":    "一段完整的中文人物档案，覆盖身份、性格、动机与主线弧光。",
	})
	mapped := mapAnalysisCandidateToAsset("character", "白鲤郡主", "", payload)
	if mapped.contentText != "一段完整的中文人物档案，覆盖身份、性格、动机与主线弧光。" {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
}

func TestMapAnalysisCandidateToAssetWorldRuleRichBody(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary":    "以太阳养剑可行",
		"rule_text":  "以太阳真火淬炼本命剑可成，但需每月朔日避雷劫，且耗寿三年。",
		"evidence":   "第二十一章：烈阳宗以日精养剑。",
		"category":   "world",
		"confidence": "0.9",
	})
	mapped := mapAnalysisCandidateToAsset("world_rule", "", "30-candidates/world_rules.json", payload)
	if mapped.summary != "以太阳养剑可行" {
		t.Fatalf("summary=%q", mapped.summary)
	}
	if !strings.Contains(mapped.contentText, "以太阳真火淬炼本命剑可成") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
	if !strings.Contains(mapped.contentText, "证据：第二十一章") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
	if !strings.Contains(mapped.contentText, "分类：world") || !strings.Contains(mapped.contentText, "置信度：0.9") {
		t.Fatalf("contentText=%q", mapped.contentText)
	}
}

func TestMapAnalysisCandidateToAssetPlotEventRichBody(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary":      "沈翠花夜探青山医院，发现冰流异动",
		"timeframe":    "第1天·夜",
		"world":        "modern",
		"participants": []any{"沈翠花", "青山医院"},
	})
	mapped := mapAnalysisCandidateToAsset("plot_event", "", "30-candidates/timeline.json", payload)
	for _, want := range []string{"沈翠花夜探青山医院", "时间：第1天·夜", "世界：modern", "涉及：沈翠花、青山医院"} {
		if !strings.Contains(mapped.contentText, want) {
			t.Fatalf("contentText missing %q: %q", want, mapped.contentText)
		}
	}
}

func TestMapAnalysisCandidateToAssetRelationshipEvidenceBody(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"source":            "陈迹",
		"target":            "陈守一",
		"relationship_type": "舅甥",
		"description":       "舅舅培养陈迹进入军情司",
		"evidence":          "第一章：陈守一安排陈迹顶替名额入伍。",
	})
	mapped := mapAnalysisCandidateToAsset("relationship", "", "", payload)
	for _, want := range []string{"陈迹 → 陈守一", "舅舅培养陈迹进入军情司", "证据：第一章"} {
		if !strings.Contains(mapped.contentText, want) {
			t.Fatalf("contentText missing %q: %q", want, mapped.contentText)
		}
	}
}

func TestMapAnalysisCandidateToAssetSummaryPrefersShortField(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{
		"summary":     "一句短摘要",
		"description": "一段很长很长很长很長的描述，不应抢占摘要位置。",
	})
	mapped := mapAnalysisCandidateToAsset("character", "某人", "", payload)
	if mapped.summary != "一句短摘要" {
		t.Fatalf("summary=%q", mapped.summary)
	}
}
