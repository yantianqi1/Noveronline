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
  Loader2,
  Package,
  BookOpen,
  Network,
  PenLine,
  Globe2,
  Sprout,
  ExternalLink,
  LayoutGrid,
  List,
  KanbanSquare,
  Users,
  Link2,
  Map,
  Film,
  Library,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ApiResponse } from "@/api/http";
import {
  listUnifiedAssets,
  getUnifiedFacets,
  searchGlobalAssets,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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

/* 语义范畴 — 回答「这是什么」。与后端 unified_asset_view.CATEGORY_* 对齐 */
interface CategoryMeta {
  key: string;
  label: string;
  icon: React.ReactNode;
  color: string;  // tailwind bg-* token for the facet chip
}

const CATEGORIES: CategoryMeta[] = [
  { key: "characters", label: "角色", icon: <Users className="h-3 w-3" />, color: "bg-violet-500" },
  { key: "relationships", label: "关系", icon: <Link2 className="h-3 w-3" />, color: "bg-rose-500" },
  { key: "world", label: "世界设定", icon: <Map className="h-3 w-3" />, color: "bg-teal-500" },
  { key: "plot", label: "情节/场景", icon: <Film className="h-3 w-3" />, color: "bg-orange-500" },
  { key: "materials", label: "写作素材", icon: <Library className="h-3 w-3" />, color: "bg-sky-500" },
  { key: "other", label: "其它", icon: <FileText className="h-3 w-3" />, color: "bg-gray-400" },
];

/* 生命周期 — 回答「处于什么阶段」。与后端 LIFECYCLE_* 对齐 */
interface LifecycleMeta {
  key: string;
  label: string;
  tone: string;  // tailwind text-* for the lifecycle badge
}

const LIFECYCLES: LifecycleMeta[] = [
  { key: "seed", label: "种子", tone: "text-lime-600 bg-lime-50 border-lime-200" },
  { key: "candidate", label: "候选待审", tone: "text-amber-600 bg-amber-50 border-amber-200" },
  { key: "canon", label: "正典", tone: "text-emerald-600 bg-emerald-50 border-emerald-200" },
  { key: "material", label: "素材", tone: "text-sky-600 bg-sky-50 border-sky-200" },
  { key: "simulation", label: "模拟", tone: "text-blue-600 bg-blue-50 border-blue-200" },
  { key: "graph", label: "图谱", tone: "text-orange-600 bg-orange-50 border-orange-200" },
];

function getLifecycleMeta(key: string): LifecycleMeta | undefined {
  return LIFECYCLES.find((l) => l.key === key);
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
  category?: string;
  lifecycle?: string;
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

interface FacetBucket {
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
  onDelete,
}: {
  item: UnifiedItem;
  onClick: () => void;
  onDelete?: (item: UnifiedItem) => void;
}) {
  const source = getSourceMeta(item.source);
  const typeLabel = ENTITY_TYPE_LABELS[item.entity_type || ""] || item.entity_type || "--";
  const importanceLabel = item.importance ? (IMPORTANCE_LABELS[item.importance] || item.importance) : null;
  const lifecycle = item.lifecycle ? getLifecycleMeta(item.lifecycle) : undefined;
  const deletable = item.source === "assets" && !!onDelete;

  return (
    <Card
      className="flex cursor-pointer flex-col gap-1.5 p-3 transition-all hover:border-primary/30 hover:shadow-md"
      onClick={onClick}
    >
      {/* Header: source badge + type + lifecycle + importance */}
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
        {lifecycle && (
          <Badge
            variant="outline"
            className={cn("h-4 border px-1 text-[9px] font-normal", lifecycle.tone)}
            title={`生命周期:${lifecycle.label}`}
          >
            {lifecycle.label}
          </Badge>
        )}
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
        {deletable && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete!(item);
            }}
            className="ml-auto inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            title="删除"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </Card>
  );
}

