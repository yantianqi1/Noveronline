package workflows

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

const analysisAssetSourceKind = "pi_analysis"

// SQLAnalysisAssetImporter projects analysis_candidates into assets for author-friendly auto-import.
// Safe to call repeatedly: uses stable source_ref = run_id:candidate_id and ON CONFLICT upsert.
type SQLAnalysisAssetImporter struct {
	db *sql.DB
}

func NewSQLAnalysisAssetImporter(db *sql.DB) *SQLAnalysisAssetImporter {
	return &SQLAnalysisAssetImporter{db: db}
}

func (i *SQLAnalysisAssetImporter) EnsureAnalysisAssetsImported(ctx context.Context, input ImportAnalysisAssetsInput) (ImportAnalysisAssetsResult, error) {
	tenantID := strings.TrimSpace(input.TenantID)
	projectID := strings.TrimSpace(input.ProjectID)
	runID := strings.TrimSpace(input.RunID)
	if tenantID == "" || projectID == "" || runID == "" {
		return ImportAnalysisAssetsResult{}, &AppError{Code: "VALIDATION_FAILED", Message: "tenant_id, project_id, and run_id are required"}
	}
	if i == nil || i.db == nil {
		return ImportAnalysisAssetsResult{}, nil
	}

	tx, err := i.db.BeginTx(ctx, nil)
	if err != nil {
		return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.ExecContext(ctx, "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)", tenantID, projectID); err != nil {
		return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
	}

	rows, err := tx.QueryContext(ctx, `
SELECT candidate_id::text,
       candidate_type,
       name,
       COALESCE(workspace_path, ''),
       payload_jsonb
  FROM analysis_candidates
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = $3::uuid
   AND status IN ('candidate', 'accepted')
 ORDER BY created_at ASC`, tenantID, projectID, runID)
	if err != nil {
		return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
	}
	defer rows.Close()

	type row struct {
		candidateID   string
		candidateType string
		name          string
		workspacePath string
		payload       []byte
	}
	items := make([]row, 0)
	for rows.Next() {
		var item row
		if err := rows.Scan(&item.candidateID, &item.candidateType, &item.name, &item.workspacePath, &item.payload); err != nil {
			return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
	}

	imported := 0
	skipped := 0
	for _, item := range items {
		mapped := mapAnalysisCandidateToAsset(item.candidateType, item.name, item.workspacePath, item.payload)
		sourceRef := fmt.Sprintf("%s:%s", runID, item.candidateID)
		result, err := tx.ExecContext(ctx, `
INSERT INTO assets (
  tenant_id, project_id, scope, asset_type, category, lifecycle,
  title, summary, content_text, payload_jsonb, tags_jsonb,
  source_kind, source_ref, enabled, pinned, created_by
) VALUES (
  $1::uuid, $2::uuid, 'project', $3, NULLIF($4, ''), 'material',
  $5, NULLIF($6, ''), NULLIF($7, ''), $8::jsonb, $9::jsonb,
  $10, $11, true, false, NULL
)
ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
DO UPDATE SET
  category = EXCLUDED.category,
  lifecycle = 'material',
  summary = EXCLUDED.summary,
  content_text = EXCLUDED.content_text,
  payload_jsonb = EXCLUDED.payload_jsonb,
  tags_jsonb = EXCLUDED.tags_jsonb,
  enabled = true,
  updated_at = now()`,
			tenantID,
			projectID,
			mapped.assetType,
			mapped.category,
			mapped.title,
			mapped.summary,
			mapped.contentText,
			mapped.payloadJSON,
			mapped.tagsJSON,
			analysisAssetSourceKind,
			sourceRef,
		)
		if err != nil {
			return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
		}
		if affected, _ := result.RowsAffected(); affected > 0 {
			imported++
		} else {
			skipped++
		}

		if _, err := tx.ExecContext(ctx, `
UPDATE analysis_candidates
   SET status = 'accepted',
       updated_at = now()
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND candidate_id = $3::uuid
   AND status = 'candidate'`, tenantID, projectID, item.candidateID); err != nil {
			return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
		}
	}

	if err := tx.Commit(); err != nil {
		return ImportAnalysisAssetsResult{}, analysisAssetImportFailed()
	}
	return ImportAnalysisAssetsResult{ImportedCount: imported, SkippedCount: skipped}, nil
}

type mappedAnalysisAsset struct {
	assetType   string
	category    string
	title       string
	summary     string
	contentText string
	payloadJSON []byte
	tagsJSON    []byte
}

func mapAnalysisCandidateToAsset(candidateType, name, workspacePath string, payloadRaw []byte) mappedAnalysisAsset {
	normalizedType := normalizeAnalysisCandidateType(candidateType)

	payload := map[string]any{}
	if len(payloadRaw) > 0 {
		_ = json.Unmarshal(payloadRaw, &payload)
	}
	if payload == nil {
		payload = map[string]any{}
	}

	assetType := normalizedType
	switch normalizedType {
	case "note_summary":
		assetType = "note"
	case "ontology":
		assetType = "story_ontology"
	}

	category := "analysis"
	switch normalizedType {
	case "character":
		category = "characters"
	case "relationship":
		category = "relationships"
	case "world_rule":
		category = "world"
	case "plot_thread", "plot_event":
		category = "plot"
	case "ontology":
		category = "ontology"
	}

	title := composeAnalysisAssetTitle(normalizedType, name, payload)
	if len(title) > 240 {
		title = title[:240]
	}

	summary := firstString(payload, "summary", "blurb", "excerpt", "description", "rule_text")
	if summary == "" {
		summary = title
	}
	if len(summary) > 2000 {
		summary = summary[:2000]
	}
	content := composeAnalysisAssetContent(normalizedType, title, summary, payload)
	if len(content) > 20_000 {
		content = content[:20_000]
	}

	tags := []string{}
	if rawTags, ok := payload["tags"].([]any); ok {
		for _, tag := range rawTags {
			if s, ok := tag.(string); ok {
				s = strings.TrimSpace(s)
				if s != "" {
					tags = append(tags, s)
				}
			}
			if len(tags) >= 24 {
				break
			}
		}
	}
	if !containsString(tags, "pi_analysis") {
		tags = append(tags, "pi_analysis")
	}
	if !containsString(tags, normalizedType) {
		tags = append(tags, normalizedType)
	}

	payload["analysis_candidate_type"] = normalizedType
	if workspacePath != "" {
		payload["workspace_path"] = workspacePath
	}
	payload["auto_imported"] = true

	payloadJSON, _ := json.Marshal(payload)
	if payloadJSON == nil {
		payloadJSON = []byte("{}")
	}
	tagsJSON, _ := json.Marshal(tags)
	if tagsJSON == nil {
		tagsJSON = []byte("[]")
	}

	return mappedAnalysisAsset{
		assetType:   assetType,
		category:    category,
		title:       title,
		summary:     summary,
		contentText: content,
		payloadJSON: payloadJSON,
		tagsJSON:    tagsJSON,
	}
}

func normalizeAnalysisCandidateType(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "character", "relationship", "world_rule", "plot_thread", "plot_event", "ontology", "note_summary":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "note_summary"
	}
}

// typeKeyTitles are machine fallbacks that should never win over payload-derived names.
var typeKeyTitles = map[string]struct{}{
	"character": {}, "relationship": {}, "world_rule": {}, "plot_thread": {}, "plot_event": {},
	"ontology": {}, "note_summary": {}, "note": {}, "story_ontology": {},
}

func isTypeKeyTitle(value string) bool {
	_, ok := typeKeyTitles[strings.ToLower(strings.TrimSpace(value))]
	return ok
}

func composeAnalysisAssetTitle(candidateType, name string, payload map[string]any) string {
	explicit := strings.TrimSpace(name)
	if explicit != "" && !isTypeKeyTitle(explicit) {
		return explicit
	}
	if fromPayload := firstString(payload, "name", "title", "canonical_name", "label"); fromPayload != "" && !isTypeKeyTitle(fromPayload) {
		return fromPayload
	}

	switch candidateType {
	case "relationship":
		if composed := composeRelationshipTitle(payload); composed != "" {
			return composed
		}
	case "character":
		if fromPayload := firstString(payload, "character_name", "full_name"); fromPayload != "" {
			return fromPayload
		}
	case "world_rule":
		if fromPayload := firstString(payload, "rule_text", "rule", "statement"); fromPayload != "" {
			return truncateRunes(fromPayload, 80)
		}
	case "plot_thread":
		if fromPayload := firstString(payload, "thread_title", "hook"); fromPayload != "" {
			return fromPayload
		}
	case "plot_event":
		// Timeline events: a Chinese title/summary always wins over a placeholder;
		// otherwise fall back to a readable 未命名事件 · timeframe tag, never the
		// bare "plot_event" key.
		if fromPayload := firstString(payload, "summary", "description"); fromPayload != "" {
			return truncateRunes(fromPayload, 60)
		}
		if timeframe := firstString(payload, "timeframe"); timeframe != "" {
			return truncateRunes("未命名事件 · "+timeframe, 240)
		}
		return "未命名事件"
	case "note_summary":
		if fromPayload := firstString(payload, "summary", "description", "content", "text", "body", "excerpt"); fromPayload != "" {
			return truncateRunes(fromPayload, 80)
		}
	case "ontology":
		if fromPayload := firstString(payload, "summary", "description"); fromPayload != "" {
			return truncateRunes(fromPayload, 80)
		}
	}

	if explicit != "" {
		return explicit
	}
	// Never surface a bare machine type key as the title — fall back to a
	// readable untitled label instead.
	return "未命名条目"
}

func composeRelationshipTitle(payload map[string]any) string {
	source := firstString(payload,
		"source", "source_name", "source_entity", "source_entity_name",
		"from", "from_name", "a", "character_a", "left", "subject",
	)
	target := firstString(payload,
		"target", "target_name", "target_entity", "target_entity_name",
		"to", "to_name", "b", "character_b", "right", "object",
	)
	relType := firstString(payload,
		"relationship_type", "relation_type", "type", "kind", "relation", "bond_type",
	)
	if source == "" && target == "" {
		return ""
	}
	if source == "" {
		source = "?"
	}
	if target == "" {
		target = "?"
	}
	if relType != "" {
		return source + " → " + target + " / " + relType
	}
	return source + " → " + target
}

func composeAnalysisAssetContent(candidateType, title, summary string, payload map[string]any) string {
	// Rich body assembled from the preserved candidate payload so the detail
	// "正文" carries real substance instead of a copy of the one-line summary.
	switch candidateType {
	case "character", "ontology":
		if body := firstString(payload, "body", "content", "text", "content_text", "note"); body != "" {
			return body
		}
		parts := make([]string, 0, 3)
		if summary != "" {
			parts = append(parts, summary)
		}
		if desc := firstString(payload, "description", "blurb"); desc != "" && desc != summary {
			parts = append(parts, desc)
		}
		if len(parts) > 0 {
			return strings.Join(parts, "\n")
		}
	case "world_rule":
		parts := make([]string, 0, 3)
		if rule := firstString(payload, "rule_text", "rule", "statement"); rule != "" {
			parts = append(parts, rule)
		} else if summary != "" {
			parts = append(parts, summary)
		}
		if evidence := firstString(payload, "evidence", "evidence_text", "source_excerpt"); evidence != "" {
			parts = append(parts, "证据："+evidence)
		}
		if meta := joinNonEmpty("　", prefixNonEmpty("分类：", firstString(payload, "category")), prefixNonEmpty("置信度：", firstString(payload, "confidence"))); meta != "" {
			parts = append(parts, meta)
		}
		if len(parts) > 0 {
			return strings.Join(parts, "\n")
		}
	case "relationship":
		source := firstString(payload,
			"source", "source_name", "source_entity", "source_entity_name", "from", "from_name", "a", "character_a",
		)
		target := firstString(payload,
			"target", "target_name", "target_entity", "target_entity_name", "to", "to_name", "b", "character_b",
		)
		relType := firstString(payload, "relationship_type", "relation_type", "type", "kind", "relation", "bond_type")
		desc := firstString(payload, "description", "summary", "blurb")
		parts := make([]string, 0, 3)
		if source != "" || target != "" {
			line := strings.TrimSpace(source + " → " + target)
			if relType != "" {
				line += "（" + relType + "）"
			}
			parts = append(parts, line)
		}
		if desc != "" {
			parts = append(parts, desc)
		}
		if evidence := firstString(payload, "evidence", "evidence_text", "source_excerpt"); evidence != "" {
			parts = append(parts, "证据："+evidence)
		}
		if len(parts) > 0 {
			return strings.Join(parts, "\n")
		}
	case "plot_thread":
		parts := make([]string, 0, 3)
		if summary != "" {
			parts = append(parts, summary)
		}
		if status := firstString(payload, "status"); status != "" {
			parts = append(parts, "状态："+status)
		}
		if evidence := firstString(payload, "evidence", "evidence_text", "source_excerpt"); evidence != "" {
			parts = append(parts, "证据："+evidence)
		}
		if len(parts) > 0 {
			return strings.Join(parts, "\n")
		}
	case "plot_event":
		parts := make([]string, 0, 5)
		if summary != "" {
			parts = append(parts, summary)
		}
		if desc := firstString(payload, "description"); desc != "" && desc != summary {
			parts = append(parts, desc)
		}
		if timeframe := firstString(payload, "timeframe"); timeframe != "" {
			parts = append(parts, "时间："+timeframe)
		}
		if world := firstString(payload, "world"); world != "" {
			parts = append(parts, "世界："+world)
		}
		if participants := firstStringList(payload, "participants", "characters", "actors"); len(participants) > 0 {
			parts = append(parts, "涉及："+strings.Join(participants, "、"))
		}
		if len(parts) > 0 {
			return strings.Join(parts, "\n")
		}
	}

	// Generic fallback: any explicit long-form body, else the richest
	// descriptive field, else the summary/title.
	if content := firstString(payload, "content", "text", "body", "content_text", "note", "excerpt"); content != "" {
		return content
	}
	if desc := firstString(payload, "description", "blurb", "rule_text", "summary"); desc != "" {
		return desc
	}
	if summary != "" {
		return summary
	}
	return title
}

func firstStringList(payload map[string]any, keys ...string) []string {
	for _, key := range keys {
		raw, ok := payload[key].([]any)
		if !ok {
			continue
		}
		items := make([]string, 0, len(raw))
		for _, entry := range raw {
			if s, ok := entry.(string); ok {
				if trimmed := strings.TrimSpace(s); trimmed != "" {
					items = append(items, trimmed)
				}
			}
		}
		if len(items) > 0 {
			return items
		}
	}
	return nil
}

func prefixNonEmpty(prefix, value string) string {
	if value == "" {
		return ""
	}
	return prefix + value
}

func joinNonEmpty(sep string, parts ...string) string {
	kept := make([]string, 0, len(parts))
	for _, part := range parts {
		if strings.TrimSpace(part) != "" {
			kept = append(kept, part)
		}
	}
	return strings.Join(kept, sep)
}

func firstString(payload map[string]any, keys ...string) string {
	for _, key := range keys {
		if value, ok := payload[key].(string); ok {
			if trimmed := strings.TrimSpace(value); trimmed != "" {
				return trimmed
			}
		}
	}
	return ""
}

func truncateRunes(value string, max int) string {
	runes := []rune(strings.TrimSpace(value))
	if max <= 0 || len(runes) <= max {
		return string(runes)
	}
	return string(runes[:max]) + "…"
}

func containsString(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

func analysisAssetImportFailed() error {
	return &AppError{Code: "ANALYSIS_ASSET_IMPORT_FAILED", Message: "analysis asset import failed"}
}
