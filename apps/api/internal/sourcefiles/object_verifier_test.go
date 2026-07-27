package sourcefiles

import (
	"context"
	"io"
	"strings"
	"testing"

	"github.com/minio/minio-go/v7"
)

func TestNewMinIOObjectVerifierRequiresExplicitStorageConfig(t *testing.T) {
	_, err := NewMinIOObjectVerifier(MinIOObjectVerifierConfig{
		Endpoint:  "127.0.0.1:9000",
		AccessKey: "mirofish",
		SecretKey: "secret",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED, got %s (%v)", code, err)
	}
}

func TestMinIOObjectVerifierRequiresObjectKey(t *testing.T) {
	verifier := minioObjectVerifier{bucket: "mirofish-uploads"}

	err := verifier.VerifyObject(context.Background(), ObjectVerificationInput{
		TenantID: "tenant-1",
		UploadID: "upload-1",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_STORAGE_VERIFY_FAILED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_VERIFY_FAILED, got %s (%v)", code, err)
	}
}

func TestMinIOObjectVerifierRejectsMismatchedObjectSize(t *testing.T) {
	client := &recordingMinIOStatClient{
		info: minio.ObjectInfo{
			Size:         98,
			UserMetadata: minio.StringMap{"sha256": "admitted-hash"},
		},
	}
	verifier := minioObjectVerifier{client: client, bucket: "mirofish-uploads"}

	err := verifier.VerifyObject(context.Background(), ObjectVerificationInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: 99,
		SHA256:    "admitted-hash",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_STORAGE_VERIFY_FAILED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_VERIFY_FAILED, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "source file storage verification failed" {
		t.Fatalf("expected stable verification message, got %v", err)
	}
	if client.bucket != "mirofish-uploads" || client.objectKey != "projects/project-1/source-files/upload-1/book.txt" {
		t.Fatalf("unexpected stat target: bucket=%q object=%q", client.bucket, client.objectKey)
	}
}

func TestMinIOObjectVerifierRejectsMismatchedSHA256Metadata(t *testing.T) {
	client := &recordingMinIOStatClient{
		info: minio.ObjectInfo{
			Size:         99,
			UserMetadata: minio.StringMap{"sha256": "different-hash"},
		},
	}
	verifier := minioObjectVerifier{client: client, bucket: "mirofish-uploads"}

	err := verifier.VerifyObject(context.Background(), ObjectVerificationInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: 99,
		SHA256:    "admitted-hash",
	})

	if code := ErrorCode(err); code != "SOURCE_FILE_STORAGE_VERIFY_FAILED" {
		t.Fatalf("expected SOURCE_FILE_STORAGE_VERIFY_FAILED, got %s (%v)", code, err)
	}
	if err == nil || err.Error() != "source file storage verification failed" {
		t.Fatalf("expected stable verification message, got %v", err)
	}
}

func TestMinIOObjectVerifierAcceptsMatchingObjectMetadata(t *testing.T) {
	client := &recordingMinIOStatClient{
		info: minio.ObjectInfo{
			Size:         99,
			UserMetadata: minio.StringMap{"sha256": "admitted-hash"},
		},
	}
	verifier := minioObjectVerifier{client: client, bucket: "mirofish-uploads"}

	err := verifier.VerifyObject(context.Background(), ObjectVerificationInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: 99,
		SHA256:    "admitted-hash",
	})

	if err != nil {
		t.Fatalf("verify matching object metadata: %v", err)
	}
}

func TestMinIOObjectVerifierRequestsChecksumMetadata(t *testing.T) {
	client := &recordingMinIOStatClient{
		info: minio.ObjectInfo{
			Size:           99,
			ChecksumSHA256: "admitted-hash",
		},
	}
	verifier := minioObjectVerifier{client: client, bucket: "mirofish-uploads"}

	err := verifier.VerifyObject(context.Background(), ObjectVerificationInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: 99,
		SHA256:    "admitted-hash",
	})

	if err != nil {
		t.Fatalf("verify object with checksum metadata: %v", err)
	}
	if !client.opts.Checksum {
		t.Fatalf("expected StatObject to request checksum metadata, got opts=%#v", client.opts)
	}
}

