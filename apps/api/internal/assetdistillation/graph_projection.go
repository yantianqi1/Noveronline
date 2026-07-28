package assetdistillation

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

// Graph-canonical asset types that must be projected when a distillation proposal is accepted.
// Story Graph builder reads entities / relationships / plot_threads / world_rule_evidence
// (see apps/agent-runtime/mirofish_agents/temporal/graph.py), not generic assets.
var graphProjectableAssetTypes = map[string]struct{}{
	"character":    {},
	"relationship": {},
	"world_rule":   {},
	"plot_thread":  {},
}

// CONN-003: SQLStore has no StoryGraphBuildStarter dependency (central wiring lives in
// apps/api/cmd/api/main.go + httpapi). After transactional projection into Graph source
// tables, callers/MAIN integration should admit/start story_graph_build so story_graph_*
// snapshots pick up the new entities/edges. We record an audit note instead of silently
// enqueuing a rebuild from this package.
const graphRebuildAuditNote = "graph source rows projected; MAIN/story_graph_build must rebuild snapshots"

type graphProjectionSource struct {
	AssetID     string
	ProjectID   string
	AssetType   string
	Title       string
	Summary     string
	Payload     map[string]any
	RunID       string
	Evidence    string
	Confidence  *float64
	CandidateID string
}

func projectAcceptedAssetToGraph(
	ctx context.Context,
	tx *sql.Tx,
	scope Scope,
	projectID, candidateAssetID, acceptedAssetID string,
) error {
	src, err := loadGraphProjectionSource(ctx, tx, scope.TenantID, projectID, candidateAssetID, acceptedAssetID)
	if err != nil {
		return err
	}
	if src == nil {
		return nil
	}
	var projected map[string]any
	switch src.AssetType {
	case "character":
		projected, err = projectCharacterEntity(ctx, tx, scope.TenantID, projectID, *src)
	case "relationship":
		projected, err = projectRelationshipEdge(ctx, tx, scope.TenantID, projectID, *src)
	case "plot_thread":
		projected, err = projectPlotThread(ctx, tx, scope.TenantID, projectID, *src)
	case "world_rule":
		projected, err = projectWorldRuleEvidence(ctx, tx, scope.TenantID, projectID, *src)
	default:
		return nil
	}
	if err != nil {
		return err
	}
	if projected == nil {
		projected = map[string]any{}
	}
	projected["asset_type"] = src.AssetType
	projected["accepted_asset_id"] = acceptedAssetID
	projected["candidate_asset_id"] = candidateAssetID
	projected["rebuild"] = graphRebuildAuditNote
	return writeAudit(ctx, tx, scope, "asset_proposal.graph_projected", acceptedAssetID, projected)
}

