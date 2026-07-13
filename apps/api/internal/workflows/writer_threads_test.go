package workflows

import "testing"

func TestSortWriterThreadMessagesOrdersBySequence(t *testing.T) {
	sorted := SortWriterThreadMessages([]WriterThreadMessage{
		{MessageID: "b", Sequence: 2, CreatedAt: "2026-07-13T00:00:02Z"},
		{MessageID: "a", Sequence: 1, CreatedAt: "2026-07-13T00:00:01Z"},
		{MessageID: "c", Sequence: 3, CreatedAt: "2026-07-13T00:00:03Z"},
	})
	if len(sorted) != 3 || sorted[0].MessageID != "a" || sorted[2].MessageID != "c" {
		t.Fatalf("unexpected order: %#v", sorted)
	}
}

func TestWriterApprovalDecisionEventIsPublicSafe(t *testing.T) {
	payload := WriterApprovalDecisionEvent(WriterApproval{
		ApprovalID: "appr-1",
		Status:     "approved",
		Action:     "adopt_draft",
	}, "approve")
	if payload["approval_id"] != "appr-1" || payload["decision"] != "approve" {
		t.Fatalf("unexpected payload: %#v", payload)
	}
	for _, banned := range []string{"api_key", "prompt", "credential_ref", "raw_body"} {
		if _, ok := payload[banned]; ok {
			t.Fatalf("banned field %s leaked", banned)
		}
	}
}