func TestMinIOObjectWriterPutsVerifiedObjectWithSHA256Metadata(t *testing.T) {
	client := &recordingMinIOPutClient{}
	writer := minioObjectWriter{client: client, bucket: "mirofish-uploads"}

	err := writer.WriteObject(context.Background(), ObjectWriteInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: int64(len("hello")),
		SHA256:    "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
		MimeType:  "text/plain",
	}, strings.NewReader("hello"))

	if err != nil {
		t.Fatalf("write object: %v", err)
	}
	if client.bucket != "mirofish-uploads" || client.objectKey != "projects/project-1/source-files/upload-1/book.txt" {
		t.Fatalf("unexpected put target: bucket=%q object=%q", client.bucket, client.objectKey)
	}
	if client.size != int64(len("hello")) || client.body != "hello" {
		t.Fatalf("unexpected put body: size=%d body=%q", client.size, client.body)
	}
	if client.opts.ContentType != "text/plain" || client.opts.UserMetadata["sha256"] != "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" {
		t.Fatalf("expected content type and sha256 metadata, got %#v", client.opts)
	}
}

func TestMinIOObjectWriterRejectsPayloadMismatchBeforePut(t *testing.T) {
	tests := []struct {
		name  string
		input ObjectWriteInput
		body  string
	}{
		{
			name: "size mismatch",
			input: ObjectWriteInput{
				ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
				SizeBytes: 99,
				SHA256:    "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
			},
			body: "hello",
		},
		{
			name: "sha mismatch",
			input: ObjectWriteInput{
				ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
				SizeBytes: int64(len("hello")),
				SHA256:    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
			},
			body: "hello",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client := &recordingMinIOPutClient{}
			writer := minioObjectWriter{client: client, bucket: "mirofish-uploads"}

			err := writer.WriteObject(context.Background(), test.input, strings.NewReader(test.body))

			if code := ErrorCode(err); code != "SOURCE_FILE_OBJECT_PAYLOAD_MISMATCH" {
				t.Fatalf("expected SOURCE_FILE_OBJECT_PAYLOAD_MISMATCH, got %s (%v)", code, err)
			}
			if client.objectKey != "" {
				t.Fatalf("payload mismatch must not put object, got object %q", client.objectKey)
			}
		})
	}
}

func TestMinIOObjectWriterRejectsDeclaredOversizeBeforeReadingOrPut(t *testing.T) {
	client := &recordingMinIOPutClient{}
	reader := &recordingReader{content: "must-not-be-read"}
	writer := minioObjectWriter{client: client, bucket: "mirofish-uploads", maxSizeBytes: 4}

	err := writer.WriteObject(context.Background(), ObjectWriteInput{
		ObjectKey: "projects/project-1/source-files/upload-1/book.txt",
		SizeBytes: 5,
		SHA256:    strings.Repeat("a", 64),
	}, reader)

	if code := ErrorCode(err); code != "SOURCE_FILE_OBJECT_TOO_LARGE" {
		t.Fatalf("expected SOURCE_FILE_OBJECT_TOO_LARGE, got %s (%v)", code, err)
	}
	if reader.reads != 0 || client.objectKey != "" {
		t.Fatalf("oversize payload was read or uploaded: reads=%d object=%q", reader.reads, client.objectKey)
	}
}

type recordingReader struct {
	content string
	reads   int
}

func (r *recordingReader) Read(p []byte) (int, error) {
	r.reads++
	if r.content == "" {
		return 0, io.EOF
	}
	n := copy(p, r.content)
	r.content = r.content[n:]
	return n, nil
}

type recordingMinIOStatClient struct {
	info      minio.ObjectInfo
	err       error
	bucket    string
	objectKey string
	opts      minio.StatObjectOptions
}

func (c *recordingMinIOStatClient) StatObject(ctx context.Context, bucket string, objectKey string, opts minio.StatObjectOptions) (minio.ObjectInfo, error) {
	c.bucket = bucket
	c.objectKey = objectKey
	c.opts = opts
	if c.err != nil {
		return minio.ObjectInfo{}, c.err
	}
	return c.info, nil
}

type recordingMinIOPutClient struct {
	bucket    string
	objectKey string
	body      string
	size      int64
	opts      minio.PutObjectOptions
	err       error
}

func (c *recordingMinIOPutClient) PutObject(ctx context.Context, bucket string, objectKey string, reader io.Reader, size int64, opts minio.PutObjectOptions) (minio.UploadInfo, error) {
	c.bucket = bucket
	c.objectKey = objectKey
	c.size = size
	c.opts = opts
	body, err := io.ReadAll(reader)
	if err != nil {
		return minio.UploadInfo{}, err
	}
	c.body = string(body)
	if c.err != nil {
		return minio.UploadInfo{}, c.err
	}
	return minio.UploadInfo{}, nil
}
