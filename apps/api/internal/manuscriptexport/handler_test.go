package manuscriptexport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/auth"
	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/workflows"
)

type recordingExporter struct {
	input  workflows.ExportManuscriptArtifactInput
	result workflows.ManuscriptArtifact
	err    error
	calls  int
}

func (e *recordingExporter) ExportManuscriptArtifact(_ context.Context, input workflows.ExportManuscriptArtifactInput) (workflows.ManuscriptArtifact, error) {
	e.calls++
	e.input = input
	return e.result, e.err
}

type staticActorResolver struct {
	actor string
	err   error
}

func (r staticActorResolver) ResolveActor(context.Context, *http.Request) (string, error) {
	return r.actor, r.err
}

type recordingAuthorizer struct {
	input auth.AuthorizeInput
	err   error
	calls int
}

func (a *recordingAuthorizer) Authorize(_ context.Context, input auth.AuthorizeInput) error {
	a.calls++
	a.input = input
	return a.err
}

func TestHandlerDownloadsRealArtifactAfterProjectReadAuthorization(t *testing.T) {
	content := []byte("第一章\n\n真实正文。\n")
	digest := sha256.Sum256(content)
	exporter := &recordingExporter{result: workflows.ManuscriptArtifact{
		ProjectID:   "project-1",
		Format:      "txt",
		FileName:    "project-1-manuscript.txt",
		ContentType: "text/plain; charset=utf-8",
		Content:     content,
		SizeBytes:   int64(len(content)),
		SHA256:      hex.EncodeToString(digest[:]),
		BlockCount:  1,
	}}
	authorizer := &recordingAuthorizer{}
	handler := NewHandler(Config{
		Exporter:      exporter,
		Authorizer:    authorizer,
		ActorResolver: staticActorResolver{actor: "user-1"},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript/export?format=txt", nil)
	request.Header.Set("X-Tenant-Id", "tenant-1")
	request.Header.Set("X-Request-Id", "req-1")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK || response.Body.String() != string(content) {
		t.Fatalf("unexpected artifact response: status=%d body=%q", response.Code, response.Body.String())
	}
	if response.Header().Get("Content-Disposition") != `attachment; filename="project-1-manuscript.txt"` {
		t.Fatalf("missing attachment header: %q", response.Header().Get("Content-Disposition"))
	}
	if response.Header().Get("X-Content-SHA256") != hex.EncodeToString(digest[:]) || response.Header().Get("Cache-Control") != "private, no-store" {
		t.Fatalf("missing integrity/privacy headers: %#v", response.Header())
	}
	if authorizer.calls != 1 || authorizer.input.Permission != auth.PermissionProjectRead || authorizer.input.ProjectID != "project-1" {
		t.Fatalf("unexpected authorization: %#v", authorizer)
	}
	if exporter.calls != 1 || exporter.input.TenantID != "tenant-1" || exporter.input.ProjectID != "project-1" || exporter.input.Format != "txt" {
		t.Fatalf("unexpected exporter invocation: %#v", exporter)
	}
}

func TestHandlerDeniedRequestCannotReadArtifact(t *testing.T) {
	exporter := &recordingExporter{}
	handler := NewHandler(Config{
		Exporter:      exporter,
		Authorizer:    &recordingAuthorizer{err: errors.New("denied prompt api_key=secret")},
		ActorResolver: staticActorResolver{actor: "user-2"},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript/export?format=txt", nil)
	request.Header.Set("X-Tenant-Id", "tenant-1")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusForbidden || exporter.calls != 0 {
		t.Fatalf("denied export reached artifact content: status=%d calls=%d", response.Code, exporter.calls)
	}
	if strings.Contains(response.Body.String(), "api_key") || strings.Contains(response.Body.String(), "prompt") {
		t.Fatalf("denied response leaked backend error: %s", response.Body.String())
	}
}

func TestHandlerSanitizesExporterFailure(t *testing.T) {
	exporter := &recordingExporter{err: errors.New("driver content_text manuscript prompt api_key=secret")}
	handler := NewHandler(Config{
		Exporter:      exporter,
		Authorizer:    &recordingAuthorizer{},
		ActorResolver: staticActorResolver{actor: "user-1"},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript/export?format=txt", nil)
	request.Header.Set("X-Tenant-Id", "tenant-1")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)

	if response.Code != http.StatusInternalServerError || !strings.Contains(response.Body.String(), "manuscript export failed") {
		t.Fatalf("unexpected failure response: status=%d body=%s", response.Code, response.Body.String())
	}
	for _, forbidden := range []string{"content_text", "api_key", "prompt"} {
		if strings.Contains(response.Body.String(), forbidden) {
			t.Fatalf("failure response leaked %q: %s", forbidden, response.Body.String())
		}
	}
}

func TestHandlerDownloadsCompletedStoredArtifactByExportID(t *testing.T) {
	content := []byte("private stable artifact\n")
	digest := sha256.Sum256(content)
	files, err := NewFileArtifactStore(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	reference, err := files.Write(context.Background(), "tenant-1", "project-1", "export-1", content)
	if err != nil {
		t.Fatal(err)
	}
	states := &memoryExportStates{record: manuscriptworkspace.PrivateExportRecord{ExportRecord: manuscriptworkspace.ExportRecord{
		ExportID: "export-1", ProjectID: "project-1", Format: "txt", Status: "completed",
		ArtifactSHA256: hex.EncodeToString(digest[:]), ArtifactSizeBytes: int64(len(content)), BlockCount: 1,
	}, ArtifactObjectRef: reference}}
	handler := NewHandler(Config{States: states, Artifacts: files, Authorizer: &recordingAuthorizer{}, ActorResolver: staticActorResolver{actor: "user-1"}})
	request := httptest.NewRequest(http.MethodGet, "/v1/projects/project-1/manuscript/exports/export-1/download", nil)
	request.Header.Set("X-Tenant-Id", "tenant-1")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK || response.Body.String() != string(content) || response.Header().Get("X-Content-SHA256") != hex.EncodeToString(digest[:]) {
		t.Fatalf("unexpected stored artifact download: status=%d headers=%#v body=%q", response.Code, response.Header(), response.Body.String())
	}
}
