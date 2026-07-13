package manuscriptexport

import (
	"context"
	"strings"
	"time"

	"mirofish-novel/apps/api/internal/manuscriptworkspace"
	"mirofish-novel/apps/api/internal/workflows"
)

type GeneratorConfig struct {
	States    manuscriptworkspace.ExportStateStore
	Exporter  workflows.ManuscriptArtifactExporter
	Artifacts ArtifactStore
}

type Generator struct {
	states    manuscriptworkspace.ExportStateStore
	exporter  workflows.ManuscriptArtifactExporter
	artifacts ArtifactStore
}

func NewGenerator(config GeneratorConfig) *Generator {
	return &Generator{states: config.States, exporter: config.Exporter, artifacts: config.Artifacts}
}

func (g *Generator) GenerateExport(ctx context.Context, input manuscriptworkspace.CreateExportInput) (manuscriptworkspace.ExportRecord, bool, error) {
	if g == nil || g.states == nil || g.exporter == nil || g.artifacts == nil {
		return manuscriptworkspace.ExportRecord{}, false, exportAppError("MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", "manuscript artifact generator is not configured")
	}
	if strings.ToLower(strings.TrimSpace(input.Format)) != workflows.ManuscriptArtifactFormatTXT {
		return manuscriptworkspace.ExportRecord{}, false, exportAppError("VALIDATION_FAILED", "only txt artifact generation is supported")
	}
	record, replay, err := g.states.CreateExport(ctx, input)
	if err != nil {
		return manuscriptworkspace.ExportRecord{}, false, err
	}
	if replay {
		if record.Status == "completed" || record.Status == "failed" {
			return record, true, nil
		}
		if record.Status == "generating" {
			return manuscriptworkspace.ExportRecord{}, true, exportAppError("EXPORT_STATE_CONFLICT", "manuscript export is already generating")
		}
	}
	if _, err := g.states.MarkExportGenerating(ctx, input.Scope, record.ExportID); err != nil {
		return manuscriptworkspace.ExportRecord{}, replay, err
	}

	artifact, err := g.exporter.ExportManuscriptArtifact(ctx, workflows.ExportManuscriptArtifactInput{
		TenantID: input.TenantID, ProjectID: input.ProjectID, Format: input.Format,
	})
	if err != nil {
		g.fail(input.Scope, record.ExportID, "ARTIFACT_RENDER_FAILED")
		return manuscriptworkspace.ExportRecord{}, replay, exportAppError("MANUSCRIPT_ARTIFACT_GENERATION_FAILED", "manuscript artifact rendering failed")
	}
	reference, err := g.artifacts.Write(ctx, input.TenantID, input.ProjectID, record.ExportID, artifact.Content)
	if err != nil {
		g.fail(input.Scope, record.ExportID, "ARTIFACT_STORE_FAILED")
		return manuscriptworkspace.ExportRecord{}, replay, exportAppError("MANUSCRIPT_ARTIFACT_GENERATION_FAILED", "manuscript artifact storage failed")
	}
	completed, err := g.states.CompleteExport(ctx, manuscriptworkspace.CompleteExportInput{
		Scope: input.Scope, ExportID: record.ExportID, ArtifactSHA256: artifact.SHA256,
		ArtifactSizeBytes: artifact.SizeBytes, ArtifactObjectRef: reference, BlockCount: artifact.BlockCount,
	})
	if err != nil {
		_ = g.artifacts.Delete(context.WithoutCancel(ctx), reference)
		g.fail(input.Scope, record.ExportID, "ARTIFACT_STATE_FAILED")
		return manuscriptworkspace.ExportRecord{}, replay, err
	}
	return completed.ExportRecord, replay, nil
}

func (g *Generator) fail(scope manuscriptworkspace.Scope, exportID, code string) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_, _ = g.states.FailExport(ctx, scope, exportID, code)
}

func exportAppError(code, message string) error {
	return &manuscriptworkspace.AppError{Code: code, Message: message}
}
