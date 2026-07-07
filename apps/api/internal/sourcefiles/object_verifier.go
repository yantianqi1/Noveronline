package sourcefiles

import (
	"context"
	"encoding/base64"
	"encoding/hex"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type MinIOObjectVerifierConfig struct {
	Endpoint  string
	AccessKey string
	SecretKey string
	Bucket    string
	UseSSL    bool
}

type minioStatClient interface {
	StatObject(context.Context, string, string, minio.StatObjectOptions) (minio.ObjectInfo, error)
}

type minioObjectVerifier struct {
	client minioStatClient
	bucket string
}

func NewMinIOObjectVerifier(config MinIOObjectVerifierConfig) (ObjectVerifier, error) {
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
	return minioObjectVerifier{client: client, bucket: bucket}, nil
}

func (v minioObjectVerifier) VerifyObject(ctx context.Context, input ObjectVerificationInput) error {
	objectKey := strings.TrimSpace(input.ObjectKey)
	if objectKey == "" || strings.TrimSpace(v.bucket) == "" || v.client == nil {
		return &AppError{Code: "SOURCE_FILE_STORAGE_VERIFY_FAILED", Message: "source file object metadata is incomplete"}
	}
	info, err := v.client.StatObject(ctx, v.bucket, objectKey, minio.StatObjectOptions{Checksum: true})
	if err != nil {
		return &AppError{Code: "SOURCE_FILE_OBJECT_NOT_FOUND", Message: "source file object was not found in object storage"}
	}
	if input.SizeBytes < 0 || strings.TrimSpace(input.SHA256) == "" {
		return sourceFileObjectVerificationFailed()
	}
	if info.Size != input.SizeBytes {
		return sourceFileObjectVerificationFailed()
	}
	if !objectSHA256Matches(info, input.SHA256) {
		return sourceFileObjectVerificationFailed()
	}
	return nil
}

func objectSHA256Matches(info minio.ObjectInfo, expected string) bool {
	expected = strings.TrimSpace(expected)
	for _, candidate := range objectSHA256Candidates(info) {
		if sha256StringMatches(candidate, expected) {
			return true
		}
	}
	return false
}

func objectSHA256Candidates(info minio.ObjectInfo) []string {
	candidates := []string{}
	if value := strings.TrimSpace(info.ChecksumSHA256); value != "" {
		candidates = append(candidates, value)
	}
	for key, value := range info.UserMetadata {
		if isSHA256MetadataKey(key) && strings.TrimSpace(value) != "" {
			candidates = append(candidates, value)
		}
	}
	for _, key := range []string{"X-Amz-Meta-Sha256", "X-Amz-Checksum-Sha256", "Sha256"} {
		if value := strings.TrimSpace(info.Metadata.Get(key)); value != "" {
			candidates = append(candidates, value)
		}
	}
	return candidates
}

func isSHA256MetadataKey(key string) bool {
	key = strings.ToLower(strings.TrimSpace(key))
	key = strings.TrimPrefix(key, "x-amz-meta-")
	key = strings.TrimPrefix(key, "x-amz-")
	return key == "sha256" || key == "checksum-sha256" || key == "content-sha256"
}

func sha256StringMatches(candidate string, expected string) bool {
	candidate = strings.TrimSpace(candidate)
	expected = strings.TrimSpace(expected)
	if candidate == "" || expected == "" {
		return false
	}
	if strings.EqualFold(candidate, expected) {
		return true
	}
	decoded, err := base64.StdEncoding.DecodeString(candidate)
	if err != nil {
		decoded, err = base64.RawStdEncoding.DecodeString(candidate)
	}
	if err != nil || len(decoded) != 32 {
		return false
	}
	return strings.EqualFold(hex.EncodeToString(decoded), expected)
}

func sourceFileObjectVerificationFailed() error {
	return &AppError{Code: "SOURCE_FILE_STORAGE_VERIFY_FAILED", Message: "source file storage verification failed"}
}
