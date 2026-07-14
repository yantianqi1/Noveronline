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
	if mapped.title != "note_summary" {
		t.Fatalf("title=%q", mapped.title)
	}
	if mapped.category != "analysis" {
		t.Fatalf("category=%q", mapped.category)
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
