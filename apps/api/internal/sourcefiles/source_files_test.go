package sourcefiles

import (
	"context"
	"database/sql"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestDisabledStoreFailsClosed(t *testing.T) {
	store := NewDisabledStore()

	_, err := store.CreateSourceFile(context.Background(), CreateInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		Filename:  "novel.md",
		MimeType:  "text/markdown",
		SizeBytes: 1,
		SHA256:    "hash",
		Purpose:   "seed",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected disabled backend error, got %s (%v)", code, err)
	}
}

func TestSQLStoreCreatesSourceFileWithoutReturningObjectCredentials(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"upload-1",
			"project-1",
			"novel.md",
			"text/markdown",
			int64(2048),
			"hash",
			"seed",
			"pending",
			"2026-07-04T10:00:00Z",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	record, err := store.CreateSourceFile(context.Background(), CreateInput{
		TenantID:    "tenant-1",
		ProjectID:   "project-1",
		ActorUserID: "user-1",
		Filename:    "novel.md",
		MimeType:    "text/markdown",
		SizeBytes:   2048,
		SHA256:      "hash",
		Purpose:     "seed",
	})

	if err != nil {
		t.Fatalf("create source file: %v", err)
	}
	if record.FileID != "file-1" || record.UploadID != "upload-1" || record.ProjectID != "project-1" || record.ParseStatus != "pending" {
		t.Fatalf("unexpected record: %#v", record)
	}
	if !strings.Contains(queryer.query, "INSERT INTO source_files") {
		t.Fatalf("expected source_files insert, got %s", queryer.query)
	}
	if strings.Contains(queryer.query, "presigned") || strings.Contains(queryer.query, "api_key") {
		t.Fatalf("source file query mentions credential-like upload material: %s", queryer.query)
	}
}

func TestSQLStoreRejectsUnsupportedSourceMimeBeforeInsert(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"upload-1",
			"project-1",
			"notes.json",
			"application/json",
			int64(99),
			"hash",
			"seed",
			"pending",
			"2026-07-04T10:00:00Z",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	_, err := store.CreateSourceFile(context.Background(), CreateInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		Filename:  "notes.json",
		MimeType:  "application/json",
		SizeBytes: 99,
		SHA256:    "hash",
		Purpose:   "seed",
	})

	if code := ErrorCode(err); code != "VALIDATION_FAILED" {
		t.Fatalf("expected unsupported MIME validation failure, got %s (%v)", code, err)
	}
	if queryer.query != "" {
		t.Fatalf("unsupported source MIME must be rejected before DB insert, got query %s", queryer.query)
	}
}

func TestSQLStoreListsTenantProjectSourceFiles(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		rows: &fakeSourceFileRows{values: [][]any{{
			"file-1",
			"upload-1",
			"project-1",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"seed",
			"pending",
			"2026-07-04T10:00:00Z",
		}}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	items, err := store.ListSourceFiles(context.Background(), ListInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
	})

	if err != nil {
		t.Fatalf("list source files: %v", err)
	}
	if len(items) != 1 || items[0].UploadID != "upload-1" || items[0].Filename != "book.txt" {
		t.Fatalf("unexpected items: %#v", items)
	}
	if !strings.Contains(queryer.query, "WHERE tenant_id::text = $1") || !strings.Contains(queryer.query, "project_id::text = $2") {
		t.Fatalf("list query must be tenant/project scoped: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "project-1", 100}) {
		t.Fatalf("unexpected query args: %#v", queryer.args)
	}
}

func TestSQLStoreCompletesUploadWithTenantScopeAndSanitizedRecord(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		rowsQueue: []fakeSourceFileRow{
			{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
			{values: []any{
				"file-1",
				"upload-1",
				"project-1",
				"book.txt",
				"text/plain",
				int64(99),
				"hash",
				"seed",
				"uploaded",
				"2026-07-04T10:00:00Z",
			}},
		},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: &recordingObjectVerifier{}})

	record, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	if record.UploadID != "upload-1" || record.ProjectID != "project-1" || record.ParseStatus != "uploaded" {
		t.Fatalf("unexpected completed record: %#v", record)
	}
	if len(queryer.queries) != 2 || !strings.Contains(queryer.queries[1], "UPDATE source_files") || !strings.Contains(queryer.queries[1], "parse_status = 'uploaded'") {
		t.Fatalf("complete query must verify then update upload state: %#v", queryer.queries)
	}
	if strings.Contains(queryer.queries[1], "object_key") || strings.Contains(queryer.queries[1], "presigned") || strings.Contains(queryer.queries[1], "api_key") {
		t.Fatalf("complete update returned credential-like upload material: %s", queryer.queries[1])
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "upload-1"}) {
		t.Fatalf("unexpected complete args: %#v", queryer.args)
	}
}

