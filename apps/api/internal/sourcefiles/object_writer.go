package sourcefiles

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type MinIOObjectWriterConfig struct {
	Endpoint     string
	AccessKey    string
	SecretKey    string
	Bucket       string
	UseSSL       bool
	MaxSizeBytes int64
}

type minioPutClient interface {
	PutObject(context.Context, string, string, io.Reader, int64, minio.PutObjectOptions) (minio.UploadInfo, error)
}

type minioObjectWriter struct {
	client       minioPutClient
	bucket       string
	maxSizeBytes int64
}

const DefaultMaxSourceUploadBytes int64 = 100 * 1024 * 1024

func NewDisabledObjectWriter() ObjectWriter {
	return disabledObjectWriter{}
}

func IsObjectWriterConfigured(writer ObjectWriter) bool {
	if writer == nil {
		return false
	}
	switch writer.(type) {
	case disabledObjectWriter:
		return false
	default:
		return true
	}
}

type disabledObjectWriter struct{}

func (disabledObjectWriter) WriteObject(context.Context, ObjectWriteInput, io.Reader) error {
	return &AppError{Code: "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", Message: "object storage backend is not configured"}
}

func NewMinIOObjectWriter(config MinIOObjectWriterConfig) (ObjectWriter, error) {
	endpoint := strings.TrimSpace(config.Endpoint)
	accessKey := strings.TrimSpace(config.AccessKey)
	secretKey := strings.TrimSpace(config.SecretKey)
	bucket := strings.TrimSpace(config.Bucket)
	if endpoint == "" || accessKey == "" || secretKey == "" || bucket == "" {
		return nil, &AppError{Code: "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", Message: "object storage backend is not fully configured"}
	}
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: config.UseSSL,
	})
	if err != nil {
		return nil, &AppError{Code: "SOURCE_FILE_STORAGE_BACKEND_UNCONFIGURED", Message: "object storage backend could not be configured"}
	}
	maxSizeBytes := config.MaxSizeBytes
	if maxSizeBytes <= 0 {
		maxSizeBytes = DefaultMaxSourceUploadBytes
	}
	return minioObjectWriter{client: client, bucket: bucket, maxSizeBytes: maxSizeBytes}, nil
}

func (w minioObjectWriter) WriteObject(ctx context.Context, input ObjectWriteInput, reader io.Reader) error {
	objectKey := strings.TrimSpace(input.ObjectKey)
	expectedSHA256 := strings.TrimSpace(input.SHA256)
	if objectKey == "" || strings.TrimSpace(w.bucket) == "" || w.client == nil || input.SizeBytes < 0 || expectedSHA256 == "" || reader == nil {
		return sourceFileObjectWriteFailed()
	}
	maxSizeBytes := w.maxSizeBytes
	if maxSizeBytes <= 0 {
		maxSizeBytes = DefaultMaxSourceUploadBytes
	}
	if input.SizeBytes > maxSizeBytes {
		return sourceFileObjectTooLarge(maxSizeBytes)
	}
	tempFile, err := os.CreateTemp("", "mirofish-source-upload-*")
	if err != nil {
		return sourceFileObjectWriteFailed()
	}
	defer func() {
		_ = tempFile.Close()
		_ = os.Remove(tempFile.Name())
	}()

	hash := sha256.New()
	bytesWritten, err := io.Copy(io.MultiWriter(tempFile, hash), io.LimitReader(reader, input.SizeBytes+1))
	if err != nil {
		return sourceFileObjectWriteFailed()
	}
	if bytesWritten != input.SizeBytes {
		return sourceFileObjectPayloadMismatch()
	}
	if !strings.EqualFold(hex.EncodeToString(hash.Sum(nil)), expectedSHA256) {
		return sourceFileObjectPayloadMismatch()
	}
	if _, err := tempFile.Seek(0, io.SeekStart); err != nil {
		return sourceFileObjectWriteFailed()
	}
	_, err = w.client.PutObject(ctx, w.bucket, objectKey, tempFile, input.SizeBytes, minio.PutObjectOptions{
		ContentType: strings.TrimSpace(input.MimeType),
		UserMetadata: map[string]string{
			"sha256": expectedSHA256,
		},
	})
	if err != nil {
		return sourceFileObjectWriteFailed()
	}
	return nil
}

func sourceFileObjectPayloadMismatch() error {
	return &AppError{Code: "SOURCE_FILE_OBJECT_PAYLOAD_MISMATCH", Message: "source file upload payload does not match admitted metadata"}
}

func sourceFileObjectTooLarge(maxSizeBytes int64) error {
	return &AppError{Code: "SOURCE_FILE_OBJECT_TOO_LARGE", Message: "source file exceeds configured upload limit of " + strconv.FormatInt(maxSizeBytes, 10) + " bytes"}
}

func sourceFileObjectWriteFailed() error {
	return &AppError{Code: "SOURCE_FILE_STORAGE_WRITE_FAILED", Message: "source file object upload failed"}
}
