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
      <section className="panel overview-analysis-candidates error-box" aria-labelledby="analysis-candidates-heading">
        <h3 id="analysis-candidates-heading">
          <Bi zh="分析候选" en="Analysis candidates" />
        </h3>
        <p>{candidates.message || tx(locale, "无法加载分析候选。", "Could not load analysis candidates.")}</p>
      </section>
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

  return (
    <section className="panel overview-analysis-candidates" aria-labelledby="analysis-candidates-heading">
      <h3 id="analysis-candidates-heading">
        <Bi zh="拆解结果（分析候选）" en="Analysis results (candidates)" />
      </h3>
      <p className="form-hint">
        <Bi
          zh="这里是本次分析整理出的角色、关系、规则等。默认不是正典资产，审阅后再入库。"
          en="Characters, relationships, and rules from this run. Not canon until you review and accept them."
        />
      </p>
      {items.length === 0 ? (
        <p className="form-hint">
          <Bi zh="尚无候选结果。分析完成后会出现角色、关系、规则等条目。" en="No candidates yet. Characters, relationships, and rules appear after analysis completes." />
        </p>
      ) : (
        <>
          <p className="overview-analysis-candidate-summary">
            <strong>
              <Bi zh={`共 ${items.length} 项`} en={`${items.length} items`} />
            </strong>
            {typeSummary ? <span>{typeSummary}</span> : null}
          </p>
          <ul className="overview-analysis-candidate-list">
            {previewItems.map((item) => (
              <li key={item.candidate_id} data-status={item.status} data-type={item.candidate_type}>
                <strong>{item.name || item.candidate_type}</strong>
                <span>
                  {item.candidate_type} · {item.status}
                </span>
              </li>
            ))}
          </ul>
          {items.length > previewLimit ? (
            <p className="form-hint">
              <Bi
                zh={`列表仅预览前 ${previewLimit} 项；完整条目请到素材库继续处理。`}
                en={`Showing the first ${previewLimit} items; open Materials for the full set.`}
              />
            </p>
          ) : null}
        </>
      )}
      <p className="overview-analysis-candidate-actions">
        <a className="text-link" href={materialsHref}>
          <Bi zh="前往素材库继续处理" en="Continue in Materials" />
        </a>
      </p>
    </section>
  );
}
