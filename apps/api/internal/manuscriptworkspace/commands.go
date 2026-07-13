package manuscriptworkspace

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"

	"github.com/google/uuid"
)

type CommandInput struct {
	Scope
	CommandType     string         `json:"command_type"`
	TargetChapterID string         `json:"target_chapter_id,omitempty"`
	TargetSceneID   string         `json:"target_scene_id,omitempty"`
	TargetBlockID   string         `json:"target_block_id,omitempty"`
	Options         map[string]any `json:"options,omitempty"`
}

type CommandRun struct {
	CommandRunID    string `json:"command_run_id"`
	ProjectID       string `json:"project_id"`
	CommandType     string `json:"command_type"`
	TargetChapterID string `json:"target_chapter_id,omitempty"`
	TargetSceneID   string `json:"target_scene_id,omitempty"`
	TargetBlockID   string `json:"target_block_id,omitempty"`
	StarterKind     string `json:"starter_kind"`
	CandidateKind   string `json:"candidate_kind"`
	Status          string `json:"status"`
	WorkflowRunID   string `json:"workflow_run_id,omitempty"`
	WriterRunID     string `json:"writer_run_id,omitempty"`
	CandidateCount  int    `json:"candidate_count"`
	MatchCount      int    `json:"match_count"`
	ErrorCode       string `json:"error_code,omitempty"`
	CreatedAt       string `json:"created_at"`
	UpdatedAt       string `json:"updated_at"`
}

type LexiconMatch struct {
	EntryID string `json:"entry_id"`
	BlockID string `json:"block_id"`
	Term    string `json:"term"`
	Count   int    `json:"count"`
}

type CommandResult struct {
	Run     CommandRun     `json:"run"`
	Matches []LexiconMatch `json:"matches,omitempty"`
	Replay  bool           `json:"replay"`
}

type WriterStartInput struct {
	TenantID        string
	ProjectID       string
	ActorUserID     string
	RequestID       string
	CommandRunID    string
	CommandType     string
	TargetChapterID string
	TargetSceneID   string
	TargetBlockID   string
	CandidateKind   string
	CandidateOnly   bool
	Options         map[string]any
}

type WorkflowStartInput = WriterStartInput

type StartedRun struct {
	RunID string
}

type WriterStarter interface {
	StartWriter(context.Context, WriterStartInput) (StartedRun, error)
}

type WorkflowStarter interface {
	StartWorkflow(context.Context, WorkflowStartInput) (StartedRun, error)
}

type CommandRepository interface {
	PrepareCommand(context.Context, CommandInput, commandSpec, string) (CommandRun, bool, error)
	MarkCommandQueued(context.Context, Scope, string, string, string) (CommandRun, error)
	MarkCommandFailed(context.Context, Scope, string, string) error
	ExecuteLexiconScan(context.Context, CommandInput, string) (CommandRun, []LexiconMatch, error)
	GetCommand(context.Context, Scope, string) (CommandRun, error)
}

type CommandService struct {
	repository CommandRepository
	writer     WriterStarter
	workflow   WorkflowStarter
}

func NewCommandService(repository CommandRepository, writer WriterStarter, workflow WorkflowStarter) *CommandService {
	return &CommandService{repository: repository, writer: writer, workflow: workflow}
}

func (s *CommandService) Admit(ctx context.Context, input CommandInput) (CommandResult, error) {
	input = normalizeCommandInput(input)
	spec, err := validateCommandInput(input)
	if err != nil {
		return CommandResult{}, err
	}
	if s == nil || s.repository == nil {
		return CommandResult{}, commandBackendUnconfigured()
	}
	fingerprint, err := commandFingerprint(input)
	if err != nil {
		return CommandResult{}, validation("command options must be JSON serializable")
	}
	run, replay, err := s.repository.PrepareCommand(ctx, input, spec, fingerprint)
	if err != nil || replay {
		return CommandResult{Run: run, Replay: replay}, err
	}
	if spec.starterKind == "deterministic" {
		run, matches, err := s.repository.ExecuteLexiconScan(ctx, input, run.CommandRunID)
		return CommandResult{Run: run, Matches: matches}, err
	}
	started, err := s.start(ctx, input, run, spec)
	if err != nil {
		if compensationErr := s.repository.MarkCommandFailed(ctx, input.Scope, run.CommandRunID, "COMMAND_START_FAILED"); compensationErr != nil {
			return CommandResult{}, &AppError{Code: "COMMAND_COMPENSATION_FAILED", Message: "writer command start compensation failed", cause: compensationErr}
		}
		return CommandResult{}, &AppError{Code: "COMMAND_START_FAILED", Message: "writer command start failed"}
	}
	run, err = s.repository.MarkCommandQueued(ctx, input.Scope, run.CommandRunID, spec.starterKind, started.RunID)
	if err != nil {
		return CommandResult{}, err
	}
	return CommandResult{Run: run}, nil
}

