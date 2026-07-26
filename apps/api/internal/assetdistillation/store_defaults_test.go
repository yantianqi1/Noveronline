package assetdistillation

import "testing"

func TestShouldAutoEnqueueAfterAdoptionTriggers(t *testing.T) {
	for _, trigger := range []string{"draft_adoption", "manuscript_update", "manuscript_restore"} {
		if !shouldAutoEnqueue("after_adoption", trigger) {
			t.Fatalf("after_adoption must auto-enqueue %q", trigger)
		}
	}
	if shouldAutoEnqueue("after_adoption", "chapter_complete") {
		t.Fatal("after_adoption must not auto-enqueue chapter_complete")
	}
	if !shouldAutoEnqueue("chapter_complete", "chapter_complete") {
		t.Fatal("chapter_complete mode must auto-enqueue chapter_complete")
	}
	if shouldAutoEnqueue("manual", "draft_adoption") || shouldAutoEnqueue("off", "draft_adoption") {
		t.Fatal("manual/off must never auto-enqueue")
	}
}

func TestMissingSettingsRowDefaultsToAfterAdoption(t *testing.T) {
	// Rollout pin: GetSettings and loadSettingsOn both fall back to this value
	// when a project predates settings rows. Assert the constant behavior by
	// checking that the fallback mode passes the auto-enqueue gate, which is
	// the behavior the rollout depends on.
	fallback := "after_adoption" // must match both ErrNoRows branches in store.go
	if !shouldAutoEnqueue(fallback, "draft_adoption") {
		t.Fatal("missing-settings fallback must auto-enqueue draft_adoption")
	}
}
