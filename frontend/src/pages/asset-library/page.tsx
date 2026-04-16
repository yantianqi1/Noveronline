import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  X,
  RefreshCw,
  Plus,
  Trash2,
  FileText,
  ChevronDown,
  ChevronRight,
  Loader2,
  Package,
  BookOpen,
  Network,
  PenLine,
  Globe2,
  Sprout,
  ExternalLink,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ApiResponse } from "@/api/http";
import {
  listAssets,
  listUnifiedAssets,
  getUnifiedFacets,
  searchGlobalAssets,
  createAsset,
  updateAsset,
  deleteAsset,
  startAssetIngestion,
  getAssetIngestionStatus,
  reindexUnifiedAssets,
} from "@/api/assets";
import { listProjects } from "@/api/project";
import { useNotification } from "@/hooks/use-notification";

import { ArchiveDetailView } from "@/components/archive-detail-view";
import { ArchiveMemoryPanel } from "@/components/archive-memory-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

interface SourceMeta {
  key: string;
  label: string;
  icon: React.ReactNode;
  color: string;
}

const SOURCES: SourceMeta[] = [
  { key: "assets", label: "资产库", icon: <Package className="h-3 w-3" />, color: "bg-indigo-500" },
  { key: "archive", label: "档案库", icon: <BookOpen className="h-3 w-3" />, color: "bg-emerald-500" },
  { key: "story_graph", label: "故事图谱", icon: <Network className="h-3 w-3" />, color: "bg-amber-500" },
  { key: "novel_db", label: "写作工坊", icon: <PenLine className="h-3 w-3" />, color: "bg-pink-500" },
  { key: "worldline", label: "世界线", icon: <Globe2 className="h-3 w-3" />, color: "bg-blue-500" },
  { key: "seed", label: "总览种子", icon: <Sprout className="h-3 w-3" />, color: "bg-lime-500" },
];

function getSourceMeta(key: string): SourceMeta {
  return SOURCES.find((s) => s.key === key) || {
    key,
    label: key,
    icon: <FileText className="h-3 w-3" />,
    color: "bg-gray-500",
  };
}

const ENTITY_TYPE_LABELS: Record<string, string> = {
  writing_style: "文风",
  author_style: "作家风格",
  worldview: "世界观",
  character_archetype: "角色原型",
  prompt_template: "提示词模板",
  manuscript_block: "稿件块",
  note: "笔记",
  world_rule: "世界规则",
  plot_template: "情节模板",
  character: "角色",
  organization: "组织",
  faction: "势力",
  relationship: "关系",
  entity: "实体",
  plot_thread: "情节线索",
  scene: "场景",
  seed_character: "种子角色",
  seed_world_rule: "种子世界规则",
  seed_plot_thread: "种子线索",
  seed_agent_profile: "Agent 档案",
  worldline_session: "世界线会话",
};

const IMPORTANCE_LABELS: Record<string, string> = {
  protagonist: "主角",
  major: "重要",
  supporting: "次要",
  minor: "群像",
};