func TestSQLStoreRejectsCompleteUploadWithoutObjectVerifierBeforeUpdate(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"upload-1",
			"project-1",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"seed",
			"uploaded",
			"2026-07-04T10:00:00Z",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	_, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
	for _, query := range queryer.queries {
		if strings.Contains(query, "UPDATE source_files") {
			t.Fatalf("complete without verifier must not mark upload completed: %#v", queryer.queries)
		}
	}
}

func TestSQLStoreVerifiesObjectBeforeCompletingUpload(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		rowsQueue: []fakeSourceFileRow{
			{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
			{values: []any{
				"file-1",
				"upload-1",
				"project-1",
				"book.txt",
				"text/plain",
				int64(99),
				"hash",
				"seed",
				"uploaded",
				"2026-07-04T10:00:00Z",
			}},
		},
	}
	verifier := &recordingObjectVerifier{}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: verifier})

	record, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if err != nil {
		t.Fatalf("complete upload: %v", err)
	}
	if record.ParseStatus != "uploaded" {
		t.Fatalf("unexpected completed record: %#v", record)
	}
	if verifier.input.ObjectKey != "projects/project-1/source-files/upload-1/book.txt" ||
		verifier.input.TenantID != "tenant-1" ||
		verifier.input.ProjectID != "project-1" ||
		verifier.input.UploadID != "upload-1" ||
		verifier.input.SizeBytes != 99 ||
		verifier.input.SHA256 != "hash" {
		t.Fatalf("object verifier did not receive expected metadata: %#v", verifier.input)
	}
	if len(queryer.queries) != 2 || !strings.Contains(queryer.queries[0], "object_key") || !strings.Contains(queryer.queries[1], "UPDATE source_files") {
		t.Fatalf("expected metadata lookup then update, got %#v", queryer.queries)
	}
}

func TestSQLStoreRejectsCompleteUploadForNonCompletableStatusBeforeVerification(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		rowsQueue: []fakeSourceFileRow{
			{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "parsed"}},
			{values: []any{
				"file-1",
				"upload-1",
				"project-1",
				"book.txt",
				"text/plain",
				int64(99),
				"hash",
				"seed",
				"uploaded",
				"2026-07-04T10:00:00Z",
			}},
		},
	}
	verifier := &recordingObjectVerifier{}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: verifier})

	_, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_UPLOAD_NOT_COMPLETABLE" {
		t.Fatalf("expected SOURCE_FILE_UPLOAD_NOT_COMPLETABLE, got %s (%v)", code, err)
	}
	if verifier.calls != 0 {
		t.Fatalf("non-completable upload status must be rejected before object verification, got %d calls", verifier.calls)
	}
	for _, query := range queryer.queries {
		if strings.Contains(query, "UPDATE source_files") {
			t.Fatalf("non-completable upload status must not update source_files: %#v", queryer.queries)
		}
	}
}