func (s *CommandService) start(ctx context.Context, input CommandInput, run CommandRun, spec commandSpec) (StartedRun, error) {
	startInput := WriterStartInput{
		TenantID: input.TenantID, ProjectID: input.ProjectID, ActorUserID: input.ActorUserID,
		RequestID: input.RequestID, CommandRunID: run.CommandRunID, CommandType: input.CommandType,
		TargetChapterID: input.TargetChapterID, TargetSceneID: input.TargetSceneID,
		TargetBlockID: input.TargetBlockID, CandidateKind: spec.candidateKind,
		CandidateOnly: true, Options: cloneOptions(input.Options),
	}
	if spec.starterKind == "writer" {
		if s.writer == nil {
			return StartedRun{}, commandBackendUnconfigured()
		}
		return s.writer.StartWriter(ctx, startInput)
	}
	if s.workflow == nil {
		return StartedRun{}, commandBackendUnconfigured()
	}
	return s.workflow.StartWorkflow(ctx, startInput)
}

type commandSpec struct {
	starterKind    string
	candidateKind  string
	requireChapter bool
	requireBlock   bool
}

var commandSpecs = map[string]commandSpec{
	CommandCompleteOutline:   {starterKind: "workflow", candidateKind: "outline", requireChapter: true},
	CommandAlignWords:        {starterKind: "writer", candidateKind: "prose", requireBlock: true},
	CommandScanLexicon:       {starterKind: "deterministic", candidateKind: "lexicon_match"},
	CommandFillRelationships: {starterKind: "workflow", candidateKind: "relationship", requireChapter: true},
	CommandContinueChapter:   {starterKind: "writer", candidateKind: "draft", requireChapter: true},
}

func validateCommandInput(input CommandInput) (commandSpec, error) {
	if err := validateScope(input.Scope, true); err != nil {
		return commandSpec{}, err
	}
	spec, ok := commandSpecs[input.CommandType]
	if !ok {
		return commandSpec{}, validation("command_type is not supported")
	}
	if spec.requireChapter && input.TargetChapterID == "" {
		return commandSpec{}, validation("target_chapter_id is required for this command")
	}
	if spec.requireBlock && input.TargetBlockID == "" {
		return commandSpec{}, validation("target_block_id is required for this command")
	}
	if input.TargetSceneID != "" && input.TargetChapterID == "" {
		return commandSpec{}, validation("target_scene_id requires target_chapter_id")
	}
	return spec, nil
}

func normalizeCommandInput(input CommandInput) CommandInput {
	input.Scope = normalizeScope(input.Scope)
	input.CommandType = strings.ToLower(strings.TrimSpace(input.CommandType))
	input.TargetChapterID = strings.TrimSpace(input.TargetChapterID)
	input.TargetSceneID = strings.TrimSpace(input.TargetSceneID)
	input.TargetBlockID = strings.TrimSpace(input.TargetBlockID)
	if input.Options == nil {
		input.Options = map[string]any{}
	}
	return input
}

func commandFingerprint(input CommandInput) (string, error) {
	payload, err := json.Marshal(struct {
		CommandType string         `json:"command_type"`
		ChapterID   string         `json:"chapter_id"`
		SceneID     string         `json:"scene_id"`
		BlockID     string         `json:"block_id"`
		Options     map[string]any `json:"options"`
	}{input.CommandType, input.TargetChapterID, input.TargetSceneID, input.TargetBlockID, input.Options})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:]), nil
}

