/**
 * ArchiveDetailView — renders the structured template sections of an
 * archive entry (identity / motivation / tension / relationship / ...).
 *
 * Used inside the unified asset-library DetailSheet when the selected
 * UnifiedItem has `source === "archive"`. Fetches the full archive detail
 * on its own given an `archiveId`.
 *
 * Extracted from the former `/archive-library` page so that merging the
 * two libraries doesn't lose the deep archive rendering.
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ApiResponse } from "@/api/http";
import { getArchiveLibraryDetail } from "@/api/archive";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

/* ------------------------------------------------------------------ */
/*  Labels                                                             */
/* ------------------------------------------------------------------ */

const ENTITY_TYPE_LABELS: Record<string, string> = {
  character: "角色",
  organization: "组织",
  relationship: "关系",
  faction: "势力",
};

const TIER_LABELS: Record<string, string> = {
  protagonist: "主角",
  major: "主要",
  supporting: "次要",
  minor: "配角",
};

const SECTION_LABELS: Record<string, string> = {
  identity: "身份信息",
  motivation: "动机驱力",
  tension: "内在张力",
  relationship: "关系网络",
  behavior: "行为模式",
  state: "当前状态",
  risk: "风险标记",
  private: "隐秘档案",
  summary: "摘要",
  agent_profile: "角色画像",
};

const FIELD_LABELS: Record<string, string> = {
  entity_name: "名称",
  entity_type: "类型",
  role: "叙事定位",
  identity_hint: "身份线索",
  core_drive: "核心驱力",
  hidden_tension: "隐藏张力",
  summary: "关系概览",
  change: "关系变化",
  history: "关系历程",
  agent_behavior_hint: "行为倾向",
  personality: "性格特征",
  skills: "技能专长",
  status: "状态",
  surface_mask: "表面形象",
  notable_risks: "风险项",
  secrets: "秘密",
};

const HIDDEN_FIELDS = new Set(["entity_name", "entity_type"]);

const PROFILE_GROUP_CONFIG = [
  { key: "basic_info", label: "基本信息", defaultExpanded: true, fields: {
    name: "名称", aliases: "别名", identity: "身份", status: "状态",
  } as Record<string, string> },
  { key: "personality", label: "性格画像", defaultExpanded: true, fields: {
    core_traits: "核心特质", values: "价值观", fears: "恐惧与弱点", decision_pattern: "决策模式",
  } as Record<string, string> },
  { key: "motivation", label: "动机目标", defaultExpanded: true, fields: {
    ultimate_goal: "终极目标", current_objective: "当前目标", internal_conflict: "内心矛盾",
  } as Record<string, string> },
  { key: "speech", label: "语言风格", defaultExpanded: false, fields: {
    style: "表达风格", verbal_habits: "口头禅", tone_range: "语气特征", example_quotes: "经典语录",
  } as Record<string, string> },
  { key: "capabilities", label: "能力特长", defaultExpanded: false, fields: {
    skills: "技能", limitations: "局限性", resources: "掌握资源",
  } as Record<string, string> },
  { key: "knowledge_boundary", label: "知识边界", defaultExpanded: false, fields: {
    knows: "已知信息", does_not_know: "未知信息", believes_wrongly: "错误认知",
  } as Record<string, string> },
  { key: "relationships", label: "人际关系", defaultExpanded: false, fields: {} as Record<string, string> },
];

/* ------------------------------------------------------------------ */
/*  Section builder                                                    */
/* ------------------------------------------------------------------ */

interface DetailSection {
  key: string;
  label: string;
  variant: "text" | "entries" | "items" | "collapsible";
  text?: string;
  entries?: Array<{ label: string; value: string }>;
  items?: Array<{ label: string; value: string | string[] }>;
  defaultExpanded?: boolean;
}

function normalizeScalar(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value).trim();
}

function isPlaceholder(value: unknown): boolean {
  if (!value) return true;
  if (value === "暂无记录") return true;
  if (Array.isArray(value) && value.length === 1 && value[0] === "暂无记录") return true;
  return false;
}

function formatEntryValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(normalizeScalar).filter(Boolean).join("、");
  if (value && typeof value === "object") {
    return Object.entries(value)
      .map(([k, v]) => `${FIELD_LABELS[k] || k}: ${formatEntryValue(v)}`)
      .filter((s) => !s.endsWith(": "))
      .join("；");
  }
  return normalizeScalar(value);
}