func TestSQLStoreGetsUploadObjectMetadataWithTenantScope(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"project-1",
			"projects/project-1/source-files/upload-1/book.txt",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"pending",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	metadata, err := store.GetUploadObject(context.Background(), GetUploadObjectInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if err != nil {
		t.Fatalf("get upload object metadata: %v", err)
	}
	if metadata.TenantID != "tenant-1" ||
		metadata.UploadID != "upload-1" ||
		metadata.FileID != "file-1" ||
		metadata.ProjectID != "project-1" ||
		metadata.ObjectKey != "projects/project-1/source-files/upload-1/book.txt" ||
		metadata.MimeType != "text/plain" ||
		metadata.SizeBytes != 99 ||
		metadata.SHA256 != "hash" ||
		metadata.ParseStatus != "pending" {
		t.Fatalf("unexpected object metadata: %#v", metadata)
	}
	if !strings.Contains(queryer.query, "WHERE tenant_id::text = $1") ||
		!strings.Contains(queryer.query, "upload_id::text = $2") {
		t.Fatalf("metadata lookup must be tenant/upload scoped: %s", queryer.query)
	}
	if !strings.Contains(queryer.query, "object_key") || !strings.Contains(queryer.query, "mime_type") || !strings.Contains(queryer.query, "parse_status") {
		t.Fatalf("metadata lookup must read internal object metadata: %s", queryer.query)
	}
}

func TestSQLStoreRejectsObjectWriteMetadataForNonPendingUpload(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"project-1",
			"projects/project-1/source-files/upload-1/book.txt",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"uploaded",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	_, err := store.GetUploadObject(context.Background(), GetUploadObjectInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_UPLOAD_NOT_WRITABLE" {
		t.Fatalf("expected SOURCE_FILE_UPLOAD_NOT_WRITABLE, got %s (%v)", code, err)
	}
}

func TestSQLStoreDoesNotCompleteUploadWhenObjectVerificationFails(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		rowsQueue: []fakeSourceFileRow{
			{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
			{values: []any{
				"file-1",
				"upload-1",
				"project-1",
				"book.txt",
				"text/plain",
				int64(99),
				"hash",
				"seed",
				"uploaded",
				"2026-07-04T10:00:00Z",
			}},
		},
	}
	verifier := &recordingObjectVerifier{err: NewAppError("SOURCE_FILE_OBJECT_NOT_FOUND", "source file object was not found")}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: verifier})

	_, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_OBJECT_NOT_FOUND" {
		t.Fatalf("expected SOURCE_FILE_OBJECT_NOT_FOUND, got %s (%v)", code, err)
	}
	if len(queryer.queries) != 1 || strings.Contains(queryer.queries[0], "UPDATE source_files") {
		t.Fatalf("object verification failure must not mark upload completed: %#v", queryer.queries)
	}
}

func TestSQLStoreReturnsNotFoundForMissingUploadComplete(t *testing.T) {
	queryer := &recordingSourceFileQueryer{row: fakeSourceFileRow{err: sql.ErrNoRows}}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: &recordingObjectVerifier{}})

	_, err := store.CompleteUpload(context.Background(), CompleteInput{
		TenantID: "tenant-1",
		UploadID: "upload-missing",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND, got %s (%v)", code, err)
	}
}

func TestSQLStoreValidatesUploadBelongsToTenantProject(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"upload-1",
			"project-1",
			"projects/project-1/source-files/upload-1/book.txt",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"uploaded",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	metadata, err := store.ValidateSourceFile(context.Background(), ValidateInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		UploadID:  "upload-1",
	})

	if err != nil {
		t.Fatalf("validate source file: %v", err)
	}
	if metadata.FileID != "file-1" ||
		metadata.UploadID != "upload-1" ||
		metadata.ProjectID != "project-1" ||
		metadata.ObjectKey != "projects/project-1/source-files/upload-1/book.txt" ||
		metadata.Filename != "book.txt" ||
		metadata.MimeType != "text/plain" ||
		metadata.SizeBytes != 99 ||
		metadata.SHA256 != "hash" ||
		metadata.ParseStatus != "uploaded" {
		t.Fatalf("validation did not return internal source metadata: %#v", metadata)
	}
	if !strings.Contains(queryer.query, "file_id::text") ||
		!strings.Contains(queryer.query, "object_key") ||
		!strings.Contains(queryer.query, "FROM source_files") ||
		!strings.Contains(queryer.query, "upload_id::text = $3") {
		t.Fatalf("validation query must target tenant/project/upload: %s", queryer.query)
	}
	if !reflect.DeepEqual(queryer.args, []any{"tenant-1", "project-1", "upload-1"}) {
		t.Fatalf("unexpected validate args: %#v", queryer.args)
	}
}

