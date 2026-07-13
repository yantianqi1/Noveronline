package workflows

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/sourcefiles"
	"mirofish-novel/apps/api/internal/testschema"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

const liveSeedTenantID = "81111111-1111-1111-1111-111111111111"
const liveSeedUserID = "82222222-2222-2222-2222-222222222222"
const liveSeedUserEmail = "seed-go-live@example.test"
const liveSeedProjectID = "83333333-3333-3333-3333-333333333333"
const liveSeedRunID = "84444444-4444-4444-4444-444444444444"
const liveSeedAppRole = "mirofish_seed_go_live_app"
const liveSeedAppPassword = "mirofish_seed_go_live_password"

func TestLiveSeedGoUploadCompleteAndAdmissionUseMinIOAndAppRole(t *testing.T) {
	adminURL := os.Getenv("MIROFISH_SEED_LIVE_DATABASE_URL")
	if strings.TrimSpace(adminURL) == "" {
		t.Skip("set MIROFISH_SEED_LIVE_DATABASE_URL to run live Seed Go upload/complete/admission E2E")
	}
	storageConfig := liveSeedObjectStorageConfig(t)
	requireLiveSeedDisposableDatabase(t, adminURL)
	objectKey := ""
	t.Cleanup(func() {
		cleanupLiveSeedGoFixture(t, adminURL, storageConfig, objectKey)
	})
	prepareLiveSeedGoDatabase(t, adminURL)
	appURL := liveSeedAppDatabaseURL(t, adminURL)
	appDB, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatalf("open app db: %v", err)
	}
	t.Cleanup(func() { _ = appDB.Close() })
	writer, err := sourcefiles.NewMinIOObjectWriter(storageConfig)
	if err != nil {
		t.Fatalf("new minio writer: %v", err)
	}
	verifier, err := sourcefiles.NewMinIOObjectVerifier(sourcefiles.MinIOObjectVerifierConfig(storageConfig))
	if err != nil {
		t.Fatalf("new minio verifier: %v", err)
	}
	sourceStore := sourcefiles.NewSQLStore(sourcefiles.SQLStoreConfig{
		Queryer:        sourcefiles.NewSQLDBQueryer(appDB),
		ObjectVerifier: verifier,
	})
	sourceBytes := []byte("第一章 雨夜\n雨声压住脚步。\n")
	sourceHash := sha256.Sum256(sourceBytes)

	record, err := sourceStore.CreateSourceFile(context.Background(), sourcefiles.CreateInput{
		TenantID:    liveSeedTenantID,
		ProjectID:   liveSeedProjectID,
		ActorUserID: liveSeedUserID,
		Filename:    "go-live-seed.txt",
		MimeType:    "text/plain",
		SizeBytes:   int64(len(sourceBytes)),
		SHA256:      hex.EncodeToString(sourceHash[:]),
		Purpose:     "seed",
	})
	if err != nil {
		t.Fatalf("create source file: %v", err)
	}
	if record.ParseStatus != "pending" {
		t.Fatalf("expected pending source file, got %#v", record)
	}

	objectInput, err := sourceStore.GetUploadObject(context.Background(), sourcefiles.GetUploadObjectInput{
		TenantID: liveSeedTenantID,
		UploadID: record.UploadID,
	})
	if err != nil {
		t.Fatalf("get upload object metadata: %v", err)
	}
	objectKey = objectInput.ObjectKey
	if err := writer.WriteObject(context.Background(), objectInput, bytes.NewReader(sourceBytes)); err != nil {
		t.Fatalf("write source object: %v", err)
	}
	completed, err := sourceStore.CompleteUpload(context.Background(), sourcefiles.CompleteInput{
		TenantID: liveSeedTenantID,
		UploadID: record.UploadID,
	})
	if err != nil {
		t.Fatalf("complete upload: code=%s err=%v", sourcefiles.ErrorCode(err), err)
	}
	if completed.ParseStatus != "uploaded" {
		t.Fatalf("expected uploaded source after object verification, got %#v", completed)
	}
	validated, err := sourceStore.ValidateSourceFile(context.Background(), sourcefiles.ValidateInput{
		TenantID:  liveSeedTenantID,
		ProjectID: liveSeedProjectID,
		UploadID:  record.UploadID,
	})
	if err != nil {
		t.Fatalf("validate completed source: %v", err)
	}
	if validated.ObjectKey != objectInput.ObjectKey || validated.SHA256 != objectInput.SHA256 {
		t.Fatalf("validated source metadata mismatch")
	}

	admissionStore := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{
		Execer: NewSQLDBWriterAdmissionExecer(appDB),
	})
	err = admissionStore.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           liveSeedTenantID,
		ProjectID:          liveSeedProjectID,
		RunID:              liveSeedRunID,
		TraceID:            "trace_" + liveSeedRunID,
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_" + liveSeedRunID,
		ActorUserID:        liveSeedUserID,
		RequestID:          "req-live-seed-go",
		UploadID:           record.UploadID,
		SourceFileID:       record.FileID,
		Status:             "queued",
	})
	if err != nil {
		t.Fatalf("admit seed run: %v", err)
	}

	persisted := readLiveSeedGoAdmissionRows(t, adminURL, record.UploadID)
	if persisted.SourceStatus != "parsing" {
		t.Fatalf("expected admission to advance source to parsing")
	}
	if persisted.WorkflowStatus != "queued" || persisted.WorkflowType != SeedWorkflowType {
		t.Fatalf("unexpected workflow admission row")
	}
	if persisted.EventType != "workflow.queued" {
		t.Fatalf("expected queued workflow event")
	}
	payloadJSON := mustJSON(t, persisted.EventPayload)
	if !strings.Contains(payloadJSON, "source_file_id") || !strings.Contains(payloadJSON, record.FileID) {
		t.Fatalf("expected queued event to include source file metadata")
	}
	assertLiveSeedGoTextDoesNotContainMarkers(t, payloadJSON, "workflow admission payload", []liveSeedForbiddenMarker{
		{Name: "object key", Value: objectInput.ObjectKey},
		{Name: "object key field", Value: "object_key"},
		{Name: "source object key field", Value: "source_object_key"},
		{Name: "source title", Value: "第一章"},
		{Name: "source body", Value: "雨声压住脚步"},
		{Name: "api key marker", Value: "api_key"},
		{Name: "credential ref marker", Value: "credential_ref"},
		{Name: "draft marker", Value: "draft"},
		{Name: "manuscript marker", Value: "manuscript"},
	})
}

