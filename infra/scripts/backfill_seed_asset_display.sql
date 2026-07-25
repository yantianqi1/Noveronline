BEGIN;

-- relationships: "甲 -> 乙 / 类型" → "甲 → 乙（类型）", summary falls back to
-- description/evidence, content_text puts the long description first.
UPDATE assets a
SET
  title = r.source_entity_name || ' → ' || r.target_entity_name || '（' || r.relationship_type || '）',
  summary = COALESCE(
    NULLIF(btrim(r.summary), ''),
    NULLIF(btrim(r.metadata_jsonb->>'description'), ''),
    NULLIF(btrim(r.evidence_text), ''),
    r.source_entity_name || ' 与 ' || r.target_entity_name || '：' || r.relationship_type
  ),
  content_text = concat_ws(
    E'\n',
    NULLIF(btrim(r.metadata_jsonb->>'description'), ''),
    NULLIF(btrim(r.summary), ''),
    NULLIF(E'证据：' || btrim(r.evidence_text), '证据：')
  ),
  payload_jsonb = a.payload_jsonb || jsonb_build_object('description', r.metadata_jsonb->>'description'),
  updated_at = now()
FROM relationships r
WHERE a.source_kind = 'seed_pipeline'
  AND a.source_ref = r.relationship_id::text
  AND a.asset_type = 'relationship'
  AND a.lifecycle = 'seed'
  AND a.pinned = false
  AND a.tenant_id = r.tenant_id
  AND a.project_id = r.project_id;

-- world rules: title/summary/body were all rule_text; prefer curated fields in
-- metadata when present, otherwise split title off rule_text.
UPDATE assets a
SET
  title = COALESCE(
    NULLIF(btrim(w.metadata_jsonb->>'title'), ''),
    left(btrim(w.rule_text), 40)
  ),
  summary = COALESCE(
    NULLIF(btrim(w.metadata_jsonb->>'summary'), ''),
    w.rule_text
  ),
  content_text = concat_ws(
    E'\n',
    NULLIF(btrim(COALESCE(w.metadata_jsonb->>'detail', w.metadata_jsonb->>'summary', w.rule_text)), ''),
    NULLIF(E'证据：' || btrim(w.evidence_text), '证据：'),
    NULLIF(
      btrim(concat_ws(
        E'　',
        NULLIF(E'分类：' || btrim(w.category), '分类：'),
        NULLIF(E'置信度：' || w.confidence::text, '置信度：')
      )),
      ''
    )
  ),
  payload_jsonb = a.payload_jsonb || jsonb_build_object(
    'title', w.metadata_jsonb->>'title',
    'summary', w.metadata_jsonb->>'summary',
    'detail', w.metadata_jsonb->>'detail'
  ),
  updated_at = now()
FROM world_rule_evidence w
WHERE a.source_kind = 'seed_pipeline'
  AND a.source_ref = w.rule_evidence_id::text
  AND a.asset_type = 'world_rule'
  AND a.lifecycle = 'seed'
  AND a.pinned = false
  AND a.tenant_id = w.tenant_id
  AND a.project_id = w.project_id;

-- plot threads: summary was often null; content_text leads with description.
UPDATE assets a
SET
  summary = COALESCE(
    NULLIF(btrim(p.summary), ''),
    left(btrim(p.metadata_jsonb->>'description'), 60)
  ),
  content_text = concat_ws(
    E'\n',
    NULLIF(btrim(p.metadata_jsonb->>'description'), ''),
    NULLIF(btrim(p.summary), ''),
    NULLIF(E'证据：' || btrim(p.evidence_text), '证据：')
  ),
  payload_jsonb = a.payload_jsonb || jsonb_build_object('description', p.metadata_jsonb->>'description'),
  updated_at = now()
FROM plot_threads p
WHERE a.source_kind = 'seed_pipeline'
  AND a.source_ref = p.thread_id::text
  AND a.asset_type = 'plot_thread'
  AND a.lifecycle = 'seed'
  AND a.pinned = false
  AND a.tenant_id = p.tenant_id
  AND a.project_id = p.project_id;

-- keep the search index in sync with the rewritten rows
UPDATE global_search_index g
SET
  title = a.title,
  body = COALESCE(a.summary, a.content_text, a.title),
  updated_at = now()
FROM assets a
WHERE g.source = 'asset'
  AND g.source_ref = a.asset_id::text
  AND a.source_kind = 'seed_pipeline'
  AND a.asset_type IN ('relationship', 'world_rule', 'plot_thread')
  AND g.tenant_id = a.tenant_id
  AND g.project_id = a.project_id;

COMMIT;