func TestSQLStoreRejectsSeedValidationForPendingUpload(t *testing.T) {
	queryer := &recordingSourceFileQueryer{
		row: fakeSourceFileRow{values: []any{
			"file-1",
			"upload-1",
			"project-1",
			"projects/project-1/source-files/upload-1/book.txt",
			"book.txt",
			"text/plain",
			int64(99),
			"hash",
			"pending",
		}},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	_, err := store.ValidateSourceFile(context.Background(), ValidateInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		UploadID:  "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_NOT_UPLOADED" {
		t.Fatalf("expected SOURCE_FILE_NOT_UPLOADED, got %s (%v)", code, err)
	}
}

func TestSQLStoreReturnsNotFoundForMissingUpload(t *testing.T) {
	queryer := &recordingSourceFileQueryer{row: fakeSourceFileRow{err: sql.ErrNoRows}}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	_, err := store.ValidateSourceFile(context.Background(), ValidateInput{
		TenantID:  "tenant-1",
		ProjectID: "project-1",
		UploadID:  "upload-missing",
	})

	if code := ErrorCode(err); code != "NOT_FOUND" {
		t.Fatalf("expected NOT_FOUND, got %s (%v)", code, err)
	}
}

func TestSQLStoreSanitizesUnexpectedErrorMessages(t *testing.T) {
	sensitiveErr := errors.New("driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-1/source-files/upload-1/book.txt")
	validRecordValues := []any{
		"file-1",
		"upload-1",
		"project-1",
		"book.txt",
		"text/plain",
		int64(99),
		"hash",
		"seed",
		"uploaded",
		"2026-07-04T10:00:00Z",
	}
	tests := []struct {
		name     string
		run      func() error
		wantCode string
	}{
		{
			name: "create scan",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{Queryer: &recordingSourceFileQueryer{row: fakeSourceFileRow{err: sensitiveErr}}})
				_, err := store.CreateSourceFile(context.Background(), CreateInput{
					TenantID:  "tenant-1",
					ProjectID: "project-1",
					Filename:  "book.txt",
					MimeType:  "text/plain",
					SizeBytes: 99,
					SHA256:    "hash",
					Purpose:   "seed",
				})
				return err
			},
			wantCode: "SOURCE_FILE_CREATE_FAILED",
		},
		{
			name: "complete scan",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{
					Queryer: &recordingSourceFileQueryer{rowsQueue: []fakeSourceFileRow{
						{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
						{err: sensitiveErr},
					}},
					ObjectVerifier: &recordingObjectVerifier{},
				})
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_COMPLETE_FAILED",
		},
		{
			name: "object lookup scan",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{
					Queryer:        &recordingSourceFileQueryer{row: fakeSourceFileRow{err: sensitiveErr}},
					ObjectVerifier: &recordingObjectVerifier{},
				})
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name: "list query",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{Queryer: &recordingSourceFileQueryer{err: sensitiveErr}})
				_, err := store.ListSourceFiles(context.Background(), ListInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name: "list rows err",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{Queryer: &recordingSourceFileQueryer{
					rows: &fakeSourceFileRows{values: [][]any{validRecordValues}, err: sensitiveErr},
				}})
				_, err := store.ListSourceFiles(context.Background(), ListInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name: "validate scan",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{Queryer: &recordingSourceFileQueryer{row: fakeSourceFileRow{err: sensitiveErr}}})
				_, err := store.ValidateSourceFile(context.Background(), ValidateInput{
					TenantID:  "tenant-1",
					ProjectID: "project-1",
					UploadID:  "upload-1",
				})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name: "object verification",
			run: func() error {
				store := NewSQLStore(SQLStoreConfig{
					Queryer: &recordingSourceFileQueryer{rowsQueue: []fakeSourceFileRow{
						{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
					}},
					ObjectVerifier: &recordingObjectVerifier{err: sensitiveErr},
				})
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_STORAGE_VERIFY_FAILED",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := test.run()
			if code := ErrorCode(err); code != test.wantCode {
				t.Fatalf("expected %s, got %s (%v)", test.wantCode, code, err)
			}
			message := err.Error()
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-1/source-files"} {
				if strings.Contains(message, forbidden) {
					t.Fatalf("source file error leaked forbidden text %q: %s", forbidden, message)
				}
			}
		})
	}
}