func cloneOptions(options map[string]any) map[string]any {
	payload, err := json.Marshal(options)
	if err != nil {
		return map[string]any{}
	}
	result := map[string]any{}
	_ = json.Unmarshal(payload, &result)
	return result
}

func (s *SQLStore) PrepareCommand(ctx context.Context, input CommandInput, spec commandSpec, fingerprint string) (CommandRun, bool, error) {
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return CommandRun{}, false, commandWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	if err := validateCommandTargets(ctx, tx, input); err != nil {
		return CommandRun{}, false, err
	}
	commandRunID := uuid.NewString()
	result, err := tx.ExecContext(ctx, `INSERT INTO writer_command_runs (
  tenant_id, command_run_id, project_id, command_type, target_chapter_id, target_scene_id,
  target_block_id, starter_kind, candidate_kind, status, request_id, input_fingerprint, created_by
) VALUES ($1::uuid, $5::uuid, $2::uuid, $6, NULLIF($7, '')::uuid, NULLIF($8, '')::uuid,
  NULLIF($9, '')::uuid, $10, $11, 'starting', $3, $12, $4::uuid)
ON CONFLICT (tenant_id, project_id, request_id) DO NOTHING`, input.TenantID, input.ProjectID,
		input.RequestID, input.ActorUserID, commandRunID, input.CommandType, input.TargetChapterID,
		input.TargetSceneID, input.TargetBlockID, spec.starterKind, spec.candidateKind, fingerprint)
	if err != nil {
		return CommandRun{}, false, commandWriteFailed()
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return CommandRun{}, false, commandWriteFailed()
	}
	run, storedFingerprint, err := getCommandTx(ctx, tx, input.Scope, "", input.RequestID, true)
	if err != nil {
		return CommandRun{}, false, err
	}
	if storedFingerprint != fingerprint {
		return CommandRun{}, false, &AppError{Code: "IDEMPOTENCY_CONFLICT", Message: "request_id was already used for a different writer command"}
	}
	if err := tx.Commit(); err != nil {
		return CommandRun{}, false, commandWriteFailed()
	}
	return run, rows == 0, nil
}

func validateCommandTargets(ctx context.Context, tx *sql.Tx, input CommandInput) error {
	if input.TargetChapterID != "" {
		var id string
		err := tx.QueryRowContext(ctx, `SELECT chapter_id::text FROM chapters
WHERE tenant_id::text = $1 AND project_id::text = $2 AND chapter_id::text = $3`,
			input.TenantID, input.ProjectID, input.TargetChapterID).Scan(&id)
		if errors.Is(err, sql.ErrNoRows) {
			return notFound("command target chapter not found")
		}
		if err != nil {
			return commandWriteFailed()
		}
	}
	if input.TargetSceneID != "" {
		var id string
		err := tx.QueryRowContext(ctx, `SELECT scene_id::text FROM scenes
WHERE tenant_id::text = $1 AND project_id::text = $2 AND scene_id::text = $3 AND chapter_id::text = $4`,
			input.TenantID, input.ProjectID, input.TargetSceneID, input.TargetChapterID).Scan(&id)
		if errors.Is(err, sql.ErrNoRows) {
			return notFound("command target scene not found")
		}
		if err != nil {
			return commandWriteFailed()
		}
	}
	if input.TargetBlockID != "" {
		var id string
		err := tx.QueryRowContext(ctx, `SELECT block_id::text FROM manuscript_blocks
WHERE tenant_id::text = $1 AND project_id::text = $2 AND block_id::text = $3 AND status = 'active'`,
			input.TenantID, input.ProjectID, input.TargetBlockID).Scan(&id)
		if errors.Is(err, sql.ErrNoRows) {
			return notFound("command target manuscript block not found")
		}
		if err != nil {
			return commandWriteFailed()
		}
	}
	return nil
}