const INGESTION_HINT_OPTIONS = [
  { label: "自动判定", value: "" },
  { label: "文风", value: "writing_style" },
  { label: "世界观", value: "worldview" },
  { label: "角色原型", value: "character_archetype" },
  { label: "创作规则 / 世界规则", value: "world_rule" },
  { label: "桥段 / 情节模板", value: "plot_template" },
  { label: "提示词模板", value: "prompt_template" },
  { label: "普通笔记", value: "note" },
] as const;

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface UnifiedItem {
  source: string;
  source_ref?: string;
  entity_type?: string;
  title?: string;
  name?: string;
  summary?: string;
  snippet?: string;
  importance?: string;
  scope?: string;
  project_id?: string;
  updated_at?: string;
  origin_link?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

interface FacetSource {
  key: string;
  count: number;
}

interface FacetEntityType {
  key: string;
  count: number;
}

interface IngestionForm {
  scope: string;
  hint_type: string;
  raw_text: string;
}

interface IngestionTaskState {
  task_id: string;
  status: string;
  progress: number;
  message?: string;
  error?: string;
  result?: { title?: string };
}

/* ------------------------------------------------------------------ */
/*  Asset Card                                                         */
/* ------------------------------------------------------------------ */

function AssetCard({
  item,
  onClick,
}: {
  item: UnifiedItem;
  onClick: () => void;
}) {
  const source = getSourceMeta(item.source);
  const typeLabel = ENTITY_TYPE_LABELS[item.entity_type || ""] || item.entity_type || "--";
  const importanceLabel = item.importance ? (IMPORTANCE_LABELS[item.importance] || item.importance) : null;

  return (
    <Card
      className="flex cursor-pointer flex-col gap-1.5 p-3 transition-all hover:border-primary/30 hover:shadow-md"
      onClick={onClick}
    >
      {/* Header: source badge + type + importance */}
      <div className="flex items-center gap-2 text-[11px]">
        <span
          className={cn(
            "inline-flex h-[22px] w-[22px] items-center justify-center rounded text-white",
            source.color,
          )}
          title={source.label}
        >
          {source.icon}
        </span>
        <span className="text-muted-foreground">{typeLabel}</span>
        {importanceLabel && (
          <Badge variant="secondary" className="ml-auto text-[10px]">
            {importanceLabel}
          </Badge>
        )}
      </div>

      {/* Title */}
      <h4 className="text-sm font-medium leading-snug">{item.title || item.name || "(无标题)"}</h4>

      {/* Summary */}
      {(item.snippet || item.summary) && (
        <p
          className="line-clamp-3 text-xs leading-relaxed text-muted-foreground"
          dangerouslySetInnerHTML={{ __html: item.snippet || item.summary || "" }}
        />
      )}

      {/* Footer */}
      <div className="mt-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span>{item.updated_at || ""}</span>
        {item.scope === "global" && (
          <>
            <span>--</span>
            <span>全局</span>
          </>
        )}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail Sheet                                                       */
/* ------------------------------------------------------------------ */

function DetailSheet({
  item,
  open,
  onClose,
}: {
  item: UnifiedItem | null;
  open: boolean;
  onClose: () => void;
}) {
  const [payloadExpanded, setPayloadExpanded] = React.useState(false);

  if (!item) return null;

  const source = getSourceMeta(item.source);

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <SheetContent side="right" className="w-[560px] max-w-[90vw]">
        <SheetHeader>
          <SheetTitle>{item.title || item.name || "(无标题)"}</SheetTitle>
          <SheetDescription>资产详情</SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 px-4 pb-4">
          <div className="flex flex-col gap-3">
            {/* Metadata */}
            <div className="flex flex-col gap-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium text-muted-foreground">来源：</span>
                <span className="inline-flex items-center gap-1">
                  <span className={cn("inline-flex h-5 w-5 items-center justify-center rounded text-white text-[10px]", source.color)}>
                    {source.icon}
                  </span>
                  {source.label} ({item.source})
                </span>
              </div>

              <div>
                <span className="font-medium text-muted-foreground">实体类型：</span>
                <span>{ENTITY_TYPE_LABELS[item.entity_type || ""] || item.entity_type || "--"}</span>
              </div>

              {item.project_id && (
                <div>
                  <span className="font-medium text-muted-foreground">项目：</span>
                  <span>{String(item.project_id)}</span>
                </div>
              )}

              {item.summary && (
                <div>
                  <span className="font-medium text-muted-foreground">摘要：</span>
                  <span>{item.summary}</span>
                </div>
              )}

              <div>
                <span className="font-medium text-muted-foreground">更新时间：</span>
                <span>{item.updated_at || "--"}</span>
              </div>

              {item.origin_link && (
                <div className="flex items-center gap-1">
                  <span className="font-medium text-muted-foreground">跳转：</span>
                  <a href={`#${item.origin_link}`} className="inline-flex items-center gap-0.5 text-primary hover:underline">
                    {item.origin_link}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </div>

            <Separator />

            {/* Source-specific deep sections */}
            {item.source === "archive" && item.source_ref && (
              <>
                <ArchiveDetailView archiveId={item.source_ref} />
                <Separator />
                <ArchiveMemoryPanel archiveId={item.source_ref} />
                <Separator />
              </>
            )}

            {/* Payload viewer */}
            <div>
              <button
                type="button"
                className="flex w-full items-center justify-between py-1 text-sm font-medium"
                onClick={() => setPayloadExpanded(!payloadExpanded)}
              >
                <span>完整数据 (payload)</span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-muted-foreground transition-transform",
                    payloadExpanded && "rotate-180",
                  )}
                />
              </button>
              {payloadExpanded && (
                <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-muted/50 p-3 text-[11px] leading-relaxed">
                  {JSON.stringify(item.payload || {}, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ */
/*  Ingestion Sheet                                                    */
/* ------------------------------------------------------------------ */

function IngestionSheet({
  open,
  onClose,
  projectId,
  onComplete,
}: {
  open: boolean;
  onClose: () => void;
  projectId: string;
  onComplete: () => void;
}) {
  const { notifySuccess, notifyError } = useNotification();
  const [form, setForm] = React.useState<IngestionForm>({
    scope: projectId ? "project" : "global",
    hint_type: "",
    raw_text: "",
  });
  const [taskState, setTaskState] = React.useState<IngestionTaskState | null>(null);
  const [running, setRunning] = React.useState(false);
  const pollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  React.useEffect(() => {
    if (open) {
      setForm({
        scope: projectId ? "project" : "global",
        hint_type: "",
        raw_text: "",
      });
      setTaskState(null);
      setRunning(false);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [open, projectId]);

  async function submitIngestion() {
    if (!form.raw_text.trim()) {
      notifyError("请粘贴原始素材");
      return;
    }
    if (form.scope === "project" && !projectId) {
      notifyError("项目范围必须先选择项目");
      return;
    }
    setRunning(true);
    try {
      const res = await startAssetIngestion({
        raw_text: form.raw_text,
        hint_type: form.hint_type || undefined,
        scope: form.scope,
        project_id: form.scope === "project" ? projectId : undefined,
      });
      const taskId = (res.data as { task_id: string })?.task_id;
      setTaskState({ task_id: taskId, status: "RUNNING", progress: 0 });
      pollIngestion(taskId);
    } catch (err) {
      notifyError((err as Error).message || "入库失败");
      setRunning(false);
    }
  }

  function pollIngestion(taskId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await getAssetIngestionStatus(taskId);
        const data = res.data as IngestionTaskState;
        setTaskState(data);
        const status = String(data.status || "").toLowerCase();
        if (status === "completed" || status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setRunning(false);
          if (status === "completed") {
            notifySuccess(`入库完成：${data.result?.title || ""}`);
            onComplete();
            onClose();
          } else {
            notifyError(`入库失败：${data.error || "(未知错误)"}`);
          }
        }
      } catch (err) {
        console.error("Poll ingestion error:", err);
      }
    }, 1500);
  }

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <SheetContent side="right" className="w-[560px] max-w-[90vw]">
        <SheetHeader>
          <SheetTitle>入库新资产</SheetTitle>
          <SheetDescription>
            把原始素材粘贴进来，「入库 Agent」会自动识别类型、抽取结构化字段、生成摘要与标签后写入资产库。
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4">
          {/* Scope */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">范围</label>
            <Select
              value={form.scope}
              onValueChange={(v) => setForm((prev) => ({ ...prev, scope: v || "global" }))}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择范围" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="global">全局</SelectItem>
                <SelectItem value="project">当前项目</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Hint type */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              类型提示（可选，留空让 Agent 自动判定）
            </label>
            <Select
              value={form.hint_type}
              onValueChange={(v) => setForm((prev) => ({ ...prev, hint_type: v || "" }))}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="自动判定" />
              </SelectTrigger>
              <SelectContent>
                {INGESTION_HINT_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value || "__auto"} value={opt.value || "__auto__"}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Raw text */}
          <div className="flex flex-1 flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground">原始素材</label>
            <Textarea
              value={form.raw_text}
              onChange={(e) => setForm((prev) => ({ ...prev, raw_text: e.target.value }))}
              rows={14}
              placeholder="贴入角色设定 / 世界观片段 / 文风范文 / 创作守则..."
              className="min-h-[200px] flex-1 resize-y"
            />
          </div>

          {/* Status + submit */}
          <div className="flex items-center justify-between gap-3">
            {taskState && (
              <span className="flex-1 text-xs text-muted-foreground">
                任务 {(taskState.task_id || "").slice(0, 8)} --{" "}
                {taskState.status} -- {taskState.progress || 0}% --{" "}
                {taskState.message || ""}
                {taskState.error && (
                  <span className="text-destructive"> -- {taskState.error}</span>
                )}
              </span>
            )}
            <Button
              disabled={running}
              onClick={submitIngestion}
            >
              {running ? (
                <>
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  Agent 工作中...
                </>
              ) : (
                <>
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  开始入库
                </>
              )}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/* ------------------------------------------------------------------ */
/*  Facet Sidebar                                                      */
/* ------------------------------------------------------------------ */

function FacetSidebar({
  projects,
  projectId,
  onProjectChange,
  facetSources,
  selectedSources,
  onSourceToggle,
  facetEntityTypes,
  selectedTypes,
  onTypeToggle,
}: {
  projects: Array<{ project_id: string; name?: string }>;
  projectId: string;
  onProjectChange: (id: string) => void;
  facetSources: Record<string, number>;
  selectedSources: string[];
  onSourceToggle: (key: string) => void;
  facetEntityTypes: FacetEntityType[];
  selectedTypes: string[];
  onTypeToggle: (key: string) => void;
}) {
  return (
    <aside className="flex flex-col gap-4 rounded-xl border border-border/60 bg-card p-4">
      {/* Project scope */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">项目范围</h3>
        <Select value={projectId || ""} onValueChange={(v) => onProjectChange(v || "")}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="（全局范围 / 不选项目）" />
          </SelectTrigger>
          <SelectContent>
            {projects.map((p) => (
              <SelectItem key={p.project_id} value={p.project_id}>
                {p.name || p.project_id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Data sources */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">数据源</h3>
        <div className="flex flex-col gap-1">
          {SOURCES.map((s) => {
            const checked = selectedSources.includes(s.key);
            return (
              <label
                key={s.key}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted/40"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onSourceToggle(s.key)}
                />
                <span className={cn("inline-flex h-5 w-5 items-center justify-center rounded text-white", s.color)}>
                  {s.icon}
                </span>
                <span className="flex-1">{s.label}</span>
                {facetSources[s.key] !== undefined && (
                  <span className="text-[11px] text-muted-foreground">{facetSources[s.key]}</span>
                )}
              </label>
            );
          })}
        </div>
      </div>

      {/* Entity types */}
      {facetEntityTypes.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">实体类型</h3>
          <ScrollArea className="max-h-[260px]">
            <div className="flex flex-col gap-1">
              {facetEntityTypes.map((t) => {
                const checked = selectedTypes.includes(t.key);
                return (
                  <label
                    key={t.key}
                    className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted/40"
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => onTypeToggle(t.key)}
                    />
                    <span className="flex-1">{ENTITY_TYPE_LABELS[t.key] || t.key}</span>
                    <span className="text-[11px] text-muted-foreground">{t.count}</span>
                  </label>
                );
              })}
            </div>
          </ScrollArea>
        </div>
      )}
    </aside>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function AssetLibraryPage() {
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotification();

  /* -- state -- */
  const [searchQuery, setSearchQuery] = React.useState("");
  const [debouncedSearch, setDebouncedSearch] = React.useState("");
  const [searchActive, setSearchActive] = React.useState(false);
  const [projectId, setProjectId] = React.useState("");
  const [selectedSources, setSelectedSources] = React.useState<string[]>(
    SOURCES.map((s) => s.key),
  );
  const [selectedTypes, setSelectedTypes] = React.useState<string[]>([]);

  /* -- detail / ingestion drawers -- */
  const [detailItem, setDetailItem] = React.useState<UnifiedItem | null>(null);
  const [ingestionOpen, setIngestionOpen] = React.useState(false);

  /* -- debounce search -- */
  React.useEffect(() => {
    const q = searchQuery.trim();
    if (q.length > 0 && q.length < 2) return;
    const timer = setTimeout(() => {
      if (q.length >= 2) {
        setDebouncedSearch(q);
        setSearchActive(true);
      } else if (searchActive) {
        setDebouncedSearch("");
        setSearchActive(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery, searchActive]);

  /* -- projects query -- */
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(50),
  });
  const projects = ((projectsQuery.data as ApiResponse | undefined)?.data || []) as Array<{
    project_id: string;
    name?: string;
  }>;

  /* -- facets query -- */
  const facetsQuery = useQuery({
    queryKey: ["unifiedFacets", projectId],
    queryFn: () => getUnifiedFacets(projectId),
  });
  const facetsData = (facetsQuery.data as ApiResponse | undefined)?.data as {
    sources?: FacetSource[];
    entity_types?: FacetEntityType[];
  } | undefined;
  const facetSources = React.useMemo(() => {
    return Object.fromEntries(
      (facetsData?.sources || []).map((s) => [s.key, s.count]),
    );
  }, [facetsData]);
  const facetEntityTypes = facetsData?.entity_types || [];

  /* -- unified list query (normal browse) -- */
  const listQuery = useQuery({
    queryKey: ["unifiedAssets", projectId, selectedSources, selectedTypes],
    queryFn: () =>
      listUnifiedAssets({
        projectId,
        sources: selectedSources,
        entityTypes: selectedTypes,
        pageSize: 200,
      }),
    enabled: !searchActive,
  });

  /* -- search query -- */
  const searchResultsQuery = useQuery({
    queryKey: ["globalAssetSearch", debouncedSearch, projectId, selectedSources, selectedTypes],
    queryFn: () =>
      searchGlobalAssets({
        q: debouncedSearch,
        projectId,
        sources: selectedSources,
        entityTypes: selectedTypes,
        limit: 100,
      }),
    enabled: searchActive && debouncedSearch.length >= 2,
  });

  /* -- resolved items -- */
  const loading = searchActive ? searchResultsQuery.isLoading : listQuery.isLoading;
  const items: UnifiedItem[] = React.useMemo(() => {
    if (searchActive) {
      return ((searchResultsQuery.data as ApiResponse | undefined)?.data || []) as UnifiedItem[];
    }
    const listData = (listQuery.data as ApiResponse | undefined)?.data as {
      items?: UnifiedItem[];
      errors?: Array<{ source: string; error: string }>;
    } | undefined;
    return listData?.items || [];
  }, [searchActive, searchResultsQuery.data, listQuery.data]);

  const listErrors = React.useMemo(() => {
    if (searchActive) return [];
    const listData = (listQuery.data as ApiResponse | undefined)?.data as {
      errors?: Array<{ source: string; error: string }>;
    } | undefined;
    return listData?.errors || [];
  }, [searchActive, listQuery.data]);

  /* -- reindex mutation -- */
  const reindexMutation = useMutation({
    mutationFn: () => {
      if (!projectId) {
        return Promise.reject(new Error("请先选择项目"));
      }
      return reindexUnifiedAssets(projectId);
    },
    onSuccess: (res: ApiResponse) => {
      const indexed = (res.data as { indexed?: number } | undefined)?.indexed ?? 0;
      notifySuccess(`已索引 ${indexed} 条记录`);
      queryClient.invalidateQueries({ queryKey: ["unifiedAssets"] });
      queryClient.invalidateQueries({ queryKey: ["unifiedFacets"] });
    },
    onError: (err: Error) => notifyError(err.message || "重建失败"),
  });

  /* -- handlers -- */
  function handleSourceToggle(key: string) {
    setSelectedSources((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function handleTypeToggle(key: string) {
    setSelectedTypes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function clearSearch() {
    setSearchQuery("");
    setDebouncedSearch("");
    setSearchActive(false);
  }

  return (
    <div className="flex h-[calc(100vh-60px)] flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">资产库</h1>
          <p className="text-sm text-muted-foreground">
            统一查看本项目所有数据：种子档案、故事图谱、写作工坊、世界线、独立资产 ——
            一个入口、一个搜索框、一份可视化。
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={() => setIngestionOpen(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            入库新资产
          </Button>
          <Button
            variant="outline"
            disabled={reindexMutation.isPending}
            onClick={() => reindexMutation.mutate()}
          >
            {reindexMutation.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 h-3.5 w-3.5" />
            )}
            {reindexMutation.isPending ? "重建中..." : "重建索引"}
          </Button>
        </div>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="全局搜索：跨所有数据源（>=2 字符即触发）"
            className="pl-9"
          />
          {searchQuery && (
            <button
              type="button"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={clearSearch}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        {searchActive && (
          <Badge variant="secondary" className="shrink-0 gap-2 px-3 py-1 text-xs">
            全局搜索 {items.length} 条结果
            <Button variant="ghost" size="sm" className="h-5 px-1" onClick={clearSearch}>
              清除
            </Button>
          </Badge>
        )}
      </div>

      {/* Main layout: facets sidebar + card grid */}
      <div className="grid min-h-0 flex-1 grid-cols-[240px_1fr] gap-4 overflow-hidden">
        {/* Facets */}
        <ScrollArea className="min-h-0">
          <FacetSidebar
            projects={projects}
            projectId={projectId}
            onProjectChange={(id) => setProjectId(id)}
            facetSources={facetSources}
            selectedSources={selectedSources}
            onSourceToggle={handleSourceToggle}
            facetEntityTypes={facetEntityTypes}
            selectedTypes={selectedTypes}
            onTypeToggle={handleTypeToggle}
          />
        </ScrollArea>

        {/* Content area */}
        <ScrollArea className="min-h-0">
          {/* Errors */}
          {listErrors.length > 0 && (
            <div className="mb-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs">
              <strong>部分数据源加载失败：</strong>
              <ul className="mt-1 list-inside list-disc">
                {listErrors.map((e) => (
                  <li key={e.source}>{e.source}: {e.error}</li>
                ))}
              </ul>
            </div>
          )}

          {loading ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-36 w-full rounded-lg" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
              没有匹配的资产
            </div>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
              {items.map((item, idx) => (
                <AssetCard
                  key={`${item.source}:${item.source_ref || idx}`}
                  item={item}
                  onClick={() => setDetailItem(item)}
                />
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Detail drawer */}
      <DetailSheet
        item={detailItem}
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
      />

      {/* Ingestion drawer */}
      <IngestionSheet
        open={ingestionOpen}
        onClose={() => setIngestionOpen(false)}
        projectId={projectId}
        onComplete={() => {
          queryClient.invalidateQueries({ queryKey: ["unifiedAssets"] });
          queryClient.invalidateQueries({ queryKey: ["unifiedFacets"] });
        }}
      />
    </div>
  );
}