func TestSQLStoreUsesTenantContextQueryerForReadAndWritePaths(t *testing.T) {
	validRecordValues := []any{
		"file-1",
		"upload-1",
		"project-1",
		"book.txt",
		"text/plain",
		int64(99),
		"hash",
		"seed",
		"uploaded",
		"2026-07-04T10:00:00Z",
	}
	for _, test := range []struct {
		name           string
		tenantID       string
		rowsQueue      []fakeSourceFileRow
		rows           *fakeSourceFileRows
		objectVerifier ObjectVerifier
		run            func(*SQLStore) error
		wantCalls      int
	}{
		{
			name:      "create source file",
			tenantID:  "tenant-create",
			rowsQueue: []fakeSourceFileRow{{values: validRecordValues}},
			run: func(store *SQLStore) error {
				_, err := store.CreateSourceFile(context.Background(), CreateInput{
					TenantID:  "tenant-create",
					ProjectID: "project-1",
					Filename:  "book.txt",
					MimeType:  "text/plain",
					SizeBytes: 99,
					SHA256:    "hash",
					Purpose:   "seed",
				})
				return err
			},
			wantCalls: 1,
		},
		{
			name:     "complete upload with object verifier",
			tenantID: "tenant-verify",
			rowsQueue: []fakeSourceFileRow{
				{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
				{values: validRecordValues},
			},
			objectVerifier: &recordingObjectVerifier{},
			run: func(store *SQLStore) error {
				_, err := store.CompleteUpload(context.Background(), CompleteInput{
					TenantID: "tenant-verify",
					UploadID: "upload-1",
				})
				return err
			},
			wantCalls: 2,
		},
		{
			name:     "list source files",
			tenantID: "tenant-list",
			rows:     &fakeSourceFileRows{values: [][]any{validRecordValues}},
			run: func(store *SQLStore) error {
				_, err := store.ListSourceFiles(context.Background(), ListInput{
					TenantID:  "tenant-list",
					ProjectID: "project-1",
				})
				return err
			},
			wantCalls: 1,
		},
		{
			name:      "validate source file",
			tenantID:  "tenant-validate",
			rowsQueue: []fakeSourceFileRow{{values: []any{"file-1", "upload-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", "book.txt", "text/plain", int64(99), "hash", "uploaded"}}},
			run: func(store *SQLStore) error {
				_, err := store.ValidateSourceFile(context.Background(), ValidateInput{
					TenantID:  "tenant-validate",
					ProjectID: "project-1",
					UploadID:  "upload-1",
				})
				return err
			},
			wantCalls: 1,
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			queryer := &recordingTenantSourceFileQueryer{
				recordingSourceFileQueryer: recordingSourceFileQueryer{
					rowsQueue: test.rowsQueue,
					rows:      test.rows,
				},
			}
			store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: test.objectVerifier})

			if err := test.run(store); err != nil {
				t.Fatalf("run source file store path: %v", err)
			}
			if queryer.tenantContextCalls != test.wantCalls {
				t.Fatalf("expected %d tenant context calls, got %d", test.wantCalls, queryer.tenantContextCalls)
			}
			for _, tenantID := range queryer.tenantIDs {
				if tenantID != test.tenantID {
					t.Fatalf("expected tenant %q, got tenant context calls %#v", test.tenantID, queryer.tenantIDs)
				}
			}
		})
	}
}

