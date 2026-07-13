package writerplanning

import (
	"regexp"
	"strconv"
	"strings"
	"testing"
)

func TestAdmissionInsertSQLUsesContiguousArguments(t *testing.T) {
	input := StartInput{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1"}
	proposed := Admission{RunID: "run-1", WorkflowType: "writer_book_plan_generation"}
	args := admissionInsertArgs(input, proposed, "temporal-1", "event-1", `{"status":"queued"}`)

	matches := regexp.MustCompile(`\$([0-9]+)`).FindAllStringSubmatch(admitWorkflowSQL, -1)
	seen := make(map[int]bool, len(args))
	for _, match := range matches {
		position, err := strconv.Atoi(match[1])
		if err != nil {
			t.Fatalf("parse placeholder %q: %v", match[0], err)
		}
		seen[position] = true
	}
	if len(args) != 8 {
		t.Fatalf("admission insert argument count = %d, want 8", len(args))
	}
	for position := 1; position <= len(args); position++ {
		if !seen[position] {
			t.Fatalf("admission insert SQL skips parameter $%d", position)
		}
	}
	for position := range seen {
		if position > len(args) {
			t.Fatalf("admission insert SQL references $%d with only %d arguments", position, len(args))
		}
	}
}

func TestBookEventSequenceKeepsUUIDParameterTypesConsistent(t *testing.T) {
	for _, predicate := range []string{
		"tenant_id=$1::uuid",
		"project_id=$2::uuid",
		"book_plan_id=$3::uuid",
	} {
		if !strings.Contains(appendBookEventSQL, predicate) {
			t.Fatalf("book event sequence query is missing typed predicate %q", predicate)
		}
	}
	if strings.Contains(appendBookEventSQL, "::text=$") {
		t.Fatal("book event sequence query compares text columns with UUID parameters")
	}
}
