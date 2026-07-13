package workflows

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestSQLManuscriptArtifactExporterBuildsRealUTF8TXTFromAdoptedBlocks(t *testing.T) {
	queryer := &recordingTenantWriterEventQueryer{rows: &fakeWriterEventRows{values: [][]any{
		{"block-1", 1, " 第一段\r\n雨声。 "},
		{"block-2", 2, "第二段\n灯灭了。"},
	}}}
	now := time.Date(2026, 7, 10, 8, 30, 0, 0, time.UTC)
	exporter := NewSQLManuscriptArtifactExporter(SQLManuscriptArtifactExporterConfig{
		Queryer: queryer,
		Now:     func() time.Time { return now },
	})

	artifact, err := exporter.ExportManuscriptArtifact(context.Background(), ExportManuscriptArtifactInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		Format:    "txt",
	})
	if err != nil {
		t.Fatalf("export manuscript artifact: %v", err)
	}
	want := "第一段\n雨声。\n\n第二段\n灯灭了。\n"
	if string(artifact.Content) != want {
		t.Fatalf("unexpected artifact content: %q", artifact.Content)
	}
	digest := sha256.Sum256([]byte(want))
	if artifact.SHA256 != hex.EncodeToString(digest[:]) || artifact.SizeBytes != int64(len([]byte(want))) {
		t.Fatalf("artifact integrity metadata mismatch: %#v", artifact)
	}
	if artifact.Format != "txt" || artifact.ContentType != "text/plain; charset=utf-8" || artifact.FileName != "project-1-manuscript.txt" {
		t.Fatalf("unexpected artifact metadata: %#v", artifact)
	}
	if artifact.BlockCount != 2 || artifact.GeneratedAt != now.Format(time.RFC3339Nano) {
		t.Fatalf("unexpected artifact counts/time: %#v", artifact)
	}
	if queryer.plainCalled || queryer.tenantID != "tenant-1" {
		t.Fatalf("export must use tenant-scoped query: %#v", queryer)
	}
	if !strings.Contains(queryer.query, "content_text") || !strings.Contains(queryer.query, "ORDER BY block_order") {
		t.Fatalf("export query must read adopted prose in manuscript order: %s", queryer.query)
	}
}

func TestSQLManuscriptArtifactExporterFailsClosedForEmptyOrUnsupportedExport(t *testing.T) {
	exporter := NewSQLManuscriptArtifactExporter(SQLManuscriptArtifactExporterConfig{
		Queryer: &recordingTenantWriterEventQueryer{rows: &fakeWriterEventRows{}},
	})
	_, err := exporter.ExportManuscriptArtifact(context.Background(), ExportManuscriptArtifactInput{
		TenantID: "tenant-1", ProjectID: "project-1", Format: "txt",
	})
	if ErrorCode(err) != "MANUSCRIPT_EMPTY" {
		t.Fatalf("expected MANUSCRIPT_EMPTY, got %s (%v)", ErrorCode(err), err)
	}

	_, err = exporter.ExportManuscriptArtifact(context.Background(), ExportManuscriptArtifactInput{
		TenantID: "tenant-1", ProjectID: "project-1", Format: "pdf",
	})
	if ErrorCode(err) != "MANUSCRIPT_EXPORT_FORMAT_UNSUPPORTED" {
		t.Fatalf("expected unsupported format, got %s (%v)", ErrorCode(err), err)
	}
}

func TestSQLManuscriptArtifactExporterSanitizesQueryFailures(t *testing.T) {
	exporter := NewSQLManuscriptArtifactExporter(SQLManuscriptArtifactExporterConfig{
		Queryer: &recordingTenantWriterEventQueryer{err: errors.New("driver prompt api_key=secret manuscript body")},
	})
	_, err := exporter.ExportManuscriptArtifact(context.Background(), ExportManuscriptArtifactInput{
		TenantID: "tenant-1", ProjectID: "project-1", Format: "txt",
	})
	if ErrorCode(err) != "MANUSCRIPT_EXPORT_QUERY_FAILED" || err.Error() != "manuscript export query failed" {
		t.Fatalf("expected stable export query failure, got %s (%v)", ErrorCode(err), err)
	}
}