func TestLiveSeedGoWorkflowRetryPostgresMinIOUsesStoredSourceHandoffWithRecordingTemporal(t *testing.T) {
	fixture := prepareLiveSeedGoRetryFixture(t)
	markLiveSeedGoRunFailedForRetry(t, fixture.AdminURL, fixture.Record.UploadID, fixture.Record.FileID)

	temporalClient := &recordingRetryTemporalClient{}
	retrier := NewTemporalWorkflowRetrier(TemporalWorkflowRetrierConfig{
		Client: temporalClient,
		Store: NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{
			Queryer: NewSQLDBWriterEventQueryer(fixture.AppDB),
			Execer:  NewSQLDBWriterAdmissionExecer(fixture.AppDB),
		}),
	})
	retried, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID:    liveSeedTenantID,
		RunID:       liveSeedRunID,
		ActorUserID: liveSeedUserID,
		RequestID:   "req-live-seed-retry",
	})
	if err != nil {
		t.Fatalf("retry seed run failed with code %s", ErrorCode(err))
	}
	if retried.RunID != liveSeedRunID || retried.Status != "retry_requested" {
		t.Fatalf("unexpected retry result: %#v", retried)
	}
	if temporalClient.workflowID != "seed_run_"+liveSeedRunID+"_retry" || temporalClient.workflowName != SeedWorkflowName {
		t.Fatalf("unexpected retry Temporal start: id=%q workflow=%#v", temporalClient.workflowID, temporalClient.workflowName)
	}
	if temporalClient.options.TaskQueue != SeedTaskQueue {
		t.Fatalf("retry Temporal start lost seed task queue: %#v", temporalClient.options)
	}
	payload, ok := temporalClient.args[0].(map[string]any)
	if !ok {
		t.Fatalf("expected retry Temporal payload map")
	}
	if payload["source_file_id"] != fixture.Record.FileID ||
		payload["source_object_key"] != fixture.ObjectInput.ObjectKey ||
		payload["source_sha256"] != fixture.ObjectInput.SHA256 ||
		payload["source_size_bytes"] != fixture.ObjectInput.SizeBytes {
		t.Fatalf("retry Temporal payload lost stored source handoff")
	}

	persisted := readLiveSeedGoRetryRows(t, fixture.AdminURL, fixture.Record.UploadID)
	if persisted.SourceStatus != "parsing" || persisted.WorkflowStatus != "queued" {
		t.Fatalf("retry did not reset run/source state")
	}
	if persisted.TemporalWorkflowID != "seed_run_"+liveSeedRunID+"_retry" {
		t.Fatalf("retry did not persist retry temporal workflow id")
	}
	if persisted.EventType != "workflow.retry_requested" || persisted.EventSequence != 2 {
		t.Fatalf("expected retry event sequence")
	}
	payloadJSON := mustJSON(t, persisted.EventPayload)
	if !strings.Contains(payloadJSON, fixture.Record.UploadID) || !strings.Contains(payloadJSON, fixture.Record.FileID) || !strings.Contains(payloadJSON, "req-live-seed-retry") {
		t.Fatalf("retry event lost public source correlation metadata")
	}
	assertLiveSeedGoTextDoesNotContainMarkers(t, payloadJSON, "retry event payload", liveSeedGoRetryForbiddenMarkers(fixture))
}

