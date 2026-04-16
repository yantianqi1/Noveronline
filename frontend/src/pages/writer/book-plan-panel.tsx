/**
 * BookPlanPanel — 成书计划表单 + book_run SSE 进度可视化。
 *
 * 单文件、自包含：把它挂到 WriterPage 或 Overview 任意位置即可使用。
 * 支持：新建/保存计划 → 启动 book_run → SSE 实时阶段条 + 每章进度 + 命中清单。
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, Loader2, Play, Square } from "lucide-react";
import {
  abortBookRun,
  createBookPlan,
  listBookPlans,
  listForbiddenLexicons,
  runBookRun,
  updateBookPlan,
  type BookPlanInput,
} from "@/api/writer-agent";

const STAGES = [
  { key: "PLAN_INIT", label: "初始化" },
  { key: "RETRIEVE", label: "检索" },
  { key: "OUTLINE", label: "大纲" },
  { key: "CHAPTER_WRITE", label: "逐章写作" },
  { key: "WORD_AUDIT", label: "字数审计" },
  { key: "LEXICON_AUDIT", label: "禁词审计" },
  { key: "CHAPTER_COMMIT", label: "章节落库" },
  { key: "DONE", label: "完成" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

interface ChapterRow {
  order: number;
  status: string;
  word_count: number;
  target: number;
  diff_pct: number;
  lexicon_hits: number;
  audit_round: number;
}

interface BookPlanPanelProps {
  projectId: string;
}

export function BookPlanPanel({ projectId }: BookPlanPanelProps) {
  const [plans, setPlans] = React.useState<any[]>([]);
  const [currentPlanId, setCurrentPlanId] = React.useState<string | null>(null);

  const [form, setForm] = React.useState<BookPlanInput>({
    project_id: projectId,
    title: "",
    chapter_count: 3,
    per_chapter_word_target: 3000,
    word_tolerance_pct: 10,
    overall_direction: "",
    global_brief: "",
    start_chapter_order: 1,
    forbidden_lexicon_asset_ids: [],
    style_asset_ids: [],
  });

  const [lexicons, setLexicons] = React.useState<any[]>([]);
  const [saving, setSaving] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [currentStage, setCurrentStage] = React.useState<StageKey | "">("");
  const [chapterRows, setChapterRows] = React.useState<Record<number, ChapterRow>>({});
  const [logLines, setLogLines] = React.useState<string[]>([]);
  const [auditHits, setAuditHits] = React.useState<any[]>([]);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    if (!projectId) return;
    setForm((f) => ({ ...f, project_id: projectId }));
    refreshPlans();
    refreshLexicons();
  }, [projectId]);

  async function refreshPlans() {
    if (!projectId) return;
    const resp = await listBookPlans(projectId);
    if (resp.success) setPlans((resp.data as any[]) || []);
  }

  async function refreshLexicons() {
    if (!projectId) return;
    const resp = await listForbiddenLexicons(projectId, false);
    if (resp.success) setLexicons((resp.data as any[]) || []);
  }

  async function handleSave() {
    if (!form.title.trim()) {
      alert("请填写计划名称");
      return;
    }
    setSaving(true);
    try {
      if (currentPlanId) {
        await updateBookPlan(currentPlanId, form);
      } else {
        const resp = await createBookPlan(form);
        const created = resp.data as { plan_id?: string } | undefined;
        if (resp.success && created?.plan_id) {
          setCurrentPlanId(created.plan_id);
        }
      }
      await refreshPlans();
    } finally {
      setSaving(false);
    }
  }

  function appendLog(line: string) {
    setLogLines((prev) => [...prev.slice(-199), line]);
  }

  function upsertChapterRow(order: number, patch: Partial<ChapterRow>) {
    setChapterRows((prev) => {
      const existing = prev[order] || {
        order,
        status: "pending",
        word_count: 0,
        target: 0,
        diff_pct: 0,
        lexicon_hits: 0,
        audit_round: 0,
      };
      return { ...prev, [order]: { ...existing, ...patch } };
    });
  }

  async function handleRun() {
    if (!currentPlanId) {
      alert("请先保存计划");
      return;
    }
    setRunning(true);
    setCurrentStage("");
    setChapterRows({});
    setLogLines([]);
    setAuditHits([]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await runBookRun(
        currentPlanId,
        {
          onEvent: (ev: any) => {
            const type = ev?.type;
            if (!type) return;
            if (type === "book_run_stage") {
              setCurrentStage(ev.stage as StageKey);
              if (typeof ev.chapter_order === "number") {
                upsertChapterRow(ev.chapter_order, { status: ev.stage });
              }
              appendLog(`[${ev.stage}] ${ev.message || ""}`);
            } else if (type === "chapter_progress") {
              upsertChapterRow(ev.chapter_order, {
                word_count: ev.word_count || 0,
                target: ev.target || 0,
                diff_pct: ev.diff_pct || 0,
              });
            } else if (type === "audit_hit") {
              setAuditHits((prev) => [...prev, ev]);
              upsertChapterRow(ev.chapter_order, {
                lexicon_hits: ev.details?.count || 0,
              });
              appendLog(
                `[audit_hit/${ev.kind}] 第 ${ev.chapter_order} 章命中 ${ev.details?.count || 0} 处`,
              );
            } else if (type === "audit_fixed") {
              upsertChapterRow(ev.chapter_order, {
                lexicon_hits: ev.remaining || 0,
                audit_round: ev.round || 0,
              });
              appendLog(
                `[audit_fixed/${ev.kind}] 第 ${ev.chapter_order} 章残留 ${ev.remaining || 0} 处`,
              );
            } else if (type === "book_run_done") {
              setCurrentStage("DONE");
              appendLog(
                `[DONE] 完成章节 ${ev.chapters_completed?.length || 0}，失败 ${ev.failed_chapters?.length || 0}`,
              );
            } else if (type === "tool_call") {
              appendLog(`  → ${ev.display || ev.name}`);
            } else if (type === "thinking" && ev.content) {
              appendLog(`  · ${String(ev.content).slice(0, 120)}`);
            }
          },
          onError: (ev: any) => {
            const msg = ev instanceof Error ? ev.message : ev?.message || String(ev);
            appendLog(`[error] ${msg}`);
          },
          onDone: () => appendLog("[sse] done"),
        },
        controller.signal,
      );
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  async function handleAbort() {
    if (!currentPlanId) return;
    await abortBookRun(currentPlanId);
    abortRef.current?.abort();
    setRunning(false);
  }

  function loadPlan(plan: any) {
    setCurrentPlanId(plan.plan_id);
    setForm({
      project_id: plan.project_id,
      title: plan.title || "",
      chapter_count: plan.chapter_count,
      per_chapter_word_target: plan.per_chapter_word_target,
      word_tolerance_pct: plan.word_tolerance_pct,
      overall_direction: plan.overall_direction || "",
      global_brief: plan.global_brief || "",
      start_chapter_order: plan.start_chapter_order,
      forbidden_lexicon_asset_ids: plan.forbidden_lexicon_asset_ids || [],
      style_asset_ids: plan.style_asset_ids || [],
      preset_id: plan.preset_id,
    });
  }

  function resetForm() {
    setCurrentPlanId(null);
    setForm({
      project_id: projectId,
      title: "",
      chapter_count: 3,
      per_chapter_word_target: 3000,
      word_tolerance_pct: 10,
      overall_direction: "",
      global_brief: "",
      start_chapter_order: 1,
      forbidden_lexicon_asset_ids: [],
      style_asset_ids: [],
    });
  }

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base">
          <span>成书计划（book_run）</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={resetForm} disabled={running}>
              新建
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving || running}>
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : "保存"}
            </Button>
            {!running ? (
              <Button size="sm" onClick={handleRun} disabled={!currentPlanId}>
                <Play className="w-3 h-3 mr-1" /> 启动
              </Button>
            ) : (
              <Button size="sm" variant="destructive" onClick={handleAbort}>
                <Square className="w-3 h-3 mr-1" /> 终止
              </Button>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Existing plans */}
        {plans.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground">
              <ChevronDown className="w-3 h-3" />
              已保存计划（{plans.length}）
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-1">
              {plans.map((p) => (
                <div
                  key={p.plan_id}
                  className={`flex justify-between text-xs p-2 rounded cursor-pointer hover:bg-muted ${
                    currentPlanId === p.plan_id ? "bg-muted" : ""
                  }`}
                  onClick={() => loadPlan(p)}
                >
                  <span>{p.title || "（未命名）"}</span>
                  <span className="text-muted-foreground">
                    {p.chapter_count}章 · {p.status}
                  </span>
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Form */}
        <div className="space-y-2">
          <div>
            <Label className="text-xs">计划名称</Label>
            <Input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="如：第一卷 · 初入江湖"
              disabled={running}
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-xs">章节数</Label>
              <Input
                type="number"
                min={1}
                max={50}
                value={form.chapter_count}
                onChange={(e) =>
                  setForm({ ...form, chapter_count: Number(e.target.value) || 1 })
                }
                disabled={running}
              />
            </div>
            <div>
              <Label className="text-xs">每章目标字数</Label>
              <Input
                type="number"
                min={500}
                step={500}
                value={form.per_chapter_word_target}
                onChange={(e) =>
                  setForm({
                    ...form,
                    per_chapter_word_target: Number(e.target.value) || 3000,
                  })
                }
                disabled={running}
              />
            </div>
            <div>
              <Label className="text-xs">容忍度 %</Label>
              <Input
                type="number"
                min={5}
                max={30}
                value={form.word_tolerance_pct}
                onChange={(e) =>
                  setForm({
                    ...form,
                    word_tolerance_pct: Number(e.target.value) || 10,
                  })
                }
                disabled={running}
              />
            </div>
          </div>
          <div>
            <Label className="text-xs">起始章节号</Label>
            <Input
              type="number"
              min={1}
              value={form.start_chapter_order}
              onChange={(e) =>
                setForm({ ...form, start_chapter_order: Number(e.target.value) || 1 })
              }
              disabled={running}
            />
          </div>
          <div>
            <Label className="text-xs">整体发展方向</Label>
            <Textarea
              value={form.overall_direction}
              onChange={(e) => setForm({ ...form, overall_direction: e.target.value })}
              placeholder="简述这几章的整体剧情走向、冲突升级曲线、关键转折"
              rows={4}
              disabled={running}
            />
          </div>
          <div>
            <Label className="text-xs">全局补充（可选）</Label>
            <Textarea
              value={form.global_brief}
              onChange={(e) => setForm({ ...form, global_brief: e.target.value })}
              placeholder="全局风格要求、禁忌、视角约束等"
              rows={3}
              disabled={running}
            />
          </div>
          {lexicons.length > 0 && (
            <div>
              <Label className="text-xs">启用禁词表</Label>
              <div className="space-y-1 mt-1">
                {lexicons.map((lx) => (
                  <label
                    key={lx.asset_id}
                    className="flex items-center gap-2 text-xs cursor-pointer"
                  >
                    <Checkbox
                      checked={
                        form.forbidden_lexicon_asset_ids?.includes(lx.asset_id) || false
                      }
                      onCheckedChange={(checked) => {
                        const ids = form.forbidden_lexicon_asset_ids || [];
                        setForm({
                          ...form,
                          forbidden_lexicon_asset_ids: checked
                            ? [...ids, lx.asset_id]
                            : ids.filter((x) => x !== lx.asset_id),
                        });
                      }}
                      disabled={running}
                    />
                    <span>
                      {lx.title}{" "}
                      <span className="text-muted-foreground">
                        ({lx.entry_count ?? "?"} 条)
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Stage bar */}
        {(running || currentStage) && (
          <div className="border-t pt-3 space-y-2">
            <div className="flex flex-wrap gap-1">
              {STAGES.map((s) => {
                const idxCurrent = STAGES.findIndex((x) => x.key === currentStage);
                const idxThis = STAGES.findIndex((x) => x.key === s.key);
                const active = idxCurrent === idxThis;
                const done = idxCurrent > idxThis;
                return (
                  <Badge
                    key={s.key}
                    variant={active ? "default" : done ? "secondary" : "outline"}
                    className="text-[10px]"
                  >
                    {s.label}
                  </Badge>
                );
              })}
            </div>

            {Object.keys(chapterRows).length > 0 && (
              <div className="space-y-1">
                {Object.values(chapterRows)
                  .sort((a, b) => a.order - b.order)
                  .map((row) => {
                    const pct =
                      row.target > 0
                        ? Math.min(100, Math.round((row.word_count / row.target) * 100))
                        : 0;
                    return (
                      <div key={row.order} className="text-xs">
                        <div className="flex justify-between">
                          <span>
                            第 {row.order} 章 · {row.status}
                          </span>
                          <span className="text-muted-foreground">
                            {row.word_count}/{row.target} ({row.diff_pct.toFixed(1)}%)
                            {row.lexicon_hits > 0 && ` · 禁词 ${row.lexicon_hits}`}
                            {row.audit_round > 0 && ` · 审 ${row.audit_round}`}
                          </span>
                        </div>
                        <Progress value={pct} className="h-1" />
                      </div>
                    );
                  })}
              </div>
            )}

            {auditHits.length > 0 && (
              <Collapsible>
                <CollapsibleTrigger className="flex items-center gap-1 text-xs text-amber-600">
                  <ChevronDown className="w-3 h-3" />
                  审计命中 ({auditHits.length})
                </CollapsibleTrigger>
                <CollapsibleContent className="mt-1 space-y-1 text-xs">
                  {auditHits.slice(-20).map((h, i) => (
                    <div key={i} className="text-muted-foreground truncate">
                      [第{h.chapter_order}章/{h.kind}]{" "}
                      {JSON.stringify(h.details?.sample?.[0] || h.details).slice(0, 120)}
                    </div>
                  ))}
                </CollapsibleContent>
              </Collapsible>
            )}

            <ScrollArea className="h-40 border rounded p-2">
              <pre className="text-[10px] whitespace-pre-wrap leading-tight">
                {logLines.join("\n")}
              </pre>
            </ScrollArea>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
