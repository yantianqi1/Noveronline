package manuscriptexport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type ArtifactStore interface {
	Write(context.Context, string, string, string, []byte) (string, error)
	Read(context.Context, string) ([]byte, error)
	Delete(context.Context, string) error
}

type FileArtifactStore struct {
	root string
}

func NewFileArtifactStore(root string) (*FileArtifactStore, error) {
	root = strings.TrimSpace(root)
	if root == "" {
		return nil, errors.New("artifact root is required")
	}
	abs, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve artifact root: %w", err)
	}
	if err := os.MkdirAll(abs, 0o700); err != nil {
		return nil, fmt.Errorf("create artifact root: %w", err)
	}
	return &FileArtifactStore{root: abs}, nil
}

func (s *FileArtifactStore) Write(_ context.Context, tenantID, projectID, exportID string, content []byte) (string, error) {
	if s == nil || s.root == "" || len(content) == 0 {
		return "", errors.New("artifact store is not configured")
	}
	reference := artifactReference(tenantID, projectID, exportID)
	path, err := s.resolve(reference)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return "", err
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), ".artifact-*")
	if err != nil {
		return "", err
	}
	temporaryPath := temporary.Name()
	defer func() { _ = os.Remove(temporaryPath) }()
	if err := temporary.Chmod(0o600); err != nil {
		_ = temporary.Close()
		return "", err
	}
	if _, err := temporary.Write(content); err != nil {
		_ = temporary.Close()
		return "", err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return "", err
	}
	if err := temporary.Close(); err != nil {
		return "", err
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return "", err
	}
	return reference, nil
}

func (s *FileArtifactStore) Read(_ context.Context, reference string) ([]byte, error) {
	path, err := s.resolve(reference)
	if err != nil {
		return nil, err
	}
	return os.ReadFile(path)
}

func (s *FileArtifactStore) Delete(_ context.Context, reference string) error {
	path, err := s.resolve(reference)
	if err != nil {
		return err
	}
	err = os.Remove(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}

func (s *FileArtifactStore) resolve(reference string) (string, error) {
	if s == nil || s.root == "" || strings.TrimSpace(reference) == "" || filepath.IsAbs(reference) {
		return "", errors.New("invalid artifact reference")
	}
	clean := filepath.Clean(reference)
	if clean == "." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) || clean == ".." {
		return "", errors.New("invalid artifact reference")
	}
	path := filepath.Join(s.root, clean)
	relative, err := filepath.Rel(s.root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return "", errors.New("artifact reference escapes root")
	}
	return path, nil
}

func artifactReference(tenantID, projectID, exportID string) string {
	return filepath.Join(opaqueSegment(tenantID), opaqueSegment(projectID), opaqueSegment(exportID)+".txt")
}

func opaqueSegment(value string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(digest[:16])
}