func TestLiveSeedGoWorkflowRetryPostgresMinIOStartFailureReleasesSourceWithRecordingTemporal(t *testing.T) {
	fixture := prepareLiveSeedGoRetryFixture(t)
	markLiveSeedGoRunFailedForRetry(t, fixture.AdminURL, fixture.Record.UploadID, fixture.Record.FileID)

	temporalClient := &recordingRetryTemporalClient{
		err: errors.New("provider response raw content prompt api_key=secret encrypted credential credential_ref=ref object_key=private draft manuscript"),
	}
	retrier := NewTemporalWorkflowRetrier(TemporalWorkflowRetrierConfig{
		Client: temporalClient,
		Store: NewSQLWorkflowRetryStore(SQLWorkflowRetryStoreConfig{
			Queryer: NewSQLDBWriterEventQueryer(fixture.AppDB),
			Execer:  NewSQLDBWriterAdmissionExecer(fixture.AppDB),
		}),
	})
	_, err := retrier.RetryWorkflowRun(context.Background(), RetryWorkflowRunInput{
		TenantID:    liveSeedTenantID,
		RunID:       liveSeedRunID,
		ActorUserID: liveSeedUserID,
		RequestID:   "req-live-seed-retry-failed",
	})
	if code := ErrorCode(err); code != "WORKFLOW_RETRY_FAILED" {
		t.Fatalf("expected stable retry failure, got code %s", code)
	}
	if err != nil {
		errText := err.Error()
		assertLiveSeedGoTextDoesNotContainMarkers(t, errText, "retry error", liveSeedGoRetryForbiddenMarkers(fixture))
	}

	persisted := readLiveSeedGoRetryRows(t, fixture.AdminURL, fixture.Record.UploadID)
	if persisted.SourceStatus != "uploaded" || persisted.WorkflowStatus != "failed" {
		t.Fatalf("retry start failure did not release source and fail run")
	}
	if persisted.TemporalWorkflowID != "seed_run_"+liveSeedRunID+"_retry" {
		t.Fatalf("retry failure should retain retry temporal workflow id for diagnostics")
	}
	if persisted.EventType != "workflow.failed" || persisted.EventSequence != 3 {
		t.Fatalf("expected retry failure event sequence")
	}
	payloadJSON := mustJSON(t, persisted.EventPayload)
	if !strings.Contains(payloadJSON, "WORKFLOW_RETRY_FAILED") ||
		!strings.Contains(payloadJSON, seedWorkflowRetryStartFailedMessage) ||
		!strings.Contains(payloadJSON, "req-live-seed-retry-failed") {
		t.Fatalf("retry failure event lost stable public failure metadata")
	}
	assertLiveSeedGoTextDoesNotContainMarkers(t, payloadJSON, "retry failure event payload", liveSeedGoRetryForbiddenMarkers(fixture))
}

