package manuscriptexport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/workflows"
)

type memoryExportStates struct {
	record   manuscriptworkspace.PrivateExportRecord
	replay   bool
	failCode string
}

func (s *memoryExportStates) CreateExport(_ context.Context, input manuscriptworkspace.CreateExportInput) (manuscriptworkspace.ExportRecord, bool, error) {
	if s.record.ExportID == "" {
		s.record = manuscriptworkspace.PrivateExportRecord{ExportRecord: manuscriptworkspace.ExportRecord{ExportID: "export-1", ProjectID: input.ProjectID, Format: input.Format, Status: "queued"}}
	}
	return s.record.ExportRecord, s.replay, nil
}
func (s *memoryExportStates) MarkExportGenerating(context.Context, manuscriptworkspace.Scope, string) (manuscriptworkspace.ExportRecord, error) {
	s.record.Status = "generating"
	return s.record.ExportRecord, nil
}
func (s *memoryExportStates) CompleteExport(_ context.Context, input manuscriptworkspace.CompleteExportInput) (manuscriptworkspace.PrivateExportRecord, error) {
	s.record.Status = "completed"
	s.record.ArtifactSHA256 = input.ArtifactSHA256
	s.record.ArtifactSizeBytes = input.ArtifactSizeBytes
	s.record.ArtifactObjectRef = input.ArtifactObjectRef
	s.record.BlockCount = input.BlockCount
	return s.record, nil
}
func (s *memoryExportStates) FailExport(_ context.Context, _ manuscriptworkspace.Scope, _ string, code string) (manuscriptworkspace.ExportRecord, error) {
	s.failCode = code
	s.record.Status = "failed"
	s.record.ErrorCode = code
	return s.record.ExportRecord, nil
}
func (s *memoryExportStates) ListExports(context.Context, manuscriptworkspace.Scope) ([]manuscriptworkspace.ExportRecord, error) {
	return []manuscriptworkspace.ExportRecord{s.record.ExportRecord}, nil
}
func (s *memoryExportStates) GetPrivateExport(context.Context, manuscriptworkspace.Scope, string) (manuscriptworkspace.PrivateExportRecord, error) {
	return s.record, nil
}

func TestGeneratorPersistsRealPrivateArtifactBeforeCompletingState(t *testing.T) {
	content := []byte("Chapter one\n\nPrivate manuscript.\n")
	digest := sha256.Sum256(content)
	states := &memoryExportStates{}
	files, err := NewFileArtifactStore(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	generator := NewGenerator(GeneratorConfig{
		States: states,
		Exporter: &recordingExporter{result: workflows.ManuscriptArtifact{
			ProjectID: "project-1", Format: "txt", Content: content, SizeBytes: int64(len(content)),
			SHA256: hex.EncodeToString(digest[:]), BlockCount: 1,
		}},
		Artifacts: files,
	})
	record, replay, err := generator.GenerateExport(context.Background(), manuscriptworkspace.CreateExportInput{
		Scope: manuscriptworkspace.Scope{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1"}, Format: "txt",
	})
	if err != nil || replay || record.Status != "completed" || record.ArtifactSHA256 != hex.EncodeToString(digest[:]) || record.ArtifactSizeBytes != int64(len(content)) {
		t.Fatalf("unexpected completed artifact: record=%#v replay=%v err=%v", record, replay, err)
	}
	if states.record.ArtifactObjectRef == "" || filepath.IsAbs(states.record.ArtifactObjectRef) {
		t.Fatalf("artifact reference must be private and relative: %#v", states.record)
	}
	stored, err := files.Read(context.Background(), states.record.ArtifactObjectRef)
	if err != nil || string(stored) != string(content) {
		t.Fatalf("stored artifact mismatch: %q err=%v", stored, err)
	}
}

func TestGeneratorFailsStateWithoutLeakingRendererError(t *testing.T) {
	states := &memoryExportStates{}
	files, _ := NewFileArtifactStore(t.TempDir())
	generator := NewGenerator(GeneratorConfig{States: states, Exporter: &recordingExporter{err: errors.New("private manuscript api_key=secret")}, Artifacts: files})
	_, _, err := generator.GenerateExport(context.Background(), manuscriptworkspace.CreateExportInput{
		Scope: manuscriptworkspace.Scope{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1"}, Format: "txt",
	})
	if manuscriptworkspace.ErrorCode(err) != "MANUSCRIPT_ARTIFACT_GENERATION_FAILED" || states.failCode != "ARTIFACT_RENDER_FAILED" {
		t.Fatalf("unexpected sanitized generation failure: code=%s state=%q err=%v", manuscriptworkspace.ErrorCode(err), states.failCode, err)
	}
}

func TestGeneratorCompletedReplayDoesNotRenderOrRewriteArtifact(t *testing.T) {
	states := &memoryExportStates{replay: true, record: manuscriptworkspace.PrivateExportRecord{ExportRecord: manuscriptworkspace.ExportRecord{
		ExportID: "export-1", ProjectID: "project-1", Format: "txt", Status: "completed",
		ArtifactSHA256: strings.Repeat("a", 64), ArtifactSizeBytes: 12, BlockCount: 1,
	}, ArtifactObjectRef: "private/artifact.txt"}}
	exporter := &recordingExporter{err: errors.New("renderer must not run")}
	files, _ := NewFileArtifactStore(t.TempDir())
	record, replay, err := NewGenerator(GeneratorConfig{States: states, Exporter: exporter, Artifacts: files}).GenerateExport(
		context.Background(), manuscriptworkspace.CreateExportInput{
			Scope: manuscriptworkspace.Scope{TenantID: "tenant-1", ProjectID: "project-1", ActorUserID: "user-1", RequestID: "request-1"}, Format: "txt",
		})
	if err != nil || !replay || record.Status != "completed" || exporter.calls != 0 {
		t.Fatalf("completed replay performed side effects: record=%#v replay=%v calls=%d err=%v", record, replay, exporter.calls, err)
	}
}

func TestFileArtifactStoreRejectsEscapingReference(t *testing.T) {
	root := t.TempDir()
	store, _ := NewFileArtifactStore(root)
	if _, err := store.Read(context.Background(), "../private.txt"); err == nil {
		t.Fatal("artifact store accepted path traversal")
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(root), "private.txt")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("unexpected escaped artifact: %v", err)
	}
}