function formatProfileFieldValue(value: unknown): string | string[] {
  if (Array.isArray(value)) return value.map(normalizeScalar).filter(Boolean);
  return normalizeScalar(value);
}

function buildProfileGroups(profileData: Record<string, unknown>): DetailSection[] {
  const groups: DetailSection[] = [];
  for (const config of PROFILE_GROUP_CONFIG) {
    const groupData = profileData[config.key];
    if (!groupData) continue;

    if (config.key === "relationships") {
      if (!Array.isArray(groupData) || groupData.length === 0) continue;
      const items = (groupData as Array<Record<string, string>>)
        .map((rel) => {
          if (typeof rel === "string") return { label: "关系", value: rel as string };
          const target = rel.target || rel.name || "";
          const desc = rel.description || rel.relation || rel.type || "";
          return { label: target, value: desc };
        })
        .filter((item) => item.value);
      if (!items.length) continue;
      groups.push({
        key: `profile_${config.key}`,
        label: config.label,
        variant: "collapsible",
        defaultExpanded: config.defaultExpanded,
        items,
      });
      continue;
    }

    if (typeof groupData !== "object") continue;
    const items: Array<{ label: string; value: string | string[] }> = [];
    for (const [fieldKey, fieldLabel] of Object.entries(config.fields)) {
      const rawValue = (groupData as Record<string, unknown>)[fieldKey];
      if (isPlaceholder(rawValue)) continue;
      const formatted = formatProfileFieldValue(rawValue);
      if (!formatted || (Array.isArray(formatted) && formatted.length === 0)) continue;
      items.push({ label: fieldLabel, value: formatted });
    }
    if (!items.length) continue;
    groups.push({
      key: `profile_${config.key}`,
      label: config.label,
      variant: "collapsible",
      defaultExpanded: config.defaultExpanded,
      items,
    });
  }
  return groups;
}