func loadGraphProjectionSource(
	ctx context.Context,
	tx *sql.Tx,
	tenantID, projectID, candidateAssetID, acceptedAssetID string,
) (*graphProjectionSource, error) {
	var assetType, title, summary string
	var payloadRaw []byte
	var conf sql.NullFloat64
	// asset_type comes from the candidate (distiller type); title/summary/payload from the
	// accepted row (candidate on create, merged target on update).
	err := tx.QueryRowContext(ctx, `SELECT cand.asset_type, acc.title, COALESCE(acc.summary,''), acc.payload_jsonb, p.confidence
FROM asset_candidate_proposals p
JOIN assets cand
  ON cand.tenant_id=p.tenant_id AND cand.project_id=p.project_id AND cand.asset_id=p.candidate_asset_id
JOIN assets acc
  ON acc.tenant_id=p.tenant_id AND acc.project_id=p.project_id AND acc.asset_id=$4::uuid
WHERE p.tenant_id=$1::uuid AND p.project_id=$2::uuid AND p.candidate_asset_id=$3::uuid`,
		tenantID, projectID, candidateAssetID, acceptedAssetID,
	).Scan(&assetType, &title, &summary, &payloadRaw, &conf)
	if err != nil {
		return nil, err
	}
	assetType = strings.TrimSpace(strings.ToLower(assetType))
	if _, ok := graphProjectableAssetTypes[assetType]; !ok {
		return nil, nil
	}
	var runID string
	err = tx.QueryRowContext(ctx, `SELECT r.run_id::text
FROM asset_candidate_proposals p
JOIN manuscript_asset_distillation_requests r
  ON r.tenant_id=p.tenant_id AND r.project_id=p.project_id AND r.request_id=p.request_id
WHERE p.tenant_id=$1::uuid AND p.candidate_asset_id=$2::uuid`,
		tenantID, candidateAssetID).Scan(&runID)
	if err != nil {
		return nil, fmt.Errorf("resolve distillation run for graph projection: %w", err)
	}
	var evidence sql.NullString
	_ = tx.QueryRowContext(ctx, `SELECT string_agg(evidence_text, E'\n' ORDER BY created_at)
FROM asset_candidate_evidence
WHERE tenant_id=$1::uuid AND candidate_asset_id=$2::uuid`,
		tenantID, candidateAssetID).Scan(&evidence)

	payload := map[string]any{}
	if len(payloadRaw) > 0 {
		_ = json.Unmarshal(payloadRaw, &payload)
	}
	src := &graphProjectionSource{
		AssetID:     acceptedAssetID,
		ProjectID:   projectID,
		AssetType:   assetType,
		Title:       strings.TrimSpace(title),
		Summary:     strings.TrimSpace(summary),
		Payload:     payload,
		RunID:       runID,
		Evidence:    strings.TrimSpace(evidence.String),
		CandidateID: candidateAssetID,
	}
	if conf.Valid {
		v := conf.Float64
		src.Confidence = &v
	}
	return src, nil
}

func projectCharacterEntity(ctx context.Context, tx *sql.Tx, tenantID, projectID string, src graphProjectionSource) (map[string]any, error) {
	name := firstNonEmpty(
		payloadString(src.Payload, "canonical_name"),
		payloadString(src.Payload, "name"),
		src.Title,
	)
	if name == "" {
		return nil, appError(CodeValidationFailed, "character projection requires a title or canonical_name")
	}
	entityType := firstNonEmpty(payloadString(src.Payload, "entity_type"), "character")
	importance := nullIfEmpty(payloadString(src.Payload, "importance"))
	stateSummary := firstNonEmpty(payloadString(src.Payload, "state_summary"), src.Summary)
	meta, _ := json.Marshal(map[string]any{
		"source":             "manuscript_asset_distillation",
		"source_asset_id":    src.AssetID,
		"candidate_asset_id": src.CandidateID,
	})
	var entityID string
	err := tx.QueryRowContext(ctx, `INSERT INTO entities (
  tenant_id, project_id, source_run_id, canonical_name, entity_type,
  importance, state_summary, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4, $5, $6, NULLIF($7,''), $8::jsonb
)
ON CONFLICT (tenant_id, project_id, canonical_name)
DO UPDATE SET
  entity_type = EXCLUDED.entity_type,
  importance = COALESCE(EXCLUDED.importance, entities.importance),
  state_summary = COALESCE(EXCLUDED.state_summary, entities.state_summary),
  metadata_jsonb = entities.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING entity_id::text`,
		tenantID, projectID, src.RunID, name, entityType, importance, stateSummary, string(meta),
	).Scan(&entityID)
	if err != nil {
		return nil, err
	}
	aliases := collectAliases(src.Payload, name)
	for _, alias := range aliases {
		if _, err := tx.ExecContext(ctx, `INSERT INTO entity_aliases (tenant_id, project_id, entity_id, alias)
VALUES ($1::uuid, $2::uuid, $3::uuid, $4)
ON CONFLICT (tenant_id, entity_id, alias) DO UPDATE SET updated_at = now()`,
			tenantID, projectID, entityID, alias); err != nil {
			return nil, err
		}
	}
	return map[string]any{
		"target_kind":    "entity",
		"target_id":      entityID,
		"canonical_name": name,
		"alias_count":    len(aliases),
	}, nil
}

