package assetcatalog

import "testing"

func intPtr(v int) *int { return &v }
func boolPtr(v bool) *bool { return &v }

func TestApplyPatchRecallControlFields(t *testing.T) {
	a := Asset{AssetID: "a1", Title: "铁律"}
	content := "body"
	contentPtr := &content

	// always_on toggles on; a positive reveal gate is set.
	applyPatch(&a, &contentPtr, AssetPatch{AlwaysOn: boolPtr(true), RevealAfterChapterOrder: intPtr(12)})
	if !a.AlwaysOn {
		t.Fatal("always_on not applied")
	}
	if a.RevealAfterChapterOrder == nil || *a.RevealAfterChapterOrder != 12 {
		t.Fatalf("reveal gate not applied: %+v", a.RevealAfterChapterOrder)
	}

	// A negative reveal gate clears it back to always-visible (NULL).
	applyPatch(&a, &contentPtr, AssetPatch{RevealAfterChapterOrder: intPtr(-1)})
	if a.RevealAfterChapterOrder != nil {
		t.Fatalf("negative reveal gate should clear to NULL, got %+v", *a.RevealAfterChapterOrder)
	}

	// Unset fields leave the asset untouched (partial patch semantics).
	before := a
	applyPatch(&a, &contentPtr, AssetPatch{Title: strPtrLocal("新标题")})
	if a.AlwaysOn != before.AlwaysOn || a.RevealAfterChapterOrder != before.RevealAfterChapterOrder {
		t.Fatal("recall control fields clobbered by an unrelated patch")
	}
}

func TestVersionSnapshotCarriesAlwaysOn(t *testing.T) {
	a := Asset{AssetID: "a1", Title: "铁律", AlwaysOn: true, Pinned: true}
	env := envelopeFromAsset(a, nil)
	if !env.Snapshot.AlwaysOn {
		t.Fatal("always_on must be captured in the version snapshot so restore preserves it")
	}
}

func strPtrLocal(s string) *string { return &s }