func TestSQLStoreReturnsRowsCloseErrorsAsStableQueryFailures(t *testing.T) {
	sensitiveErr := errors.New("commit failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden object_key=projects/project-1/source-files/upload-1/book.txt")
	validRecordValues := []any{
		"file-1",
		"upload-1",
		"project-1",
		"book.txt",
		"text/plain",
		int64(99),
		"hash",
		"seed",
		"uploaded",
		"2026-07-04T10:00:00Z",
	}
	for _, test := range []struct {
		name           string
		rowsQueue      []fakeSourceFileRow
		rows           *fakeSourceFileRows
		objectVerifier ObjectVerifier
		run            func(*SQLStore) error
		wantCode       string
	}{
		{
			name:      "create source file",
			rowsQueue: []fakeSourceFileRow{{values: validRecordValues, closeErr: sensitiveErr}},
			run: func(store *SQLStore) error {
				_, err := store.CreateSourceFile(context.Background(), CreateInput{
					TenantID:  "tenant-1",
					ProjectID: "project-1",
					Filename:  "book.txt",
					MimeType:  "text/plain",
					SizeBytes: 99,
					SHA256:    "hash",
					Purpose:   "seed",
				})
				return err
			},
			wantCode: "SOURCE_FILE_CREATE_FAILED",
		},
		{
			name: "complete upload",
			rowsQueue: []fakeSourceFileRow{
				{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
				{values: validRecordValues, closeErr: sensitiveErr},
			},
			objectVerifier: &recordingObjectVerifier{},
			run: func(store *SQLStore) error {
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_COMPLETE_FAILED",
		},
		{
			name:           "object lookup",
			rowsQueue:      []fakeSourceFileRow{{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}, closeErr: sensitiveErr}},
			objectVerifier: &recordingObjectVerifier{},
			run: func(store *SQLStore) error {
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name: "list source files",
			rows: &fakeSourceFileRows{values: [][]any{validRecordValues}, closeErr: sensitiveErr},
			run: func(store *SQLStore) error {
				_, err := store.ListSourceFiles(context.Background(), ListInput{TenantID: "tenant-1", ProjectID: "project-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
		{
			name:      "validate source file",
			rowsQueue: []fakeSourceFileRow{{values: []any{"file-1", "upload-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", "book.txt", "text/plain", int64(99), "hash", "uploaded"}, closeErr: sensitiveErr}},
			run: func(store *SQLStore) error {
				_, err := store.ValidateSourceFile(context.Background(), ValidateInput{TenantID: "tenant-1", ProjectID: "project-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_QUERY_FAILED",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			queryer := &recordingTenantSourceFileQueryer{
				recordingSourceFileQueryer: recordingSourceFileQueryer{
					rowsQueue: test.rowsQueue,
					rows:      test.rows,
				},
			}
			store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: test.objectVerifier})

			err := test.run(store)

			if code := ErrorCode(err); code != test.wantCode {
				t.Fatalf("expected %s, got %s (%v)", test.wantCode, code, err)
			}
			for _, forbidden := range []string{"prompt", "api_key", "sk-hidden", "credential_ref", "object_key", "projects/project-1/source-files"} {
				if strings.Contains(err.Error(), forbidden) {
					t.Fatalf("source file close error leaked forbidden text %q: %s", forbidden, err.Error())
				}
			}
		})
	}
}

func TestSQLStoreDoesNotTreatTenantRowsErrAfterSuccessfulCloseAsQueryFailure(t *testing.T) {
	queryer := &recordingTenantSourceFileQueryer{
		recordingSourceFileQueryer: recordingSourceFileQueryer{
			rowsQueue: []fakeSourceFileRow{{
				values:        []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", "book.txt", "text/plain", int64(99), "hash", "pending"},
				errAfterClose: context.Canceled,
			}},
		},
	}
	store := NewSQLStore(SQLStoreConfig{Queryer: queryer})

	metadata, err := store.GetUploadObject(context.Background(), GetUploadObjectInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if err != nil {
		t.Fatalf("expected successful tenant-scoped row scan, got %s (%v)", ErrorCode(err), err)
	}
	if metadata.ObjectKey != "projects/project-1/source-files/upload-1/book.txt" {
		t.Fatalf("unexpected upload metadata: %#v", metadata)
	}
	if len(queryer.tenantRows) != 1 || !queryer.tenantRows[0].closed {
		t.Fatalf("expected tenant rows to close successfully, got %#v", queryer.tenantRows)
	}
}

func TestSQLStoreAbortsTenantContextRowsOnScanFailure(t *testing.T) {
	sensitiveErr := errors.New("scan failed prompt=hidden api_key=sk-hidden credential_ref=secret")
	for _, test := range []struct {
		name           string
		rowsQueue      []fakeSourceFileRow
		objectVerifier ObjectVerifier
		run            func(*SQLStore) error
		wantCode       string
	}{
		{
			name:      "create source file",
			rowsQueue: []fakeSourceFileRow{{values: []any{"file-1"}, scanErr: sensitiveErr}},
			run: func(store *SQLStore) error {
				_, err := store.CreateSourceFile(context.Background(), CreateInput{
					TenantID:  "tenant-1",
					ProjectID: "project-1",
					Filename:  "book.txt",
					MimeType:  "text/plain",
					SizeBytes: 99,
					SHA256:    "hash",
					Purpose:   "seed",
				})
				return err
			},
			wantCode: "SOURCE_FILE_CREATE_FAILED",
		},
		{
			name: "complete upload",
			rowsQueue: []fakeSourceFileRow{
				{values: []any{"file-1", "project-1", "projects/project-1/source-files/upload-1/book.txt", int64(99), "hash", "pending"}},
				{values: []any{"file-1"}, scanErr: sensitiveErr},
			},
			objectVerifier: &recordingObjectVerifier{},
			run: func(store *SQLStore) error {
				_, err := store.CompleteUpload(context.Background(), CompleteInput{TenantID: "tenant-1", UploadID: "upload-1"})
				return err
			},
			wantCode: "SOURCE_FILE_COMPLETE_FAILED",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			queryer := &recordingTenantSourceFileQueryer{
				recordingSourceFileQueryer: recordingSourceFileQueryer{rowsQueue: test.rowsQueue},
			}
			store := NewSQLStore(SQLStoreConfig{Queryer: queryer, ObjectVerifier: test.objectVerifier})

			err := test.run(store)

			if code := ErrorCode(err); code != test.wantCode {
				t.Fatalf("expected %s, got %s (%v)", test.wantCode, code, err)
			}
			if len(queryer.tenantRows) == 0 || !queryer.tenantRows[len(queryer.tenantRows)-1].aborted {
				t.Fatalf("expected scan failure to abort tenant rows, got %#v", queryer.tenantRows)
			}
		})
	}
}

type recordingSourceFileQueryer struct {
	query     string
	queries   []string
	args      []any
	argsList  [][]any
	row       fakeSourceFileRow
	rowsQueue []fakeSourceFileRow
	rows      *fakeSourceFileRows
	err       error
}

func (q *recordingSourceFileQueryer) QueryRowContext(_ context.Context, query string, args ...any) SQLRow {
	q.query = query
	q.queries = append(q.queries, query)
	q.args = append([]any(nil), args...)
	q.argsList = append(q.argsList, append([]any(nil), args...))
	if q.err != nil {
		return fakeSourceFileRow{err: q.err}
	}
	if len(q.rowsQueue) > 0 {
		row := q.rowsQueue[0]
		q.rowsQueue = q.rowsQueue[1:]
		return row
	}
	return q.row
}

func (q *recordingSourceFileQueryer) QueryContext(_ context.Context, query string, args ...any) (SQLRows, error) {
	q.query = query
	q.args = append([]any(nil), args...)
	if q.err != nil {
		return nil, q.err
	}
	if q.rows == nil {
		return nil, errors.New("no rows configured")
	}
	return q.rows, nil
}

type recordingTenantSourceFileQueryer struct {
	recordingSourceFileQueryer
	tenantContextCalls int
	tenantIDs          []string
	tenantRows         []*fakeSourceFileRows
}

func (q *recordingTenantSourceFileQueryer) QueryTenantContext(ctx context.Context, tenantID string, query string, args ...any) (SQLRows, error) {
	q.tenantContextCalls++
	q.tenantIDs = append(q.tenantIDs, tenantID)
	q.query = query
	q.queries = append(q.queries, query)
	q.args = append([]any(nil), args...)
	q.argsList = append(q.argsList, append([]any(nil), args...))
	if q.err != nil {
		return nil, q.err
	}
	var rows *fakeSourceFileRows
	if len(q.rowsQueue) > 0 {
		row := q.rowsQueue[0]
		q.rowsQueue = q.rowsQueue[1:]
		if errors.Is(row.err, sql.ErrNoRows) {
			rows = &fakeSourceFileRows{}
		} else {
			rows = &fakeSourceFileRows{
				values:        [][]any{row.values},
				err:           row.err,
				scanErr:       row.scanErr,
				closeErr:      row.closeErr,
				errAfterClose: row.errAfterClose,
			}
		}
	} else if q.rows != nil {
		q.rows.index = 0
		rows = q.rows
	} else if q.row.values != nil || q.row.err != nil || q.row.scanErr != nil || q.row.closeErr != nil || q.row.errAfterClose != nil {
		rows = &fakeSourceFileRows{
			values:        [][]any{q.row.values},
			err:           q.row.err,
			scanErr:       q.row.scanErr,
			closeErr:      q.row.closeErr,
			errAfterClose: q.row.errAfterClose,
		}
	} else {
		rows = &fakeSourceFileRows{}
	}
	q.tenantRows = append(q.tenantRows, rows)
	return rows, nil
}

type fakeSourceFileRow struct {
	values        []any
	err           error
	scanErr       error
	closeErr      error
	errAfterClose error
}

func (r fakeSourceFileRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	for index, value := range r.values {
		if index >= len(dest) {
			return errors.New("fake source file row has more values than scan destinations")
		}
		switch target := dest[index].(type) {
		case *bool:
			*target = value.(bool)
		case *string:
			*target = value.(string)
		case *int64:
			*target = value.(int64)
		default:
			return errors.New("unsupported scan target")
		}
	}
	return nil
}

type recordingObjectVerifier struct {
	input ObjectVerificationInput
	err   error
	calls int
}

func (v *recordingObjectVerifier) VerifyObject(ctx context.Context, input ObjectVerificationInput) error {
	v.input = input
	v.calls++
	return v.err
}

type fakeSourceFileRows struct {
	values        [][]any
	index         int
	err           error
	scanErr       error
	closeErr      error
	errAfterClose error
	closed        bool
	aborted       bool
}

func (r *fakeSourceFileRows) Next() bool {
	return r.index < len(r.values)
}

func (r *fakeSourceFileRows) Scan(dest ...any) error {
	if r.scanErr != nil {
		return r.scanErr
	}
	if r.index >= len(r.values) {
		return errors.New("scan past end")
	}
	row := fakeSourceFileRow{values: r.values[r.index]}
	r.index++
	return row.Scan(dest...)
}

func (r *fakeSourceFileRows) Close() error {
	r.closed = true
	return r.closeErr
}

func (r *fakeSourceFileRows) Err() error {
	if r.closed && r.errAfterClose != nil {
		return r.errAfterClose
	}
	return r.err
}

func (r *fakeSourceFileRows) Abort() error {
	r.aborted = true
	r.closed = true
	return nil
}
