import { ChevronRight, Library } from "lucide-react";

import type { AnalysisCandidateSummary, AnalysisCandidatesSummary } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

type OverviewAnalysisCandidatesPanelProps = {
  locale: Locale;
  candidates: AnalysisCandidatesSummary | null;
  materialsHref: string;
};

export function OverviewAnalysisCandidatesPanel({
  locale,
  candidates,
  materialsHref,
}: OverviewAnalysisCandidatesPanelProps) {
  if (!candidates) {
    return null;
  }

  if (!candidates.ok) {
    return (
      <details className="overview-details overview-analysis-candidates error-box" open>
        <summary>
          <Library aria-hidden="true" size={18} strokeWidth={1.8} />
          <span>
            <strong id="analysis-candidates-heading">
              <Bi zh="分析候选" en="Analysis candidates" />
            </strong>
            <small><Bi zh="加载失败" en="Failed to load" /></small>
          </span>
          <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
        </summary>
        <div className="overview-details-content">
          <section>
            <p>{candidates.message || tx(locale, "无法加载分析候选。", "Could not load analysis candidates.")}</p>
          </section>
        </div>
      </details>
    );
  }

  const items = candidates.items.filter(
    (item): item is Extract<AnalysisCandidateSummary, { ok: true }> => item.ok,
  );
  const previewLimit = 24;
  const previewItems = items.slice(0, previewLimit);
  const typeCounts = items.reduce<Record<string, number>>((acc, item) => {
    const key = item.candidate_type || "other";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const typeSummary = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => `${type} ${count}`)
    .join(" · ");
  const summaryHint =
    items.length === 0
      ? tx(locale, "完成后在此预览", "Preview after analysis")
      : tx(locale, `已入库 ${items.length} 项`, `${items.length} items imported`);

  return (
    <details className="overview-details overview-analysis-candidates" open>
      <summary>
        <Library aria-hidden="true" size={18} strokeWidth={1.8} />
        <span>
          <strong id="analysis-candidates-heading">
            <Bi zh="拆解结果（已自动入库）" en="Analysis results (auto-imported)" />
          </strong>
          <small>{summaryHint}</small>
        </span>
        <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
      </summary>
      <div className="overview-details-content">
        <section>
          <p className="form-hint">
            <Bi
              zh="拆解完成后会自动写入素材库，可直接在资产库查看角色、关系、世界规则等。它们标记为「素材」，可随时编辑或升为正典。"
              en="When analysis finishes, results are auto-imported into the library. Open Assets to browse characters, relationships, and world rules. They are stored as materials you can edit or promote to canon."
            />
          </p>
          {items.length === 0 ? (
            <p className="form-hint">
              <Bi zh="尚无拆解结果。分析完成后会出现角色、关系、规则等条目，并自动入库。" en="No results yet. After analysis completes, characters, relationships, and rules appear here and are auto-imported." />
            </p>
          ) : (
            <>
              <p className="overview-analysis-candidate-summary">
                <strong>
                  <Bi zh={`已入库 ${items.length} 项`} en={`${items.length} items imported`} />
                </strong>
                {typeSummary ? <span>{typeSummary}</span> : null}
              </p>
              <ul className="overview-analysis-candidate-list">
                {previewItems.map((item) => (
                  <li key={item.candidate_id} data-status={item.status} data-type={item.candidate_type}>
                    <strong>{item.name || item.candidate_type}</strong>
                    <span>
                      {item.candidate_type}
                      {item.status === "accepted" || item.status === "candidate" ? (
                        <> · <Bi zh="已入库" en="imported" /></>
                      ) : (
                        <> · {item.status}</>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              {items.length > previewLimit ? (
                <p className="form-hint">
                  <Bi
                    zh={`列表仅预览前 ${previewLimit} 项；完整条目请到资产库查看。`}
                    en={`Showing the first ${previewLimit} items; open Assets for the full set.`}
                  />
                </p>
              ) : null}
            </>
          )}
          <p className="overview-analysis-candidate-actions">
            <a className="text-link" href={materialsHref}>
              <Bi zh="打开资产库 / 素材" en="Open Assets / Materials" />
            </a>
          </p>
        </section>
      </div>
    </details>
  );
}
