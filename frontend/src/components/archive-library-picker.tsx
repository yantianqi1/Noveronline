import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ChevronRight, ChevronDown, X } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ArchiveEntry } from "@/types/archive";
import type { ApiResponse } from "@/api/http";
import {
  getArchiveLibraryDetail,
  listArchiveLibrary,
} from "@/api/assets";
import { listProjects } from "@/api/project";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

/* ---------- constants ---------- */

const ENTITY_TYPE_OPTIONS = [
  { label: "角色", value: "character" },
  { label: "组织", value: "organization" },
  { label: "关系", value: "relationship" },
] as const;

const IMPORTANCE_TIER_OPTIONS = [
  { label: "主角", value: "protagonist" },
  { label: "主要", value: "major" },
  { label: "次要", value: "supporting" },
  { label: "配角", value: "minor" },
] as const;

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

/* ---------- detail section builder (ported from archive-library/page.tsx) ---------- */

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

const PROFILE_GROUP_CONFIG: Array<{
  key: string;
  label: string;
  defaultExpanded: boolean;
  fields: Record<string, string>;
}> = [
  {
    key: "basic_info",
    label: "基本信息",
    defaultExpanded: true,
    fields: {
      name: "名称",
      aliases: "别名",
      identity: "身份",
      status: "状态",
    },
  },
  {
    key: "personality",
    label: "性格画像",
    defaultExpanded: true,
    fields: {
      core_traits: "核心特质",
      values: "价值观",
      fears: "恐惧与弱点",
      decision_pattern: "决策模式",
    },
  },
  {
    key: "motivation",
    label: "动机目标",
    defaultExpanded: true,
    fields: {
      ultimate_goal: "终极目标",
      current_objective: "当前目标",
      internal_conflict: "内心矛盾",
    },
  },
  {
    key: "speech",
    label: "语言风格",
    defaultExpanded: false,
    fields: {
      style: "表达风格",
      verbal_habits: "口头禅",
      tone_range: "语气特征",
      example_quotes: "经典语录",
    },
  },
  {
    key: "capabilities",
    label: "能力特长",
    defaultExpanded: false,
    fields: {
      skills: "技能",
      limitations: "局限性",
      resources: "掌握资源",
    },
  },
  {
    key: "knowledge_boundary",
    label: "知识边界",
    defaultExpanded: false,
    fields: {
      knows: "已知信息",
      does_not_know: "未知信息",
      believes_wrongly: "错误认知",
    },
  },
  {
    key: "relationships",
    label: "人际关系",
    defaultExpanded: false,
    fields: {},
  },
];

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
    return Object.entries(value as Record<string, unknown>)
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
      const items = (groupData as Array<Record<string, string> | string>)
        .map((rel) => {
          if (typeof rel === "string") return { label: "关系", value: rel };
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

function buildArchiveDetailSections(archive: ArchiveEntry): DetailSection[] {
  const templateSections = (archive.template_sections || []) as string[];
  const templatePayload = (archive.template_payload || {}) as Record<string, unknown>;

  if (!templateSections.length) {
    const result: DetailSection[] = [];
    const fallbacks = [
      { key: "entity_role", label: "故事定位" },
      { key: "core_drive", label: "核心动机" },
      { key: "surface_mask", label: "表层伪装" },
      { key: "hidden_tension", label: "隐藏张力" },
      { key: "relationship_summary", label: "关系摘要" },
    ];
    for (const f of fallbacks) {
      const raw = (archive as Record<string, unknown>)[f.key];
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
      const entries = Object.entries(value as Record<string, unknown>)
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

/* ---------- types ---------- */

export interface ArchiveLibraryPickerProps {
  /** Controlled project filter — empty string means "all projects". */
  projectId?: string;
  onProjectIdChange?: (value: string) => void;
  selectedIds?: string[];
  onSelect?: (archive: ArchiveEntry) => void;
  multiSelect?: boolean;
  className?: string;
}

/* ---------- sub-components ---------- */

function GridItem({
  item,
  expanded,
  selected,
  onExpand,
  onToggle,
}: {
  item: ArchiveEntry;
  expanded: boolean;
  selected: boolean;
  onExpand: () => void;
  onToggle: () => void;
}) {
  const entityType = String(item.entity_type || "");
  const typeLabel = ENTITY_TYPE_LABELS[entityType.toLowerCase()] || entityType;
  const tierLabel =
    TIER_LABELS[String(item.importance_tier || "").toLowerCase()] ||
    String(item.importance_tier || "");
  const roleText = String(item.entity_role || "");
  const driveText = String(item.core_drive || "");
  const projectText = String(item.project_name || item.project_id || "");

  return (
    <Card
      className={cn(
        "flex cursor-pointer flex-col gap-1.5 border-l-[3px] border-l-transparent px-3 py-2.5 transition-all hover:bg-muted/40",
        selected && "border-l-primary bg-primary/5",
        expanded && "border-l-primary bg-muted/40",
      )}
      onClick={onToggle}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-start gap-1.5">
          <h4 className="line-clamp-2 min-w-0 flex-1 text-sm font-semibold leading-snug">
            {String(item.entity_name || "")}
          </h4>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge variant="secondary" className="text-[10px]">
            {typeLabel}
          </Badge>
          {tierLabel && (
            <Badge variant="outline" className="text-[10px]">
              {tierLabel}
            </Badge>
          )}
        </div>
      </div>

      {/* Body: role / drive */}
      {(roleText || driveText) && (
        <div className="flex flex-col gap-0.5">
          {roleText && (
            <p className="line-clamp-1 text-xs text-muted-foreground">{roleText}</p>
          )}
          {driveText && (
            <p className="line-clamp-2 text-xs text-muted-foreground">{driveText}</p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="mt-0.5 flex items-center justify-between gap-2 border-t border-border/40 pt-1.5">
        <span className="truncate text-[11px] text-muted-foreground">{projectText}</span>
        <button
          type="button"
          className={cn(
            "inline-flex shrink-0 items-center gap-0.5 rounded-full border px-2 py-0.5 text-xs transition-colors",
            expanded
              ? "border-primary bg-primary/10 text-primary"
              : "border-border/60 text-muted-foreground hover:border-primary hover:text-primary",
          )}
          onClick={(e) => {
            e.stopPropagation();
            onExpand();
          }}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          {expanded ? "收起" : "详情"}
        </button>
      </div>
    </Card>
  );
}

function DetailCard({
  archive,
  selected,
  onToggle,
}: {
  archive: ArchiveEntry | null;
  selected: boolean;
  onToggle: () => void;
}) {
  const [expandedMap, setExpandedMap] = React.useState<Record<string, boolean>>({});

  const sections = React.useMemo(
    () => (archive ? buildArchiveDetailSections(archive) : []),
    [archive],
  );

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

  if (!archive) {
    return (
      <div className="flex min-h-[280px] items-center justify-center text-sm text-muted-foreground">
        点击左侧列表中的任意档案卡片查看详情
      </div>
    );
  }

  const entityType = String(archive.entity_type || "");
  const typeLabel = ENTITY_TYPE_LABELS[entityType.toLowerCase()] || entityType;
  const tierLabel =
    TIER_LABELS[String(archive.importance_tier || "").toLowerCase()] ||
    String(archive.importance_tier || "");

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h3 className="break-words text-[15px] font-semibold leading-snug">
            {String(archive.entity_name || "")}
          </h3>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary" className="text-[10px]">
              {typeLabel}
            </Badge>
            {tierLabel && (
              <Badge variant="outline" className="text-[10px]">
                {tierLabel}
              </Badge>
            )}
            <span className="truncate text-[11px] text-muted-foreground">
              {String(archive.project_name || archive.project_id || "")}
            </span>
          </div>
        </div>
        <Button
          size="sm"
          variant={selected ? "outline" : "default"}
          className="shrink-0 h-7 px-2.5 text-xs"
          onClick={onToggle}
        >
          {selected ? "移出" : "加入"}
        </Button>
      </div>

      <Separator />

      <div className="flex flex-col">
        {sections.map((section) => {
          if (section.variant === "text") {
            return (
              <div
                key={section.key}
                className="border-b border-border/40 py-2 last:border-b-0"
              >
                <h4 className="mb-1 text-[13px] font-semibold text-primary">
                  {section.label}
                </h4>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {section.text}
                </p>
              </div>
            );
          }

          if (section.variant === "entries") {
            return (
              <div
                key={section.key}
                className="border-b border-border/40 py-2 last:border-b-0"
              >
                <h4 className="mb-1 text-[13px] font-semibold text-primary">
                  {section.label}
                </h4>
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
              <div
                key={section.key}
                className="border-b border-border/40 last:border-b-0"
              >
                <button
                  type="button"
                  className="flex w-full items-center justify-between py-3 transition-colors hover:bg-muted/30"
                  onClick={() =>
                    setExpandedMap((prev) => ({
                      ...prev,
                      [section.key]: !isOpen,
                    }))
                  }
                >
                  <h4 className="text-[13px] font-semibold text-primary">
                    {section.label}
                  </h4>
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
                      <div
                        key={ei}
                        className="flex flex-col gap-0.5 border-t border-border/10 py-1.5"
                      >
                        <dt className="text-[11.5px] text-muted-foreground">
                          {entry.label}
                        </dt>
                        <dd className="break-words text-[13.5px] leading-relaxed">
                          {Array.isArray(entry.value) ? (
                            <div className="flex flex-wrap gap-1">
                              {entry.value.map((tag, ti) => (
                                <span
                                  key={ti}
                                  className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-xs"
                                >
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
            <div
              key={section.key}
              className="border-b border-border/40 py-2 last:border-b-0"
            >
              <h4 className="mb-1 text-[13px] font-semibold text-primary">
                {section.label}
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {Array.isArray(section.items) &&
                  section.items.map((item, ii) => (
                    <span
                      key={ii}
                      className="rounded-full bg-primary/10 px-2.5 py-1 text-[13px] text-primary"
                    >
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

/* ---------- main component ---------- */

export function ArchiveLibraryPicker({
  projectId,
  onProjectIdChange,
  onSelect,
  selectedIds = [],
  className,
}: ArchiveLibraryPickerProps) {
  const [searchText, setSearchText] = React.useState("");
  const [debouncedSearch, setDebouncedSearch] = React.useState("");
  const [agentKind, setAgentKind] = React.useState<string>("");
  const [importanceTier, setImportanceTier] = React.useState<string>("");
  const [expandedArchiveId, setExpandedArchiveId] = React.useState<string>("");

  const selectedIdSet = React.useMemo(() => new Set(selectedIds), [selectedIds]);

  /* debounce search text */
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchText.trim()), 200);
    return () => clearTimeout(t);
  }, [searchText]);

  /* projects dropdown */
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(100),
  });
  const projects = ((projectsQuery.data as ApiResponse | undefined)?.data || []) as Array<{
    project_id: string;
    name?: string;
  }>;

  /* archive list */
  const archiveListQuery = useQuery({
    queryKey: [
      "archiveLibrary",
      debouncedSearch,
      projectId || "",
      agentKind,
      importanceTier,
    ],
    queryFn: () =>
      listArchiveLibrary({
        q: debouncedSearch,
        projectId: projectId || "",
        agentKind: agentKind || "",
        importanceTier: importanceTier || "",
        limit: 60,
      }),
  });

  const archivePayload = (archiveListQuery.data as ApiResponse | undefined)?.data as
    | { items?: ArchiveEntry[]; total?: number }
    | undefined;
  const items = archivePayload?.items || [];
  const total = archivePayload?.total || 0;

  /* keep expanded archive valid when list changes */
  React.useEffect(() => {
    if (!expandedArchiveId) return;
    const stillPresent = items.some((i) => String(i.archive_id) === expandedArchiveId);
    if (!stillPresent) setExpandedArchiveId("");
  }, [items, expandedArchiveId]);

  /* detail */
  const detailQuery = useQuery({
    queryKey: ["archiveDetail", expandedArchiveId],
    queryFn: () => getArchiveLibraryDetail(expandedArchiveId),
    enabled: !!expandedArchiveId,
  });
  const activeDetail = ((detailQuery.data as ApiResponse | undefined)?.data || null) as
    | ArchiveEntry
    | null;

  /* handlers */
  function handleToggleSelect(archive: ArchiveEntry | null) {
    if (!archive || !onSelect) return;
    onSelect(archive);
  }

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col gap-3 overflow-hidden",
        className,
      )}
    >
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border/60 bg-card p-2">
        <div className="relative min-w-0 flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="搜索角色、组织、动机、关系..."
            className="pl-8"
          />
          {searchText && (
            <button
              type="button"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setSearchText("")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {onProjectIdChange && (
            <Select
              value={projectId ? projectId : null}
              onValueChange={(v) => onProjectIdChange(v || "")}
            >
              <SelectTrigger className="min-w-[120px]">
                <SelectValue placeholder="全部项目">
                  {(value: unknown) => {
                    const id = typeof value === "string" ? value : "";
                    if (!id) return "全部项目";
                    const found = projects.find((p) => p.project_id === id);
                    const name = (found?.name || "").trim();
                    return name || "未命名项目";
                  }}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.project_id} value={p.project_id}>
                    {(p.name || "").trim() || "未命名项目"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Select
            value={agentKind || null}
            onValueChange={(v) => setAgentKind(v || "")}
          >
            <SelectTrigger className="min-w-[100px]">
              <SelectValue placeholder="全部类型">
                {(value: unknown) => {
                  const v = typeof value === "string" ? value : "";
                  if (!v) return "全部类型";
                  const opt = ENTITY_TYPE_OPTIONS.find((o) => o.value === v);
                  return opt?.label || v;
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {ENTITY_TYPE_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={importanceTier || null}
            onValueChange={(v) => setImportanceTier(v || "")}
          >
            <SelectTrigger className="min-w-[100px]">
              <SelectValue placeholder="全部位阶">
                {(value: unknown) => {
                  const v = typeof value === "string" ? value : "";
                  if (!v) return "全部位阶";
                  const opt = IMPORTANCE_TIER_OPTIONS.find((o) => o.value === v);
                  return opt?.label || v;
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {IMPORTANCE_TIER_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {(projectId || agentKind || importanceTier) && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-9 px-2 text-xs"
              onClick={() => {
                if (onProjectIdChange) onProjectIdChange("");
                setAgentKind("");
                setImportanceTier("");
              }}
            >
              <X className="mr-1 h-3 w-3" />
              清除
            </Button>
          )}
        </div>
      </div>

      {/* Summary bar */}
      <div className="flex items-center justify-between px-1 text-[13px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>
            {archiveListQuery.isLoading ? "载入中..." : `找到 ${total} 条档案`}
          </span>
          {selectedIds.length > 0 && (
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
              {selectedIds.length} 已选
            </span>
          )}
        </div>
      </div>

      {/* Error */}
      {archiveListQuery.isError && (
        <p className="px-2 text-[13px] text-destructive">
          {(archiveListQuery.error as Error)?.message || "档案读取失败"}
        </p>
      )}

      {/* Body: responsive grid list with inline-expanded detail */}
      <ScrollArea className="flex-1 min-h-0 min-w-0 rounded-xl border border-border/60 bg-card shadow-sm">
        <div
          className="grid gap-2 p-2"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}
        >
          {archiveListQuery.isLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))
          ) : items.length === 0 ? (
            <div className="col-span-full rounded-lg border border-dashed border-border/60 bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
              <h4 className="mb-1 text-[15px] font-medium">未找到符合条件的档案</h4>
              <p>尝试调整搜索关键词或筛选条件</p>
            </div>
          ) : (
            items.map((item) => {
              const archiveId = String(item.archive_id);
              const expanded = expandedArchiveId === archiveId;
              const inlineDetail =
                expanded && activeDetail?.archive_id === archiveId ? activeDetail : item;
              return (
                <React.Fragment key={archiveId}>
                  <GridItem
                    item={item}
                    expanded={expanded}
                    selected={selectedIdSet.has(archiveId)}
                    onExpand={() =>
                      setExpandedArchiveId((curr) => (curr === archiveId ? "" : archiveId))
                    }
                    onToggle={() => handleToggleSelect(item)}
                  />
                  {expanded && (
                    <div className="col-span-full rounded-lg border border-primary/25 bg-primary/2 p-3">
                      {detailQuery.isLoading && activeDetail?.archive_id !== archiveId ? (
                        <div className="space-y-2">
                          <Skeleton className="h-5 w-40" />
                          <Skeleton className="h-3 w-28" />
                          <Skeleton className="h-16 w-full" />
                        </div>
                      ) : (
                        <DetailCard
                          archive={inlineDetail}
                          selected={selectedIdSet.has(archiveId)}
                          onToggle={() => handleToggleSelect(inlineDetail)}
                        />
                      )}
                    </div>
                  )}
                </React.Fragment>
              );
            })
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
