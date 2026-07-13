/**
 * Author-surface content boundary for the SaaS creative workspace.
 *
 * Technical material must not rely on CSS hiding alone. Author projections and
 * UI copy should keep these patterns out of default-visible surfaces.
 */

export const AUTHOR_FORBIDDEN_PATH_MARKERS = [
  "docs/refactor-saas",
  "docs/refactor-saas/",
  "AGENTS.md",
  "CLAUDE.md",
  "DEVELOPMENT_PLAN.md",
  "24-current-development-progress",
  "FRONTEND_LAYOUT_HANDOFF",
] as const;

export const AUTHOR_FORBIDDEN_TECHNICAL_MARKERS = [
  "system prompt",
  "system_prompt",
  "provider body",
  "provider_body",
  "request_body",
  "response_body",
  "encrypted_api",
  "api_key",
  "raw JSON",
  "workflow worker",
  "temporal worker",
  "queue name",
  "database url",
  "DATABASE_URL",
] as const;

/** Writer workspace patterns that must not appear in author-visible JSX projections. */
export const AUTHOR_FORBIDDEN_WRITER_SURFACE_PATTERNS = [
  /placeholder=["']chapter_id["']/,
  /placeholder=["']scene_id["']/,
  /placeholder=["']block_id["']/,
  /option\s+value=["']complete_outline["']/,
  /option\s+value=["']align_words["']/,
  /option\s+value=["']scan_lexicon["']/,
  /option\s+value=["']fill_relationships["']/,
  /option\s+value=["']continue_chapter["']/,
  /<input[^>]*name=["']orderedIds["'][^>]*defaultValue=\{[^}]*\.join\(["'],["']\)/,
  /<input[^>]*name=["']items["'][^>]*defaultValue=\{[^}]*block_id/,
  /<a[^>]*href=\{`\$\{[^}]+\}\?commandId=/,
  /<a[^>]*href=\{`\$\{[^}]+\}\?planningRunId=/,
  /<strong>\{[^}]*\.command_type\}<\/strong>/,
  /<strong>\{[^}]*\.workflow_type\}<\/strong>/,
] as const;

/** Patterns that must not appear as author-visible labels or raw dumps. */
export const AUTHOR_FORBIDDEN_UI_PATTERNS = [
  /docs\/refactor-saas/i,
  /\bAGENTS\.md\b/,
  /\bCLAUDE\.md\b/,
  /\bDEVELOPMENT_PLAN\.md\b/,
  /24-current-development-progress/i,
  /system[_\s-]?prompt/i,
  /provider[_\s-]?body/i,
  /request[_\s-]?body/i,
  /response[_\s-]?body/i,
  /encrypted[_\s-]?api/i,
  /\bapi[_\s-]?key\b/i,
  /ranking\.(?:final_score|keyword_score|vector_score|embedding_model)/i,
  /searchRanking|formatScore|raw relevance/i,
] as const;

/** Internal error codes may exist in data models but must not be primary author copy. */
export const AUTHOR_FORBIDDEN_ERROR_CODE_RENDER = [
  /\{(?:status|error)?\.code\}/,
  /\{[a-zA-Z0-9_.]*\.code\}/,
  /code:\s*\{/,
] as const;

/**
 * UUID literals are allowed in route params and form hidden fields, but not as
 * default-visible author labels such as `<dd>{run_id}</dd>`.
 */
export const AUTHOR_FORBIDDEN_VISIBLE_ID_RENDERS = [
  /<dd>\{\s*[a-zA-Z0-9_.]*(?:_id|Id|ID)\s*\}<\/dd>/,
  /<span className="form-hint">\{\s*[a-zA-Z0-9_.]*(?:asset_id|run_id|request_id)\s*\}<\/span>/,
  />\{\s*(?:selectedSeedRun|projectReadiness|projectOverview)\.(?:run_id|project_readiness_snapshot_id)\s*\}</,
] as const;

export type ContentBoundaryFinding = {
  marker: string;
  kind: "path" | "technical" | "pattern" | "writer_surface" | "error_code" | "visible_id";
};

export function scanAuthorSurfaceText(source: string): ContentBoundaryFinding[] {
  const findings: ContentBoundaryFinding[] = [];

  for (const marker of AUTHOR_FORBIDDEN_PATH_MARKERS) {
    if (source.includes(marker)) {
      findings.push({ marker, kind: "path" });
    }
  }

  for (const marker of AUTHOR_FORBIDDEN_TECHNICAL_MARKERS) {
    if (source.toLowerCase().includes(marker.toLowerCase())) {
      findings.push({ marker, kind: "technical" });
    }
  }

  for (const pattern of AUTHOR_FORBIDDEN_UI_PATTERNS) {
    if (pattern.test(source)) {
      findings.push({ marker: String(pattern), kind: "pattern" });
    }
  }

  for (const pattern of AUTHOR_FORBIDDEN_WRITER_SURFACE_PATTERNS) {
    if (pattern.test(source)) {
      findings.push({ marker: String(pattern), kind: "writer_surface" });
    }
  }

  for (const pattern of AUTHOR_FORBIDDEN_ERROR_CODE_RENDER) {
    if (pattern.test(source)) {
      findings.push({ marker: String(pattern), kind: "error_code" });
    }
  }

  for (const pattern of AUTHOR_FORBIDDEN_VISIBLE_ID_RENDERS) {
    if (pattern.test(source)) {
      findings.push({ marker: String(pattern), kind: "visible_id" });
    }
  }

  return findings;
}

export function assertAuthorSurfaceClean(source: string, surfaceName: string): void {
  const findings = scanAuthorSurfaceText(source);
  if (findings.length === 0) {
    return;
  }
  const detail = findings
    .map((finding) => `${finding.kind}:${finding.marker}`)
    .join("; ");
  throw new Error(`author surface ${surfaceName} violates content boundary: ${detail}`);
}