function buildArchiveDetailSections(archive: Record<string, unknown>): DetailSection[] {
  const templateSections = (archive.template_sections || []) as string[];
  const templatePayload = (archive.template_payload || {}) as Record<string, unknown>;

  if (!templateSections.length) {
    // Legacy fallback
    const result: DetailSection[] = [];
    const fallbacks = [
      { key: "entity_role", label: "故事定位" },
      { key: "core_drive", label: "核心动机" },
      { key: "surface_mask", label: "表层伪装" },
      { key: "hidden_tension", label: "隐藏张力" },
      { key: "relationship_summary", label: "关系摘要" },
    ];
    for (const f of fallbacks) {
      const raw = archive[f.key];
      if (raw) {
        result.push({ key: f.key, label: f.label, variant: "text", text: String(raw) });
      }
    }
    return result;
  }

  const sections: DetailSection[] = [];
  for (const section of templateSections) {
    if (section === "agent_profile") {
      const profileData = templatePayload[section];
      if (profileData && typeof profileData === "object") {
        sections.push(...buildProfileGroups(profileData as Record<string, unknown>));
      }
      continue;
    }
    const value = templatePayload[section];
    const label = SECTION_LABELS[section] || section;
    if (typeof value === "string") {
      sections.push({ key: section, label, variant: "text", text: value || "暂无" });
    } else if (Array.isArray(value)) {
      const items = value.map(normalizeScalar).filter(Boolean);
      if (items.length) {
        sections.push({
          key: section,
          label,
          variant: "items",
          items: items.map((v) => ({ label: v, value: v })),
        });
      }
    } else if (value && typeof value === "object") {
      const entries = Object.entries(value)
        .filter(([k]) => !HIDDEN_FIELDS.has(k))
        .map(([k, v]) => ({ label: FIELD_LABELS[k] || k, value: formatEntryValue(v) }))
        .filter((e) => e.value);
      if (entries.length) {
        sections.push({ key: section, label, variant: "entries", entries });
      }
    }
  }
  return sections;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function ArchiveDetailView({ archiveId }: { archiveId: string }) {
  const detailQuery = useQuery({
    queryKey: ["archiveDetail", archiveId],
    queryFn: () => getArchiveLibraryDetail(archiveId),
    enabled: !!archiveId,
  });

  const archive = ((detailQuery.data as ApiResponse | undefined)?.data || null) as Record<string, unknown> | null;

  const sections = React.useMemo(
    () => (archive ? buildArchiveDetailSections(archive) : []),
    [archive],
  );

  const [expandedMap, setExpandedMap] = React.useState<Record<string, boolean>>({});

  React.useEffect(() => {
    const initial: Record<string, boolean> = {};
    for (const s of sections) {
      if (s.variant === "collapsible" && !(s.key in expandedMap)) {
        initial[s.key] = s.defaultExpanded ?? false;
      }
    }
    if (Object.keys(initial).length > 0) {
      setExpandedMap((prev) => ({ ...prev, ...initial }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sections]);

  if (detailQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-32" />
        <Separator />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (!archive) {
    return (
      <div className="flex min-h-[160px] items-center justify-center text-sm text-muted-foreground">
        档案详情加载失败
      </div>
    );
  }

  const entityType = String(archive.entity_type || "");
  const typeLabel = ENTITY_TYPE_LABELS[entityType.toLowerCase()] || entityType;
  const tierLabel = TIER_LABELS[String(archive.importance_tier || "").toLowerCase()] || String(archive.importance_tier || "");

  return (
    <div className="flex flex-col gap-2">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1.5">
          <h3 className="text-lg font-semibold">{String(archive.entity_name || "")}</h3>
          <div className="flex flex-wrap items-center gap-1.5">
            {typeLabel && <Badge variant="secondary" className="text-[11px]">{typeLabel}</Badge>}
            {tierLabel && <Badge variant="outline" className="text-[11px]">{tierLabel}</Badge>}
            <span className="text-xs text-muted-foreground">
              {String(archive.project_name || archive.project_id || "")}
            </span>
          </div>
        </div>
      </div>

      <Separator />

      {/* Sections */}
      <div className="flex flex-col">
        {sections.map((section) => {
          if (section.variant === "text") {
            return (
              <div key={section.key} className="border-b border-border/40 py-2 last:border-b-0">
                <h4 className="mb-1 text-[13px] font-semibold text-primary">{section.label}</h4>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{section.text}</p>
              </div>
            );
          }

          if (section.variant === "entries") {
            return (
              <div key={section.key} className="border-b border-border/40 py-2 last:border-b-0">
                <h4 className="mb-1 text-[13px] font-semibold text-primary">{section.label}</h4>
                <dl className="flex flex-col gap-1.5">
                  {section.entries?.map((entry) => (
                    <div key={entry.label} className="flex flex-col gap-0.5">
                      <dt className="text-xs text-muted-foreground">{entry.label}</dt>
                      <dd className="text-sm leading-relaxed">{entry.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            );
          }

          if (section.variant === "collapsible") {
            const isOpen = expandedMap[section.key] ?? false;
            return (
              <div key={section.key} className="border-b border-border/40 last:border-b-0">
                <button
                  type="button"
                  className="flex w-full items-center justify-between py-3 transition-colors hover:bg-muted/30"
                  onClick={() =>
                    setExpandedMap((prev) => ({ ...prev, [section.key]: !isOpen }))
                  }
                >
                  <h4 className="text-[13px] font-semibold text-primary">{section.label}</h4>
                  <ChevronDown
                    className={cn(
                      "h-3 w-3 text-muted-foreground transition-transform",
                      isOpen && "rotate-180",
                    )}
                  />
                </button>
                {isOpen && Array.isArray(section.items) && (
                  <div className="flex flex-col gap-0.5 pb-3">
                    {section.items.map((entry, ei) => (
                      <div key={ei} className="flex flex-col gap-0.5 border-t border-border/10 py-1.5">
                        <dt className="text-[11.5px] text-muted-foreground">{entry.label}</dt>
                        <dd className="break-words text-[13.5px] leading-relaxed">
                          {Array.isArray(entry.value) ? (
                            <div className="flex flex-wrap gap-1">
                              {entry.value.map((tag, ti) => (
                                <span key={ti} className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-xs">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          ) : (
                            entry.value
                          )}
                        </dd>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          }

          // items variant
          return (
            <div key={section.key} className="border-b border-border/40 py-2 last:border-b-0">
              <h4 className="mb-1 text-[13px] font-semibold text-primary">{section.label}</h4>
              <div className="flex flex-wrap gap-1.5">
                {Array.isArray(section.items) &&
                  section.items.map((item, ii) => (
                    <span key={ii} className="rounded-full bg-primary/6 px-2.5 py-1 text-[13px] text-primary">
                      {typeof item === "string" ? item : item.label}
                    </span>
                  ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
