package workflows

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"mirofish-novel/apps/api/internal/sourcefiles"

	_ "github.com/jackc/pgx/v5/stdlib"
)

const liveSeedTenantID = "81111111-1111-1111-1111-111111111111"
const liveSeedUserID = "82222222-2222-2222-2222-222222222222"
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
	prepareLiveSeedGoDatabase(t, adminURL)
	appURL := liveSeedAppDatabaseURL(t, adminURL)
	appDB, err := sql.Open("pgx", appURL)
	if err != nil {
		t.Fatalf("open app db: %v", err)
	}
	defer appDB.Close()
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
		t.Fatalf("validated source metadata mismatch: %#v vs %#v", validated, objectInput)
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
		t.Fatalf("expected admission to advance source to parsing, got %#v", persisted)
	}
	if persisted.WorkflowStatus != "queued" || persisted.WorkflowType != SeedWorkflowType {
		t.Fatalf("unexpected workflow admission row: %#v", persisted)
	}
	if persisted.EventType != "workflow.queued" {
		t.Fatalf("expected queued workflow event, got %#v", persisted)
	}
	payloadJSON := mustJSON(t, persisted.EventPayload)
	if !strings.Contains(payloadJSON, "source_file_id") || !strings.Contains(payloadJSON, record.FileID) {
		t.Fatalf("expected queued event to include source file metadata, got %s", payloadJSON)
	}
	for _, forbidden := range []string{
		objectInput.ObjectKey,
		"object_key",
		"source_object_key",
		"第一章",
		"雨声压住脚步",
		"api_key",
		"credential_ref",
		"draft",
		"manuscript",
	} {
		if strings.Contains(payloadJSON, forbidden) {
			t.Fatalf("workflow admission payload leaked forbidden text %q: %s", forbidden, payloadJSON)
		}
	}
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
	migrationSQL, err := os.ReadFile(migrationPath)
	if err != nil {
		t.Fatalf("read migration: %v", err)
	}
	if _, err := db.Exec(string(migrationSQL)); err != nil {
		t.Fatalf("apply migration: %v", err)
	}
	if _, err := db.Exec("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_seed_go_live_app') THEN CREATE ROLE mirofish_seed_go_live_app LOGIN PASSWORD 'mirofish_seed_go_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_seed_go_live_app WITH LOGIN PASSWORD 'mirofish_seed_go_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_seed_go_live_app;"); err != nil {
		t.Fatalf("ensure app role: %v", err)
	}
	if _, err := db.Exec("DELETE FROM tenants WHERE tenant_id = $1", liveSeedTenantID); err != nil {
		t.Fatalf("cleanup tenant: %v", err)
	}
	if _, err := db.Exec(`INSERT INTO users (user_id, email, display_name)
VALUES ($1, 'seed-go-live@example.test', 'Seed Go Live')
ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name`, liveSeedUserID); err != nil {
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