func liveSeedObjectStorageConfig(t *testing.T) sourcefiles.MinIOObjectWriterConfig {
	t.Helper()
	endpoint := strings.TrimSpace(os.Getenv("MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT"))
	bucket := strings.TrimSpace(os.Getenv("MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET"))
	accessKey := strings.TrimSpace(os.Getenv("MIROFISH_SEED_LIVE_OBJECT_STORAGE_ACCESS_KEY"))
	secretKey := strings.TrimSpace(os.Getenv("MIROFISH_SEED_LIVE_OBJECT_STORAGE_SECRET_KEY"))
	if endpoint == "" {
		t.Skip("set MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT to run live Seed Go upload/complete E2E")
	}
	if bucket == "" || accessKey == "" || secretKey == "" {
		t.Skip("set MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET/ACCESS_KEY/SECRET_KEY to run live Seed Go upload/complete E2E")
	}
	return sourcefiles.MinIOObjectWriterConfig{
		Endpoint:  endpoint,
		Bucket:    bucket,
		AccessKey: accessKey,
		SecretKey: secretKey,
		UseSSL:    liveSeedEnvBool("MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL"),
	}
}

func prepareLiveSeedGoDatabase(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	defer db.Close()
	migrationPath := filepath.Join("..", "..", "..", "..", "infra", "postgres", "migrations", "0001_core_saas.sql")
	if err := testschema.EnsureLiveSchema(context.Background(), db, migrationPath,
		"tenants", "projects", "source_files", "workflow_runs", "seed_tasks", "workflow_events",
	); err != nil {
		t.Fatalf("ensure live Seed schema: %v", err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_seed_go_live_app') THEN CREATE ROLE mirofish_seed_go_live_app LOGIN PASSWORD 'mirofish_seed_go_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_seed_go_live_app WITH LOGIN PASSWORD 'mirofish_seed_go_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_seed_go_live_app;"); err != nil {
		t.Fatalf("ensure app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveSeedTenantID); err != nil {
		t.Fatalf("cleanup tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users (user_id, email, display_name)
	VALUES ($1, $2, 'Seed Go Live')
	ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name`, liveSeedUserID, liveSeedUserEmail); err != nil {
		t.Fatalf("seed user: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES ($1, 'seed-go-live', 'Seed Go Live', 'personal')`, liveSeedTenantID); err != nil {
		t.Fatalf("seed tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES ($1, $2, 'Live Seed Go Project', $3)`, liveSeedTenantID, liveSeedProjectID, liveSeedUserID); err != nil {
		t.Fatalf("seed project: %v", err)
	}
}

type liveSeedGoAdmissionRows struct {
	SourceStatus   string
	WorkflowStatus string
	WorkflowType   string
	EventType      string
	EventPayload   map[string]any
}

type liveSeedGoRetryRows struct {
	SourceStatus       string
	WorkflowStatus     string
	TemporalWorkflowID string
	EventType          string
	EventSequence      int
	EventPayload       map[string]any
}

type liveSeedGoRetryFixture struct {
	AdminURL    string
	AppDB       *sql.DB
	Record      sourcefiles.Record
	ObjectInput sourcefiles.ObjectWriteInput
}

type liveSeedForbiddenMarker struct {
	Name  string
	Value string
}

func prepareLiveSeedGoRetryFixture(t *testing.T) liveSeedGoRetryFixture {
	t.Helper()
	adminURL := os.Getenv("MIROFISH_SEED_LIVE_DATABASE_URL")
	if strings.TrimSpace(adminURL) == "" {
		t.Skip("set MIROFISH_SEED_LIVE_DATABASE_URL to run live Seed Go retry Postgres/MinIO harness")
	}
	storageConfig := liveSeedObjectStorageConfig(t)
	requireLiveSeedDisposableDatabase(t, adminURL)
	objectKey := ""
	t.Cleanup(func() {
		cleanupLiveSeedGoFixture(t, adminURL, storageConfig, objectKey)
	})
	prepareLiveSeedGoDatabase(t, adminURL)
	appURL := liveSeedAppDatabaseURL(t, adminURL)
	appDB, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatalf("open app db: %v", err)
	}
	t.Cleanup(func() { _ = appDB.Close() })
	writer, err := sourcefiles.NewMinIOObjectWriter(storageConfig)
	if err != nil {
		t.Fatalf("new minio writer: %v", err)
	}
	verifier, err := sourcefiles.NewMinIOObjectVerifier(sourcefiles.MinIOObjectVerifierConfig(storageConfig))
	if err != nil {
		t.Fatalf("new minio verifier: %v", err)
	}
	sourceStore := sourcefiles.NewSQLStore(sourcefiles.SQLStoreConfig{
		Queryer:        sourcefiles.NewSQLDBQueryer(appDB),
		ObjectVerifier: verifier,
	})
	sourceBytes := []byte("第一章 重试\n风声穿过廊下。\n")
	sourceHash := sha256.Sum256(sourceBytes)
	record, err := sourceStore.CreateSourceFile(context.Background(), sourcefiles.CreateInput{
		TenantID:    liveSeedTenantID,
		ProjectID:   liveSeedProjectID,
		ActorUserID: liveSeedUserID,
		Filename:    "go-live-seed-retry.txt",
		MimeType:    "text/plain",
		SizeBytes:   int64(len(sourceBytes)),
		SHA256:      hex.EncodeToString(sourceHash[:]),
		Purpose:     "seed",
	})
	if err != nil {
		t.Fatalf("create source file: %v", err)
	}
	objectInput, err := sourceStore.GetUploadObject(context.Background(), sourcefiles.GetUploadObjectInput{
		TenantID: liveSeedTenantID,
		UploadID: record.UploadID,
	})
	if err != nil {
		t.Fatalf("get upload object metadata: %v", err)
	}
	objectKey = objectInput.ObjectKey
	if err := writer.WriteObject(context.Background(), objectInput, bytes.NewReader(sourceBytes)); err != nil {
		t.Fatalf("write source object: %v", err)
	}
	if _, err := sourceStore.CompleteUpload(context.Background(), sourcefiles.CompleteInput{
		TenantID: liveSeedTenantID,
		UploadID: record.UploadID,
	}); err != nil {
		t.Fatalf("complete upload: code=%s err=%v", sourcefiles.ErrorCode(err), err)
	}
	admissionStore := NewSQLSeedAdmissionStore(SQLSeedAdmissionStoreConfig{
		Execer: NewSQLDBWriterAdmissionExecer(appDB),
	})
	if err := admissionStore.AdmitSeedRun(context.Background(), SeedAdmissionInput{
		TenantID:           liveSeedTenantID,
		ProjectID:          liveSeedProjectID,
		RunID:              liveSeedRunID,
		TraceID:            "trace_" + liveSeedRunID,
		WorkflowType:       SeedWorkflowType,
		TemporalWorkflowID: "seed_run_" + liveSeedRunID,
		ActorUserID:        liveSeedUserID,
		RequestID:          "req-live-seed-go",
		UploadID:           record.UploadID,
		SourceFileID:       record.FileID,
		Status:             "queued",
	}); err != nil {
		t.Fatalf("admit seed run: %v", err)
	}
	return liveSeedGoRetryFixture{
		AdminURL:    adminURL,
		AppDB:       appDB,
		Record:      record,
		ObjectInput: objectInput,
	}
}

func liveSeedGoRetryForbiddenMarkers(fixture liveSeedGoRetryFixture) []liveSeedForbiddenMarker {
	return []liveSeedForbiddenMarker{
		{Name: "object key", Value: fixture.ObjectInput.ObjectKey},
		{Name: "source hash", Value: fixture.ObjectInput.SHA256},
		{Name: "object key field", Value: "object_key"},
		{Name: "source object key field", Value: "source_object_key"},
		{Name: "source hash field", Value: "source_sha256"},
		{Name: "source title", Value: "第一章"},
		{Name: "source body", Value: "风声穿过廊下"},
		{Name: "provider response marker", Value: "provider response"},
		{Name: "raw marker", Value: "raw"},
		{Name: "content marker", Value: "content"},
		{Name: "prompt marker", Value: "prompt"},
		{Name: "api key marker", Value: "api_key"},
		{Name: "encrypted credential marker", Value: "encrypted credential"},
		{Name: "credential ref marker", Value: "credential_ref"},
		{Name: "draft marker", Value: "draft"},
		{Name: "manuscript marker", Value: "manuscript"},
	}
}

func assertLiveSeedGoTextDoesNotContainMarkers(t *testing.T, text string, surface string, markers []liveSeedForbiddenMarker) {
	t.Helper()
	for _, marker := range markers {
		if strings.TrimSpace(marker.Value) == "" {
			continue
		}
		if strings.Contains(text, marker.Value) {
			t.Fatalf("%s leaked forbidden %s", surface, marker.Name)
		}
	}
}

func cleanupLiveSeedGoFixture(t *testing.T, adminURL string, storageConfig sourcefiles.MinIOObjectWriterConfig, objectKey string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Errorf("open admin db for live Seed cleanup: %v", err)
	} else {
		if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveSeedTenantID); err != nil {
			t.Errorf("cleanup live Seed tenant: %v", err)
		}
		if _, err := db.Exec("DELETE FROM users WHERE user_id = $1 AND email = $2", liveSeedUserID, liveSeedUserEmail); err != nil {
			t.Errorf("cleanup live Seed user: %v", err)
		}
		_ = db.Close()
	}
	if objectKey == "" {
		return
	}
	client, err := minio.New(storageConfig.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(storageConfig.AccessKey, storageConfig.SecretKey, ""),
		Secure: storageConfig.UseSSL,
	})
	if err != nil {
		t.Errorf("create MinIO client for live Seed cleanup: %v", err)
		return
	}
	if err := client.RemoveObject(context.Background(), storageConfig.Bucket, objectKey, minio.RemoveObjectOptions{}); err != nil {
		t.Errorf("cleanup live Seed object: %v", err)
	}
}

