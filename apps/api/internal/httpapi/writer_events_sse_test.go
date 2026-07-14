package httpapi

import (
	"context"
	"fmt"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/workflows"
)

// paginatedWriterEventReader mimics the SQL reader's page-size behaviour: each
// call returns at most pageSize events strictly after the cursor.
type paginatedWriterEventReader struct {
	events   []workflows.WriterEvent
	pageSize int
	calls    int
}

func (r *paginatedWriterEventReader) ListWriterEvents(_ context.Context, input workflows.ListWriterEventsInput) ([]workflows.WriterEvent, error) {
	r.calls++
	start := 0
	if cursor := strings.TrimSpace(input.AfterEventID); cursor != "" {
		for index, event := range r.events {
			if event.EventID == cursor {
				start = index + 1
				break
			}
		}
	}
	end := start + r.pageSize
	if end > len(r.events) {
		end = len(r.events)
	}
	page := make([]workflows.WriterEvent, end-start)
	copy(page, r.events[start:end])
	return page, nil
}

func writerEventFixture(sequence int, eventType string) workflows.WriterEvent {
	return workflows.WriterEvent{
		EventID:   "evt-" + strconv.Itoa(sequence),
		RunID:     "run-1",
		ProjectID: "project-1",
		Sequence:  sequence,
		EventType: eventType,
		Payload:   map[string]any{},
	}
}

// A finished run with more events than one reader page must still stream every
// remaining page down to the terminal event instead of stopping after page one.
func TestDrainWriterEventsSSEPagesToTerminalEvent(t *testing.T) {
	total := 230
	events := make([]workflows.WriterEvent, 0, total)
	for sequence := 1; sequence <= total-1; sequence++ {
		events = append(events, writerEventFixture(sequence, "writer.token"))
	}
	events = append(events, writerEventFixture(total, "writer.run.completed"))
	reader := &paginatedWriterEventReader{events: events, pageSize: 100}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest("GET", "/v1/writer-runs/run-1/events?stream=1", nil)

	drainWriterEventsSSE(request, recorder, nil, reader, "tenant-1", "run-1", "evt-100")

	body := recorder.Body.String()
	if !strings.Contains(body, "writer.run.completed") {
		t.Fatalf("terminal event missing from drained stream")
	}
	for _, sequence := range []int{101, 150, 200, total} {
		if !strings.Contains(body, fmt.Sprintf("id: evt-%d\n", sequence)) {
			t.Fatalf("event %d missing from drained stream", sequence)
		}
	}
	if strings.Contains(body, "id: evt-100\n") {
		t.Fatalf("drain replayed events at or before the cursor")
	}
	if reader.calls < 2 {
		t.Fatalf("expected multiple pages, reader called %d times", reader.calls)
	}
}

// Draining must terminate when the store has no further events even without a
// terminal event (e.g. events written by an older runtime build).
func TestDrainWriterEventsSSEStopsOnEmptyPage(t *testing.T) {
	reader := &paginatedWriterEventReader{
		events:   []workflows.WriterEvent{writerEventFixture(1, "writer.token")},
		pageSize: 100,
	}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest("GET", "/v1/writer-runs/run-1/events?stream=1", nil)

	drainWriterEventsSSE(request, recorder, nil, reader, "tenant-1", "run-1", "")

	if !strings.Contains(recorder.Body.String(), "id: evt-1\n") {
		t.Fatalf("expected the stored event in the stream")
	}
	if reader.calls != 2 {
		t.Fatalf("expected exactly two reader calls (page + empty), got %d", reader.calls)
	}
}
