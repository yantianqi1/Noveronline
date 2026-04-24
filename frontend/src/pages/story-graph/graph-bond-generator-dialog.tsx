import * as React from "react";
import { Loader2, Sparkles, AlertCircle, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { useNotification } from "@/hooks/use-notification";
import {
  generateGraphBond,
  type GeneratedBond,
  type GeneratedPlotThread,
  type GraphBondGenerateResponse,
} from "@/api/project";
import type { ApiResponse } from "@/api/http";
import type { GraphNodeVM } from "./graph-view-model";

interface GraphBondGeneratorDialogProps {
  open: boolean;
  projectId: string;
  selectedNodes: GraphNodeVM[];
  onOpenChange: (open: boolean) => void;
  onGenerated?: (result: GraphBondGenerateResponse) => void;
}

export function GraphBondGeneratorDialog({
  open,
  projectId,
  selectedNodes,
  onOpenChange,
  onGenerated,
}: GraphBondGeneratorDialogProps) {
  const { notifySuccess, notifyError } = useNotification();

  const [generateBonds, setGenerateBonds] = React.useState(true);
  const [generateThreads, setGenerateThreads] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<GraphBondGenerateResponse | null>(null);
  const [errorText, setErrorText] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      setResult(null);
      setErrorText("");
      setBusy(false);
    }
  }, [open]);

  const canSubmit =
    projectId &&
    selectedNodes.length >= 2 &&
    selectedNodes.length <= 6 &&
    (generateBonds || generateThreads) &&
    !busy;

  async function handleGenerate() {
    if (!canSubmit) return;
    setBusy(true);
    setErrorText("");
    try {
      const res = (await generateGraphBond(projectId, {
        node_uuids: selectedNodes.map((n) => n.id),
        generate_bonds: generateBonds,
        generate_threads: generateThreads,
      })) as ApiResponse<GraphBondGenerateResponse>;
      if (!res.success || !res.data) {
        const msg = (res.error as string) || "生成失败";
        setErrorText(msg);
        notifyError(msg);
        return;
      }
      setResult(res.data);
      const bondOk = res.data.bonds.filter((b) => b.persisted).length;
      const threadOk = res.data.plot_threads.filter((t) => t.persisted).length;
      notifySuccess(
        `已落库 ${bondOk} 条羁绊 / ${threadOk} 条支线`,
        "图谱羁绊生成",
      );
      onGenerated?.(res.data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "生成失败";
      setErrorText(msg);
      notifyError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[720px]">
        <DialogHeader>
          <DialogTitle>图谱羁绊 / 支线生成</DialogTitle>
          <DialogDescription>
            基于 {selectedNodes.length} 个选中节点，让 LLM 创作人物羁绊（关系）与支线剧情。
            生成后会直接写入关系库与支线库，可事后编辑。
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh]">
          <div className="flex flex-col gap-3 pr-2">
            {/* Selected nodes */}
            <section className="rounded-lg border border-border/60 bg-muted/30 p-2.5">
              <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                {"已选节点"}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {selectedNodes.map((n) => (
                  <span
                    key={n.id}
                    className="inline-flex items-center gap-1 rounded-md bg-card px-2 py-0.5 text-xs ring-1 ring-border"
                  >
                    <span className="font-medium">{n.name || "(未命名)"}</span>
                    {n.entity_type ? (
                      <span className="text-[10px] text-muted-foreground">
                        {n.entity_type}
                      </span>
                    ) : null}
                  </span>
                ))}
              </div>
            </section>

            {/* Options */}
            <section className="rounded-lg border border-border/60 p-2.5">
              <div className="mb-1.5 text-xs font-semibold text-muted-foreground">
                {"生成内容"}
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={generateBonds}
                    onCheckedChange={(v) => setGenerateBonds(v === true)}
                    disabled={busy}
                  />
                  {"人物羁绊（关系 / 情感）"}
                </label>
                <label className="flex items-center gap-2">
                  <Checkbox
                    checked={generateThreads}
                    onCheckedChange={(v) => setGenerateThreads(v === true)}
                    disabled={busy}
                  />
                  {"支线剧情"}
                </label>
              </div>
            </section>

            {/* Error */}
            {errorText && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {errorText}
              </p>
            )}

            {/* Loading state */}
            {busy && !result && (
              <div className="flex items-center gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {"LLM 正在创作，通常需要 5-15 秒..."}
              </div>
            )}

            {/* Results */}
            {result && (
              <ResultPreview result={result} />
            )}
          </div>
        </ScrollArea>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            {result ? "关闭" : "取消"}
          </Button>
          <Button onClick={handleGenerate} disabled={!canSubmit}>
            {busy ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            )}
            {result ? "再生成一次" : "生成"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResultPreview({ result }: { result: GraphBondGenerateResponse }) {
  const hasBonds = result.bonds.length > 0;
  const hasThreads = result.plot_threads.length > 0;
  const hasUnmapped = result.unmapped_names.length > 0;

  return (
    <section className="flex flex-col gap-3">
      {hasUnmapped && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50 p-2 text-xs text-amber-900">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <div>
            <div className="font-semibold">{"以下节点未能匹配实体库，羁绊未落库："}</div>
            <div className="mt-0.5">{result.unmapped_names.join("、")}</div>
          </div>
        </div>
      )}

      {hasBonds && (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-semibold text-muted-foreground">
            {`羁绊（${result.bonds.length}）`}
          </div>
          {result.bonds.map((bond, idx) => (
            <BondCard key={`bond_${idx}`} bond={bond} />
          ))}
        </div>
      )}

      {hasThreads && (
        <div className="flex flex-col gap-2">
          <div className="text-xs font-semibold text-muted-foreground">
            {`支线剧情（${result.plot_threads.length}）`}
          </div>
          {result.plot_threads.map((thread, idx) => (
            <ThreadCard key={`thread_${idx}`} thread={thread} />
          ))}
        </div>
      )}

      {!hasBonds && !hasThreads && (
        <p className="text-xs text-muted-foreground">{"LLM 未返回有效结果，请重试或调整选择。"}</p>
      )}
    </section>
  );
}