func requireLiveSeedDisposableDatabase(t *testing.T, adminURL string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open live Seed database guard: %v", err)
	}
	defer db.Close()
	if err := testschema.RequireDisposableLiveDatabase(context.Background(), db); err != nil {
		t.Fatal(err)
	}
}

func readLiveSeedGoAdmissionRows(t *testing.T, adminURL string, uploadID string) liveSeedGoAdmissionRows {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	defer db.Close()
	var rows liveSeedGoAdmissionRows
	var payloadBytes []byte
	if err := db.QueryRow(`SELECT parse_status FROM source_files WHERE tenant_id = $1 AND upload_id = $2`, liveSeedTenantID, uploadID).Scan(&rows.SourceStatus); err != nil {
		t.Fatalf("read source status: %v", err)
	}
	if err := db.QueryRow(`SELECT status, workflow_type FROM workflow_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3`, liveSeedTenantID, liveSeedProjectID, liveSeedRunID).Scan(&rows.WorkflowStatus, &rows.WorkflowType); err != nil {
		t.Fatalf("read workflow run: %v", err)
	}
	if err := db.QueryRow(`SELECT event_type, payload_jsonb::text FROM workflow_events WHERE tenant_id = $1 AND run_id = $2 AND sequence = 1`, liveSeedTenantID, liveSeedRunID).Scan(&rows.EventType, &payloadBytes); err != nil {
		t.Fatalf("read workflow event: %v", err)
	}
	if err := json.Unmarshal(payloadBytes, &rows.EventPayload); err != nil {
		t.Fatalf("decode workflow event payload: %v", err)
	}
	return rows
}