func projectRelationshipEdge(ctx context.Context, tx *sql.Tx, tenantID, projectID string, src graphProjectionSource) (map[string]any, error) {
	sourceName := firstNonEmpty(
		payloadString(src.Payload, "source_entity_name"),
		payloadString(src.Payload, "source_entity"),
		payloadString(src.Payload, "source"),
	)
	targetName := firstNonEmpty(
		payloadString(src.Payload, "target_entity_name"),
		payloadString(src.Payload, "target_entity"),
		payloadString(src.Payload, "target"),
	)
	relType := firstNonEmpty(
		payloadString(src.Payload, "relationship_type"),
		payloadString(src.Payload, "kind"),
		"related",
	)
	if sourceName == "" || targetName == "" {
		// Title forms like "A / B" are a common distiller fallback when payload is sparse.
		parts := splitRelationshipTitle(src.Title)
		if sourceName == "" && len(parts) > 0 {
			sourceName = parts[0]
		}
		if targetName == "" && len(parts) > 1 {
			targetName = parts[1]
		}
	}
	if sourceName == "" || targetName == "" {
		return nil, appError(CodeValidationFailed, "relationship projection requires source and target entity names")
	}
	// Ensure endpoint entities exist so Graph rebuild has nodes for the edge.
	for _, endpoint := range []string{sourceName, targetName} {
		endpointSrc := src
		endpointSrc.Title = endpoint
		endpointSrc.Summary = ""
		endpointSrc.Payload = map[string]any{"entity_type": "character"}
		if _, err := projectCharacterEntity(ctx, tx, tenantID, projectID, endpointSrc); err != nil {
			return nil, err
		}
	}
	summary := firstNonEmpty(src.Summary, payloadString(src.Payload, "summary"))
	meta, _ := json.Marshal(map[string]any{
		"source":             "manuscript_asset_distillation",
		"source_asset_id":    src.AssetID,
		"candidate_asset_id": src.CandidateID,
	})
	var relationshipID string
	err := tx.QueryRowContext(ctx, `INSERT INTO relationships (
  tenant_id, project_id, source_entity_name, target_entity_name,
  relationship_type, summary, source_run_id, evidence_text, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3, $4, $5, NULLIF($6,''), $7::uuid, NULLIF($8,''), $9::jsonb
)
ON CONFLICT (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type)
DO UPDATE SET
  summary = COALESCE(EXCLUDED.summary, relationships.summary),
  evidence_text = COALESCE(EXCLUDED.evidence_text, relationships.evidence_text),
  metadata_jsonb = relationships.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING relationship_id::text`,
		tenantID, projectID, sourceName, targetName, relType, summary, src.RunID, src.Evidence, string(meta),
	).Scan(&relationshipID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"target_kind":        "relationship",
		"target_id":          relationshipID,
		"source_entity_name": sourceName,
		"target_entity_name": targetName,
		"relationship_type":  relType,
	}, nil
}

func projectPlotThread(ctx context.Context, tx *sql.Tx, tenantID, projectID string, src graphProjectionSource) (map[string]any, error) {
	title := firstNonEmpty(payloadString(src.Payload, "title"), src.Title)
	if title == "" {
		return nil, appError(CodeValidationFailed, "plot_thread projection requires a title")
	}
	status := firstNonEmpty(
		payloadString(src.Payload, "status"),
		payloadString(src.Payload, "thread_status"),
		"open",
	)
	switch status {
	case "open", "resolved", "abandoned":
	default:
		status = "open"
	}
	summary := firstNonEmpty(src.Summary, payloadString(src.Payload, "summary"))
	meta, _ := json.Marshal(map[string]any{
		"source":             "manuscript_asset_distillation",
		"source_asset_id":    src.AssetID,
		"candidate_asset_id": src.CandidateID,
		"thread_type":        payloadString(src.Payload, "thread_type"),
	})
	var threadID string
	err := tx.QueryRowContext(ctx, `INSERT INTO plot_threads (
  tenant_id, project_id, source_run_id, title, status,
  summary, evidence_text, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4, $5, NULLIF($6,''), NULLIF($7,''), $8::jsonb
)
ON CONFLICT (tenant_id, project_id, title)
DO UPDATE SET
  status = COALESCE(EXCLUDED.status, plot_threads.status),
  summary = COALESCE(EXCLUDED.summary, plot_threads.summary),
  evidence_text = COALESCE(EXCLUDED.evidence_text, plot_threads.evidence_text),
  metadata_jsonb = plot_threads.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING thread_id::text`,
		tenantID, projectID, src.RunID, title, status, summary, src.Evidence, string(meta),
	).Scan(&threadID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"target_kind": "plot_thread",
		"target_id":   threadID,
		"title":       title,
		"status":      status,
	}, nil
}