/* Compact row variant used by the list view. */
function AssetRow({
  item,
  onClick,
  onDelete,
}: {
  item: UnifiedItem;
  onClick: () => void;
  onDelete?: (item: UnifiedItem) => void;
}) {
  const source = getSourceMeta(item.source);
  const typeLabel = ENTITY_TYPE_LABELS[item.entity_type || ""] || item.entity_type || "--";
  const lifecycle = item.lifecycle ? getLifecycleMeta(item.lifecycle) : undefined;
  const deletable = item.source === "assets" && !!onDelete;
  return (
    <div
      className="group flex cursor-pointer items-center gap-2 rounded border border-transparent px-2 py-1.5 text-xs hover:border-primary/20 hover:bg-muted/40"
      onClick={onClick}
    >
      <span
        className={cn(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-white",
          source.color,
        )}
        title={source.label}
      >
        {source.icon}
      </span>
      <span className="w-20 shrink-0 truncate text-muted-foreground">{typeLabel}</span>
      {lifecycle && (
        <Badge
          variant="outline"
          className={cn("h-4 shrink-0 border px-1 text-[9px] font-normal", lifecycle.tone)}
        >
          {lifecycle.label}
        </Badge>
      )}
      <span className="min-w-0 flex-1 truncate font-medium">
        {item.title || item.name || "(无标题)"}
      </span>
      <span className="hidden shrink-0 truncate text-muted-foreground md:inline md:max-w-[200px]">
        {item.summary || ""}
      </span>
      <span className="shrink-0 text-[10px] text-muted-foreground">{item.updated_at || ""}</span>
      {deletable && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete!(item);
          }}
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground opacity-0 hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
          title="删除"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail Sheet                                                       */
/* ------------------------------------------------------------------ */

function DetailSheet({
  item,
  open,
  onClose,
  onDelete,
}: {
  item: UnifiedItem | null;
  open: boolean;
  onClose: () => void;
  onDelete?: (item: UnifiedItem) => void;
}) {
  const [payloadExpanded, setPayloadExpanded] = React.useState(false);

  if (!item) return null;

  const source = getSourceMeta(item.source);
  const deletable = item.source === "assets" && !!onDelete;

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

            {/* Delete action — only for source=assets */}
            {deletable && (
              <>
                <Separator />
                <div className="flex justify-end">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onDelete!(item)}
                  >
                    <Trash2 className="mr-1 h-3.5 w-3.5" />
                    删除资产
                  </Button>
                </div>
              </>
            )}
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
  facetCategories,
  selectedCategories,
  onCategoryToggle,
  facetLifecycles,
  selectedLifecycles,
  onLifecycleToggle,
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
  facetCategories: Record<string, number>;
  selectedCategories: string[];
  onCategoryToggle: (key: string) => void;
  facetLifecycles: Record<string, number>;
  selectedLifecycles: string[];
  onLifecycleToggle: (key: string) => void;
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
            <SelectValue placeholder="(全局范围 / 不选项目)">
              {(value: unknown) => {
                const id = typeof value === "string" ? value : "";
                if (!id) return "(全局范围 / 不选项目)";
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
      </div>

      {/* Semantic category — 这是什么 */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">语义范畴</h3>
        <div className="flex flex-col gap-1">
          {CATEGORIES.map((c) => {
            const count = facetCategories[c.key];
            if (count === undefined) return null;
            const checked = selectedCategories.includes(c.key);
            return (
              <label
                key={c.key}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted/40"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onCategoryToggle(c.key)}
                />
                <span className={cn("inline-flex h-5 w-5 items-center justify-center rounded text-white", c.color)}>
                  {c.icon}
                </span>
                <span className="flex-1">{c.label}</span>
                <span className="text-[11px] text-muted-foreground">{count}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Lifecycle — 处于什么阶段 */}
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">生命周期</h3>
        <div className="flex flex-col gap-1">
          {LIFECYCLES.map((l) => {
            const count = facetLifecycles[l.key];
            if (count === undefined) return null;
            const checked = selectedLifecycles.includes(l.key);
            return (
              <label
                key={l.key}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted/40"
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => onLifecycleToggle(l.key)}
                />
                <Badge variant="outline" className={cn("h-5 border px-1.5 text-[10px] font-normal", l.tone)}>
                  {l.label}
                </Badge>
                <span className="ml-auto text-[11px] text-muted-foreground">{count}</span>
              </label>
            );
          })}
        </div>
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
  const [selectedCategories, setSelectedCategories] = React.useState<string[]>([]);
  const [selectedLifecycles, setSelectedLifecycles] = React.useState<string[]>([]);
  const [viewMode, setViewMode] = React.useState<"cards" | "list" | "kanban">("cards");

  /* -- detail / ingestion drawers -- */
  const [detailItem, setDetailItem] = React.useState<UnifiedItem | null>(null);
  const [ingestionOpen, setIngestionOpen] = React.useState(false);

  /* -- delete confirmation -- */
  const [deleteTarget, setDeleteTarget] = React.useState<UnifiedItem | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (target: UnifiedItem) =>
      deleteAsset(target.source_ref || "", {
        scope: target.scope === "project" ? "project" : "global",
        projectId: target.project_id || "",
      }),
    onSuccess: () => {
      notifySuccess("已删除");
      setDeleteTarget(null);
      setDetailItem(null);
      queryClient.invalidateQueries({ queryKey: ["unifiedAssets"] });
      queryClient.invalidateQueries({ queryKey: ["unifiedFacets"] });
      queryClient.invalidateQueries({ queryKey: ["globalAssetSearch"] });
    },
    onError: (err: Error) => {
      notifyError(err.message || "删除失败");
      setDeleteTarget(null);
    },
  });

  const handleRequestDelete = React.useCallback((item: UnifiedItem) => {
    if (item.source !== "assets" || !item.source_ref) return;
    setDeleteTarget(item);
  }, []);

  const confirmDelete = React.useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget);
    }
  }, [deleteTarget, deleteMutation]);

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
    categories?: FacetBucket[];
    lifecycles?: FacetBucket[];
    total?: number;
  } | undefined;
  const facetSources = React.useMemo(() => {
    return Object.fromEntries(
      (facetsData?.sources || []).map((s) => [s.key, s.count]),
    );
  }, [facetsData]);
  const facetCategories = React.useMemo(() => {
    return Object.fromEntries(
      (facetsData?.categories || []).map((c) => [c.key, c.count]),
    );
  }, [facetsData]);
  const facetLifecycles = React.useMemo(() => {
    return Object.fromEntries(
      (facetsData?.lifecycles || []).map((l) => [l.key, l.count]),
    );
  }, [facetsData]);
  const facetEntityTypes = facetsData?.entity_types || [];

  /* -- unified list query (normal browse) -- */
  const listQuery = useQuery({
    queryKey: ["unifiedAssets", projectId, selectedSources, selectedTypes, selectedCategories, selectedLifecycles],
    queryFn: () =>
      listUnifiedAssets({
        projectId,
        sources: selectedSources,
        entityTypes: selectedTypes,
        categories: selectedCategories,
        lifecycles: selectedLifecycles,
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

  function handleCategoryToggle(key: string) {
    setSelectedCategories((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function handleLifecycleToggle(key: string) {
    setSelectedLifecycles((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  function clearSearch() {
    setSearchQuery("");
    setDebouncedSearch("");
    setSearchActive(false);
  }

  /* -- stats for the header strip -- */
  const candidateCount = facetLifecycles.candidate || 0;
  const statCards: Array<{ key: string; label: string; count: number; color: string; icon: React.ReactNode }> = [
    { key: "characters", label: "角色", color: "bg-violet-50 text-violet-600", icon: <Users className="h-3.5 w-3.5" />, count: facetCategories.characters || 0 },
    { key: "relationships", label: "关系", color: "bg-rose-50 text-rose-600", icon: <Link2 className="h-3.5 w-3.5" />, count: facetCategories.relationships || 0 },
    { key: "world", label: "世界设定", color: "bg-teal-50 text-teal-600", icon: <Map className="h-3.5 w-3.5" />, count: facetCategories.world || 0 },
    { key: "plot", label: "情节/场景", color: "bg-orange-50 text-orange-600", icon: <Film className="h-3.5 w-3.5" />, count: facetCategories.plot || 0 },
    { key: "materials", label: "写作素材", color: "bg-sky-50 text-sky-600", icon: <Library className="h-3.5 w-3.5" />, count: facetCategories.materials || 0 },
  ];

  return (
    <div className="flex h-[calc(100vh-60px)] flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">资产库</h1>
          <p className="text-sm text-muted-foreground">
            统一查看本项目所有数据:种子档案、故事图谱、写作工坊、世界线、独立资产 ——
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

      {/* Stats strip: one tile per category + candidate review shortcut */}
      <div className="flex flex-wrap items-center gap-2">
        {statCards.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => handleCategoryToggle(c.key)}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors",
              selectedCategories.includes(c.key)
                ? "border-primary/50 bg-primary/5"
                : "border-border/60 hover:border-primary/30",
            )}
            title={`按「${c.label}」过滤`}
          >
            <span className={cn("inline-flex h-6 w-6 items-center justify-center rounded", c.color)}>
              {c.icon}
            </span>
            <span className="flex flex-col items-start leading-none">
              <span className="text-[10px] text-muted-foreground">{c.label}</span>
              <span className="text-sm font-semibold">{c.count}</span>
            </span>
          </button>
        ))}
        {candidateCount > 0 && (
          <button
            type="button"
            onClick={() => handleLifecycleToggle("candidate")}
            className={cn(
              "ml-auto inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors",
              selectedLifecycles.includes("candidate")
                ? "border-amber-500/70 bg-amber-50"
                : "border-amber-400/40 bg-amber-50/50 hover:border-amber-500/60",
            )}
            title="筛选候选记忆待审核"
          >
            <span className="inline-flex h-6 min-w-6 items-center justify-center rounded bg-amber-500 px-1 text-[10px] font-bold text-white">
              {candidateCount}
            </span>
            <span className="font-medium text-amber-700">候选待审核</span>
          </button>
        )}
      </div>

      {/* Search bar + view switcher */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="全局搜索:跨所有数据源(>=2 字符即触发)"
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
        <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as "cards" | "list" | "kanban")}>
          <TabsList className="h-8">
            <TabsTrigger value="cards" className="h-6 px-2 text-xs" title="卡片视图">
              <LayoutGrid className="h-3.5 w-3.5" />
            </TabsTrigger>
            <TabsTrigger value="list" className="h-6 px-2 text-xs" title="紧凑列表">
              <List className="h-3.5 w-3.5" />
            </TabsTrigger>
            <TabsTrigger value="kanban" className="h-6 px-2 text-xs" title="生命周期看板">
              <KanbanSquare className="h-3.5 w-3.5" />
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Main layout: facets sidebar + content */}
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
            facetCategories={facetCategories}
            selectedCategories={selectedCategories}
            onCategoryToggle={handleCategoryToggle}
            facetLifecycles={facetLifecycles}
            selectedLifecycles={selectedLifecycles}
            onLifecycleToggle={handleLifecycleToggle}
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
              <strong>部分数据源加载失败:</strong>
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
          ) : viewMode === "cards" ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
              {items.map((item, idx) => (
                <AssetCard
                  key={`${item.source}:${item.source_ref || idx}`}
                  item={item}
                  onClick={() => setDetailItem(item)}
                  onDelete={handleRequestDelete}
                />
              ))}
            </div>
          ) : viewMode === "list" ? (
            <div className="flex flex-col gap-0.5">
              {items.map((item, idx) => (
                <AssetRow
                  key={`${item.source}:${item.source_ref || idx}`}
                  item={item}
                  onClick={() => setDetailItem(item)}
                  onDelete={handleRequestDelete}
                />
              ))}
            </div>
          ) : (
            /* Kanban — group by lifecycle column */
            <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3">
              {LIFECYCLES.filter((l) => items.some((it) => (it.lifecycle || "canon") === l.key)).map((l) => {
                const colItems = items.filter((it) => (it.lifecycle || "canon") === l.key);
                return (
                  <div
                    key={l.key}
                    className={cn(
                      "flex min-h-[200px] flex-col gap-2 rounded-lg border p-2",
                      l.tone,
                    )}
                  >
                    <div className="flex items-center justify-between px-1 text-xs font-semibold">
                      <span>{l.label}</span>
                      <span className="rounded bg-white/70 px-1.5 text-[10px]">{colItems.length}</span>
                    </div>
                    <div className="flex flex-col gap-2 overflow-hidden">
                      {colItems.slice(0, 40).map((item, idx) => (
                        <AssetCard
                          key={`${item.source}:${item.source_ref || idx}`}
                          item={item}
                          onClick={() => setDetailItem(item)}
                          onDelete={handleRequestDelete}
                        />
                      ))}
                      {colItems.length > 40 && (
                        <span className="px-1 text-[10px] text-muted-foreground">
                          另有 {colItems.length - 40} 条未显示
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Detail drawer */}
      <DetailSheet
        item={detailItem}
        open={!!detailItem}
        onClose={() => setDetailItem(null)}
        onDelete={handleRequestDelete}
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

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? `确认删除资产「${deleteTarget.title || deleteTarget.name || "(无标题)"}」吗？此操作不可撤销。`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