func markLiveSeedGoRunFailedForRetry(t *testing.T, adminURL string, uploadID string, sourceFileID string) {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	defer db.Close()
	if _, err := db.Exec(`UPDATE workflow_runs
SET status = 'failed',
    message = 'failed before retry',
    error_code = 'WORKFLOW_FAILED',
    error_message = 'failed before retry',
    updated_at = now()
WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3 AND workflow_type = $4`, liveSeedTenantID, liveSeedProjectID, liveSeedRunID, SeedWorkflowType); err != nil {
		t.Fatalf("mark workflow failed for retry: %v", err)
	}
	if _, err := db.Exec(`UPDATE source_files
SET parse_status = 'uploaded',
    updated_at = now()
WHERE tenant_id = $1 AND project_id = $2 AND upload_id = $3 AND file_id = $4`, liveSeedTenantID, liveSeedProjectID, uploadID, sourceFileID); err != nil {
		t.Fatalf("release source for retry: %v", err)
	}
}

func readLiveSeedGoRetryRows(t *testing.T, adminURL string, uploadID string) liveSeedGoRetryRows {
	t.Helper()
	db, err := sql.Open("pgx", adminURL)
	if err != nil {
		t.Fatalf("open admin db: %v", err)
	}
	defer db.Close()
	var rows liveSeedGoRetryRows
	var payloadBytes []byte
	if err := db.QueryRow(`SELECT parse_status FROM source_files WHERE tenant_id = $1 AND upload_id = $2`, liveSeedTenantID, uploadID).Scan(&rows.SourceStatus); err != nil {
		t.Fatalf("read retry source status: %v", err)
	}
	if err := db.QueryRow(`SELECT status, temporal_workflow_id FROM workflow_runs WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3`, liveSeedTenantID, liveSeedProjectID, liveSeedRunID).Scan(&rows.WorkflowStatus, &rows.TemporalWorkflowID); err != nil {
		t.Fatalf("read retry workflow run: %v", err)
	}
	if err := db.QueryRow(`SELECT event_type, sequence, payload_jsonb::text
FROM workflow_events
WHERE tenant_id = $1 AND run_id = $2
ORDER BY sequence DESC
LIMIT 1`, liveSeedTenantID, liveSeedRunID).Scan(&rows.EventType, &rows.EventSequence, &payloadBytes); err != nil {
		t.Fatalf("read retry workflow event: %v", err)
	}
	if err := json.Unmarshal(payloadBytes, &rows.EventPayload); err != nil {
		t.Fatalf("decode retry workflow event payload: %v", err)
	}
	return rows
}

func liveSeedAppDatabaseURL(t *testing.T, adminURL string) string {
	t.Helper()
	parsed, err := url.Parse(adminURL)
	if err != nil {
		t.Fatalf("parse admin database URL: %v", err)
	}
	parsed.User = url.UserPassword(liveSeedAppRole, liveSeedAppPassword)
	return parsed.String()
}

func liveSeedEnvBool(name string) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(name))) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func mustJSON(t *testing.T, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal json: %v", err)
	}
	return string(encoded)
}