func projectWorldRuleEvidence(ctx context.Context, tx *sql.Tx, tenantID, projectID string, src graphProjectionSource) (map[string]any, error) {
	ruleText := firstNonEmpty(
		payloadString(src.Payload, "rule_text"),
		src.Title,
		src.Summary,
	)
	if ruleText == "" {
		return nil, appError(CodeValidationFailed, "world_rule projection requires rule_text or title")
	}
	segmentID, err := ensureDistillationBridgeSegment(ctx, tx, tenantID, projectID, src)
	if err != nil {
		return nil, err
	}
	category := nullIfEmpty(firstNonEmpty(payloadString(src.Payload, "category"), "world_rule"))
	var confidence any
	if src.Confidence != nil {
		confidence = *src.Confidence
	} else if v, ok := payloadFloat(src.Payload, "confidence"); ok {
		confidence = v
	}
	meta, _ := json.Marshal(map[string]any{
		"source":             "manuscript_asset_distillation",
		"source_asset_id":    src.AssetID,
		"candidate_asset_id": src.CandidateID,
	})
	var ruleEvidenceID string
	err = tx.QueryRowContext(ctx, `INSERT INTO world_rule_evidence (
  tenant_id, project_id, run_id, segment_id, rule_text,
  evidence_text, category, confidence, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, $4::uuid, $5,
  NULLIF($6,''), $7, $8, $9::jsonb
)
ON CONFLICT (tenant_id, project_id, run_id, segment_id, rule_text)
DO UPDATE SET
  evidence_text = COALESCE(EXCLUDED.evidence_text, world_rule_evidence.evidence_text),
  category = COALESCE(EXCLUDED.category, world_rule_evidence.category),
  confidence = COALESCE(EXCLUDED.confidence, world_rule_evidence.confidence),
  metadata_jsonb = world_rule_evidence.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING rule_evidence_id::text`,
		tenantID, projectID, src.RunID, segmentID, ruleText, src.Evidence, category, confidence, string(meta),
	).Scan(&ruleEvidenceID)
	if err != nil {
		return nil, err
	}
	return map[string]any{
		"target_kind": "world_rule_evidence",
		"target_id":   ruleEvidenceID,
		"rule_text":   ruleText,
		"segment_id":  segmentID,
	}, nil
}

// world_rule_evidence.segment_id is NOT NULL and FK to text_segments. Manuscript distillation
// does not produce seed segments, so we upsert a bridge segment under the distillation run.
func ensureDistillationBridgeSegment(ctx context.Context, tx *sql.Tx, tenantID, projectID string, src graphProjectionSource) (string, error) {
	excerpt := src.Evidence
	excerptRunes := []rune(excerpt)
	if len(excerptRunes) > 240 {
		excerpt = string(excerptRunes[:240])
	}
	if excerpt == "" {
		excerpt = src.Summary
	}
	if excerpt == "" {
		excerpt = src.Title
	}
	meta, _ := json.Marshal(map[string]any{
		"source":             "manuscript_asset_distillation",
		"source_asset_id":    src.AssetID,
		"candidate_asset_id": src.CandidateID,
	})
	var segmentID string
	err := tx.QueryRowContext(ctx, `INSERT INTO text_segments (
  tenant_id, project_id, run_id, segment_order, title_guess, content_excerpt, metadata_jsonb
) VALUES (
  $1::uuid, $2::uuid, $3::uuid, 0, 'manuscript_asset_distillation', NULLIF($4,''), $5::jsonb
)
ON CONFLICT (tenant_id, project_id, run_id, segment_order)
DO UPDATE SET
  content_excerpt = COALESCE(EXCLUDED.content_excerpt, text_segments.content_excerpt),
  metadata_jsonb = text_segments.metadata_jsonb || EXCLUDED.metadata_jsonb,
  updated_at = now()
RETURNING segment_id::text`,
		tenantID, projectID, src.RunID, excerpt, string(meta),
	).Scan(&segmentID)
	return segmentID, err
}