function BondCard({ bond }: { bond: GeneratedBond }) {
  return (
    <div
      className={cn(
        "rounded-lg border p-2.5 text-xs",
        bond.persisted ? "border-emerald-500/40 bg-emerald-50/50" : "border-amber-500/40 bg-amber-50/40",
      )}
    >
      <div className="mb-1 flex items-center gap-1.5">
        {bond.persisted ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
        ) : (
          <XCircle className="h-3.5 w-3.5 text-amber-600" />
        )}
        <span className="font-semibold">{bond.source_name}</span>
        <span className="text-muted-foreground">→</span>
        <span className="font-semibold">{bond.target_name}</span>
        {bond.relation_type && (
          <span className="rounded bg-card px-1.5 py-0.5 text-[10px] ring-1 ring-border">
            {bond.relation_type}
          </span>
        )}
      </div>
      {bond.description && <p className="mb-1 leading-relaxed">{bond.description}</p>}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
        {bond.trust_level !== null && <span>{`信任度 ${bond.trust_level}`}</span>}
        {bond.power_dynamic && <span>{`权力：${bond.power_dynamic}`}</span>}
        {bond.history && <span className="basis-full">{`背景：${bond.history}`}</span>}
        {bond.conflict_trigger && (
          <span className="basis-full">{`冲突触发：${bond.conflict_trigger}`}</span>
        )}
        {!bond.persisted && bond.skip_reason && (
          <span className="basis-full text-amber-700">{`未落库：${bond.skip_reason}`}</span>
        )}
      </div>
    </div>
  );
}

function ThreadCard({ thread }: { thread: GeneratedPlotThread }) {
  return (
    <div
      className={cn(
        "rounded-lg border p-2.5 text-xs",
        thread.persisted ? "border-emerald-500/40 bg-emerald-50/50" : "border-amber-500/40 bg-amber-50/40",
      )}
    >
      <div className="mb-1 flex items-center gap-1.5">
        {thread.persisted ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
        ) : (
          <XCircle className="h-3.5 w-3.5 text-amber-600" />
        )}
        <span className="font-mono text-[10px] text-muted-foreground">{thread.thread_key}</span>
        <span className="rounded bg-card px-1.5 py-0.5 text-[10px] ring-1 ring-border">
          {thread.status}
        </span>
      </div>
      {thread.detail && <p className="mb-1 leading-relaxed">{thread.detail}</p>}
      {thread.involved_names.length > 0 && (
        <div className="text-[10px] text-muted-foreground">
          {`涉及：${thread.involved_names.join("、")}`}
          {thread.linked_entity_ids.length > 0 && (
            <span>{`（已链接 ${thread.linked_entity_ids.length} 个实体）`}</span>
          )}
        </div>
      )}
      {!thread.persisted && thread.skip_reason && (
        <p className="mt-1 text-[10px] text-amber-700">{`未落库：${thread.skip_reason}`}</p>
      )}
    </div>
  );
}
