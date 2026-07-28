package assetdistillation

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestCollectAliasesDedupesCanonicalAndHints(t *testing.T) {
	aliases := collectAliases(map[string]any{
		"aliases":        []any{"林晚", "林小姐"},
		"identity_hints": []string{"晚晚", "林晚"},
		"aka":            "小晚, 林小姐",
	}, "林晚")
	if len(aliases) != 3 {
		t.Fatalf("expected 3 unique aliases, got %#v", aliases)
	}
	joined := "|" + strings.Join(aliases, "|") + "|"
	for _, want := range []string{"林小姐", "晚晚", "小晚"} {
		if !strings.Contains(joined, "|"+want+"|") {
			t.Fatalf("missing alias %q in %#v", want, aliases)
		}
	}
}

func TestSplitRelationshipTitle(t *testing.T) {
	parts := splitRelationshipTitle("林晚 / 陈舟")
	if len(parts) != 2 || parts[0] != "林晚" || parts[1] != "陈舟" {
		t.Fatalf("slash title: %#v", parts)
	}
	parts = splitRelationshipTitle("林晚 -> 陈舟")
	if len(parts) != 2 || parts[0] != "林晚" || parts[1] != "陈舟" {
		t.Fatalf("arrow title: %#v", parts)
	}
	if splitRelationshipTitle("solo name") != nil {
		t.Fatalf("expected nil for non-pair title")
	}
}

func TestSplitRelationshipTitleChinese(t *testing.T) {
	cases := []struct {
		title          string
		source, target string
	}{
		{"李玉春与许七安的交易", "李玉春", "许七安"},
		{"林晚和陈舟", "林晚", "陈舟"},
		{"林晚跟陈舟的恩怨", "林晚", "陈舟"},
		{"林晚同陈舟的同盟", "林晚", "陈舟"},
		{"林晚对陈舟的仇恨", "林晚", "陈舟"},
		{"林晚、陈舟", "林晚", "陈舟"},
		{"林晚与陈舟", "林晚", "陈舟"},
	}
	for _, tc := range cases {
		parts := splitRelationshipTitle(tc.title)
		if len(parts) != 2 || parts[0] != tc.source || parts[1] != tc.target {
			t.Fatalf("%q: got %#v, want [%q %q]", tc.title, parts, tc.source, tc.target)
		}
	}
}

func TestPayloadHelpers(t *testing.T) {
	payload := map[string]any{
		"source_entity_name": "林晚",
		"confidence":         json.Number("0.85"),
		"extra":              2,
	}
	if got := payloadString(payload, "source_entity_name"); got != "林晚" {
		t.Fatalf("payloadString: %q", got)
	}
	if got, ok := payloadFloat(payload, "confidence"); !ok || got != 0.85 {
		t.Fatalf("payloadFloat confidence: %v %v", got, ok)
	}
	if got, ok := payloadFloat(payload, "extra"); !ok || got != 2 {
		t.Fatalf("payloadFloat int: %v %v", got, ok)
	}
	if firstNonEmpty("", " ", "x") != "x" {
		t.Fatalf("firstNonEmpty failed")
	}
}

func TestGraphProjectableTypes(t *testing.T) {
	for _, typ := range []string{"character", "relationship", "world_rule", "plot_thread"} {
		if _, ok := graphProjectableAssetTypes[typ]; !ok {
			t.Fatalf("missing projectable type %s", typ)
		}
	}
	if _, ok := graphProjectableAssetTypes["location"]; ok {
		t.Fatalf("location must not project into graph source tables via CONN-003 path")
	}
}