func collectAliases(payload map[string]any, canonical string) []string {
	seen := map[string]struct{}{strings.ToLower(strings.TrimSpace(canonical)): {}}
	var out []string
	add := func(raw string) {
		alias := strings.TrimSpace(raw)
		if alias == "" {
			return
		}
		key := strings.ToLower(alias)
		if _, ok := seen[key]; ok {
			return
		}
		seen[key] = struct{}{}
		out = append(out, alias)
	}
	for _, key := range []string{"aliases", "identity_hints", "aka"} {
		switch v := payload[key].(type) {
		case []any:
			for _, item := range v {
				add(fmt.Sprint(item))
			}
		case []string:
			for _, item := range v {
				add(item)
			}
		case string:
			for _, part := range strings.Split(v, ",") {
				add(part)
			}
		}
	}
	return out
}

func splitRelationshipTitle(title string) []string {
	title = strings.TrimSpace(title)
	if title == "" {
		return nil
	}
	for _, sep := range []string{" / ", " -> ", "→", "—", " - ", "、", "vs", "VS"} {
		if strings.Contains(title, sep) {
			parts := strings.SplitN(title, sep, 2)
			out := make([]string, 0, 2)
			for _, p := range parts {
				p = strings.TrimSpace(p)
				if p != "" {
					out = append(out, p)
				}
			}
			if len(out) == 2 {
				return out
			}
		}
	}
	// Chinese relationship titles are usually "X与Y的<关系名词>" / "X和Y…". The
	// distiller often leaves the endpoints only in this natural-language title
	// (sparse payload), so recover them by splitting on the conjunction and
	// trimming the trailing relation-noun suffix from the target side.
	for _, conj := range []string{"与", "和", "跟", "同", "及", "对"} {
		idx := strings.Index(title, conj)
		if idx <= 0 {
			continue
		}
		source := strings.TrimSpace(title[:idx])
		target := strings.TrimSpace(title[idx+len(conj):])
		if source == "" || target == "" {
			continue
		}
		if before, ok := cutChineseRelationSuffix(target); ok {
			target = before
		}
		if source != "" && target != "" {
			return []string{source, target}
		}
	}
	return nil
}

// cutChineseRelationSuffix strips a trailing relation noun ("…的交易" → "…")
// from the target side of a Chinese relationship title, returning the bare
// entity name. Returns ok=false when no known suffix is present so the caller
// can keep the original target text.
func cutChineseRelationSuffix(target string) (string, bool) {
	for _, noun := range []string{"关系", "交易", "约定", "冲突", "纠葛", "恩怨", "往来", "合作", "结盟", "联盟", "对立", "矛盾", "牵连", "牵扯", "联系", "接触", "相遇", "相识", "重逢", "决裂", "和解", "对峙", "同盟", "羁绊", "渊源", "旧怨", "新仇", "密谋", "密约", "婚约", "仇怨", "仇恨"} {
		if strings.HasSuffix(target, noun) {
			stripped := strings.TrimSpace(target[:len(target)-len(noun)])
			stripped = strings.TrimSuffix(stripped, "的")
			stripped = strings.TrimSpace(stripped)
			if stripped != "" {
				return stripped, true
			}
		}
	}
	return target, false
}

func payloadString(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	v, ok := payload[key]
	if !ok || v == nil {
		return ""
	}
	switch t := v.(type) {
	case string:
		return strings.TrimSpace(t)
	default:
		return strings.TrimSpace(fmt.Sprint(t))
	}
}

func payloadFloat(payload map[string]any, key string) (float64, bool) {
	if payload == nil {
		return 0, false
	}
	v, ok := payload[key]
	if !ok || v == nil {
		return 0, false
	}
	switch t := v.(type) {
	case float64:
		return t, true
	case float32:
		return float64(t), true
	case int:
		return float64(t), true
	case int64:
		return float64(t), true
	case json.Number:
		f, err := t.Float64()
		return f, err == nil
	default:
		return 0, false
	}
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

func nullIfEmpty(v string) any {
	v = strings.TrimSpace(v)
	if v == "" {
		return nil
	}
	return v
}
