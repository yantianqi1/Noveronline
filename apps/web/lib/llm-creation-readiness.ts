import type { ProjectOverviewSummary } from "./api";

export type CreationReadinessBlocker = {
  zh: string;
  en: string;
};

export type CreationReadinessResult = {
  ready: boolean;
  blockers: CreationReadinessBlocker[];
  primaryAction: { zh: string; en: string } | null;
  llmFacilityHref: string;
};

export function evaluateCreationReadiness(
  projectOverview: ProjectOverviewSummary,
  tenantSlug: string,
  projectId: string,
): CreationReadinessResult {
  const llmFacilityHref = llmFacilityProjectHref(tenantSlug, projectId);

  if (!projectOverview.ok) {
    return {
      ready: false,
      blockers: [
        {
          zh: "项目概览暂不可用，无法确认创作就绪状态。",
          en: "Project overview is unavailable; creation readiness cannot be confirmed.",
        },
      ],
      primaryAction: { zh: "完成模型与预算设置", en: "Complete model & budget setup" },
      llmFacilityHref,
    };
  }

  const blockers: CreationReadinessBlocker[] = [];

  if (projectOverview.llm_enabled_channel_count <= 0) {
    blockers.push({
      zh: "尚未启用任何 LLM 通道，创作调用无法开始。",
      en: "No LLM channel is enabled yet, so creative workflows cannot start.",
    });
  }

  if (projectOverview.llm_missing_core_module_count > 0) {
    blockers.push({
      zh: `还有 ${projectOverview.llm_missing_core_module_count} 个核心模块未绑定模型。`,
      en: `${projectOverview.llm_missing_core_module_count} core module(s) still need model bindings.`,
    });
  }

  if (!projectOverview.llm_has_quota_policy) {
    blockers.push({
      zh: "尚未配置 LLM 配额策略，生产调用将关闭失败。",
      en: "No LLM quota policy is configured; production calls fail closed.",
    });
  }

  if (projectOverview.llm_sync_failed_channel_count > 0) {
    blockers.push({
      zh: `${projectOverview.llm_sync_failed_channel_count} 个通道同步失败，请检查模型与凭证。`,
      en: `${projectOverview.llm_sync_failed_channel_count} channel(s) failed to sync; check models and credentials.`,
    });
  }

  const ready = blockers.length === 0;
  return {
    ready,
    blockers,
    primaryAction: ready ? null : { zh: "完成模型与预算设置", en: "Complete model & budget setup" },
    llmFacilityHref,
  };
}

export function llmFacilityProjectHref(tenantSlug: string, projectId: string) {
  return `/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/llm-facility`;
}