func (s *SQLStore) MarkCommandQueued(ctx context.Context, scope Scope, commandRunID, starterKind, runID string) (CommandRun, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, true); err != nil || commandRunID == "" || runID == "" {
		return CommandRun{}, validation("command_run_id and started run_id are required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return CommandRun{}, commandWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	column := "workflow_run_id"
	if starterKind == "writer" {
		column = "writer_run_id"
	}
	query := `UPDATE writer_command_runs SET status = 'queued', ` + column + ` = $4::uuid,
  started_at = now(), updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND command_run_id::text = $3 AND status = 'starting'`
	result, err := tx.ExecContext(ctx, query, scope.TenantID, scope.ProjectID, commandRunID, runID)
	if err != nil {
		return CommandRun{}, commandWriteFailed()
	}
	count, _ := result.RowsAffected()
	if count != 1 {
		return CommandRun{}, &AppError{Code: "COMMAND_STATE_CONFLICT", Message: "writer command is no longer starting"}
	}
	run, _, err := getCommandTx(ctx, tx, scope, commandRunID, "", false)
	if err != nil {
		return CommandRun{}, err
	}
	if err := tx.Commit(); err != nil {
		return CommandRun{}, commandWriteFailed()
	}
	return run, nil
}

func (s *SQLStore) MarkCommandFailed(ctx context.Context, scope Scope, commandRunID, errorCode string) error {
	tx, err := s.begin(ctx, normalizeScope(scope))
	if err != nil {
		return commandWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	result, err := tx.ExecContext(ctx, `UPDATE writer_command_runs
SET status = 'failed', error_code = $4, completed_at = now(), updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND command_run_id::text = $3 AND status = 'starting'`,
		scope.TenantID, scope.ProjectID, commandRunID, errorCode)
	if err != nil {
		return commandWriteFailed()
	}
	count, _ := result.RowsAffected()
	if count != 1 {
		return &AppError{Code: "COMMAND_COMPENSATION_FAILED", Message: "writer command start compensation failed"}
	}
	if err := tx.Commit(); err != nil {
		return commandWriteFailed()
	}
	return nil
}

func (s *SQLStore) ExecuteLexiconScan(ctx context.Context, input CommandInput, commandRunID string) (CommandRun, []LexiconMatch, error) {
	tx, err := s.begin(ctx, input.Scope)
	if err != nil {
		return CommandRun{}, nil, commandWriteFailed()
	}
	defer func() { _ = tx.Rollback() }()
	rows, err := tx.QueryContext(ctx, `SELECT lexicon.lexicon_entry_id::text, block.block_id::text, lexicon.term,
  (length(lower(block.content_text)) - length(replace(lower(block.content_text), lower(lexicon.term), ''))) / NULLIF(length(lexicon.term), 0)
FROM forbidden_lexicon_entries AS lexicon
JOIN manuscript_blocks AS block
  ON block.tenant_id = lexicon.tenant_id AND block.project_id = lexicon.project_id
WHERE lexicon.tenant_id::text = $1 AND lexicon.project_id::text = $2
  AND lexicon.enabled = TRUE AND block.status = 'active'
  AND ($3 = '' OR block.chapter_id::text = $3)
  AND ($4 = '' OR block.scene_id::text = $4)
  AND ($5 = '' OR block.block_id::text = $5)
  AND position(lower(lexicon.term) in lower(block.content_text)) > 0
ORDER BY block.block_order, lexicon.term, lexicon.lexicon_entry_id`, input.TenantID, input.ProjectID,
		input.TargetChapterID, input.TargetSceneID, input.TargetBlockID)
	if err != nil {
		return CommandRun{}, nil, lexiconScanFailed(err)
	}
	matches := []LexiconMatch{}
	total := 0
	for rows.Next() {
		var match LexiconMatch
		if err := rows.Scan(&match.EntryID, &match.BlockID, &match.Term, &match.Count); err != nil {
			_ = rows.Close()
			return CommandRun{}, nil, lexiconScanFailed(err)
		}
		matches = append(matches, match)
		total += match.Count
	}
	if err := rows.Err(); err != nil {
		_ = rows.Close()
		return CommandRun{}, nil, lexiconScanFailed(err)
	}
	if err := rows.Close(); err != nil {
		return CommandRun{}, nil, lexiconScanFailed(err)
	}
	result, err := tx.ExecContext(ctx, `UPDATE writer_command_runs
SET status = 'completed', match_count = $4, candidate_count = 0,
  started_at = now(), completed_at = now(), updated_at = now()
WHERE tenant_id::text = $1 AND project_id::text = $2 AND command_run_id::text = $3
  AND command_type = 'scan_lexicon' AND starter_kind = 'deterministic' AND status = 'starting'`,
		input.TenantID, input.ProjectID, commandRunID, total)
	if err != nil {
		return CommandRun{}, nil, lexiconScanFailed(err)
	}
	count, _ := result.RowsAffected()
	if count != 1 {
		return CommandRun{}, nil, &AppError{Code: "COMMAND_STATE_CONFLICT", Message: "writer command is no longer starting"}
	}
	run, _, err := getCommandTx(ctx, tx, input.Scope, commandRunID, "", false)
	if err != nil {
		return CommandRun{}, nil, err
	}
	if err := tx.Commit(); err != nil {
		return CommandRun{}, nil, lexiconScanFailed(err)
	}
	return run, matches, nil
}

func (s *SQLStore) GetCommand(ctx context.Context, scope Scope, commandRunID string) (CommandRun, error) {
	scope = normalizeScope(scope)
	if err := validateScope(scope, false); err != nil || strings.TrimSpace(commandRunID) == "" {
		return CommandRun{}, validation("command_run_id is required")
	}
	tx, err := s.begin(ctx, scope)
	if err != nil {
		return CommandRun{}, queryFailed()
	}
	defer func() { _ = tx.Rollback() }()
	run, _, err := getCommandTx(ctx, tx, scope, commandRunID, "", false)
	if err != nil {
		return CommandRun{}, err
	}
	if err := tx.Commit(); err != nil {
		return CommandRun{}, queryFailed()
	}
	return run, nil
}

const commandSelect = `SELECT command_run_id::text, project_id::text, command_type,
  COALESCE(target_chapter_id::text, ''), COALESCE(target_scene_id::text, ''), COALESCE(target_block_id::text, ''),
  starter_kind, candidate_kind, status, COALESCE(workflow_run_id::text, ''), COALESCE(writer_run_id::text, ''),
  candidate_count, match_count, COALESCE(error_code, ''), created_at::text, updated_at::text, input_fingerprint
FROM writer_command_runs`

func getCommandTx(ctx context.Context, tx *sql.Tx, scope Scope, commandRunID, requestID string, lock bool) (CommandRun, string, error) {
	query := commandSelect + ` WHERE tenant_id::text = $1 AND project_id::text = $2`
	args := []any{scope.TenantID, scope.ProjectID}
	if commandRunID != "" {
		query += ` AND command_run_id::text = $3`
		args = append(args, commandRunID)
	} else {
		query += ` AND request_id = $3`
		args = append(args, requestID)
	}
	if lock {
		query += " FOR UPDATE"
	}
	var run CommandRun
	var fingerprint string
	err := tx.QueryRowContext(ctx, query, args...).Scan(&run.CommandRunID, &run.ProjectID, &run.CommandType,
		&run.TargetChapterID, &run.TargetSceneID, &run.TargetBlockID, &run.StarterKind, &run.CandidateKind,
		&run.Status, &run.WorkflowRunID, &run.WriterRunID, &run.CandidateCount, &run.MatchCount,
		&run.ErrorCode, &run.CreatedAt, &run.UpdatedAt, &fingerprint)
	if errors.Is(err, sql.ErrNoRows) {
		return CommandRun{}, "", notFound("writer command not found")
	}
	if err != nil {
		return CommandRun{}, "", queryFailed()
	}
	return run, fingerprint, nil
}

func commandBackendUnconfigured() *AppError {
	return &AppError{Code: "COMMAND_BACKEND_UNCONFIGURED", Message: "writer command backend is not configured"}
}
func commandWriteFailed() *AppError {
	return &AppError{Code: "COMMAND_WRITE_FAILED", Message: "writer command admission failed"}
}
func lexiconScanFailed(err error) *AppError {
	return &AppError{Code: "LEXICON_SCAN_FAILED", Message: "deterministic lexicon scan failed", cause: err}
}
