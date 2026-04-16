import * as React from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  formatArchiveKindLabel,
  formatArchiveSectionLabel,
  formatArchiveTierLabel,
  sectionKeysByTier,
  tierSelectOptions,
} from "./archive-template-labels";
import { sanitizeDisplayText } from "./display-text";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ArchiveCandidate {
  entity_uuid: string;
  display_name: string;
  summary: string;
  agent_kind: string;
  recommended_importance_tier: string;
  selected_importance_tier?: string;
  template_sections?: string[];
  [key: string]: unknown;
}

interface AgentTemplateConfiguratorProps {
  open: boolean;
  candidates: ArchiveCandidate[];
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: (candidateSnapshot: ArchiveCandidate[]) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AgentTemplateConfigurator({
  open,
  candidates,
  busy,
  error,
  onClose,
  onConfirm,
}: AgentTemplateConfiguratorProps) {
  const [tierState, setTierState] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    const initial: Record<string, string> = {};
    for (const item of candidates) {
      initial[item.entity_uuid] =
        item.selected_importance_tier || item.recommended_importance_tier || "supporting";
    }
    setTierState(initial);
  }, [candidates]);

  function resolvedTier(entityUuid: string): string {
    return tierState[entityUuid] || "supporting";
  }

  function updateTier(entityUuid: string, value: string) {
    setTierState((prev) => ({ ...prev, [entityUuid]: value }));
  }

  function previewSections(item: ArchiveCandidate): string[] {
    return sectionKeysByTier[resolvedTier(item.entity_uuid)] || item.template_sections || [];
  }

  function handleConfirm() {
    onConfirm(
      candidates.map((item) => ({
        ...item,
        selected_importance_tier: resolvedTier(item.entity_uuid),
      })),
    );
  }

  const groupedCandidates = React.useMemo(() => {
    const groups = new Map<string, { kind: string; label: string; items: ArchiveCandidate[] }>();
    for (const item of candidates) {
      const kind = item.agent_kind || "generic";
      if (!groups.has(kind)) {
        groups.set(kind, { kind, label: formatArchiveKindLabel(kind), items: [] });
      }
      groups.get(kind)!.items.push(item);
    }
    return Array.from(groups.values());
  }, [candidates]);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-[900px]">
        <DialogHeader>
          <DialogTitle>档案模板确认</DialogTitle>
          <DialogDescription>
            系统已按叙事重要度推荐档位，你只需调整少量对象。
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          <ScrollArea className="max-h-[60vh]">
            <div className="flex flex-col gap-3 pr-2">
              {groupedCandidates.map((group) => (
                <div key={group.kind} className="flex flex-col gap-2.5">
                  <div className="text-sm font-bold">
                    {group.label} · {group.items.length}
                  </div>
                  {group.items.map((item) => (
                    <div
                      key={item.entity_uuid}
                      className="flex min-w-0 flex-col gap-1.5 rounded-lg border p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <strong className="break-words text-sm">
                            {sanitizeDisplayText(item.display_name, { emptyLabel: "未命名对象" })}
                          </strong>
                          <div className="font-mono text-[11px] text-muted-foreground">
                            推荐 {formatArchiveTierLabel(item.recommended_importance_tier)} ·{" "}
                            当前 {formatArchiveTierLabel(resolvedTier(item.entity_uuid))}
                          </div>
                        </div>
                        <Select
                          value={resolvedTier(item.entity_uuid)}
                          onValueChange={(val) => updateTier(item.entity_uuid, val ?? "supporting")}
                        >
                          <SelectTrigger className="w-[130px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {tierSelectOptions.map((opt) => (
                              <SelectItem key={opt.value} value={opt.value}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <p className="break-words text-xs text-muted-foreground">
                        {sanitizeDisplayText(item.summary, { emptyLabel: "" })}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {previewSections(item).map((section) => (
                          <Badge key={section} variant="secondary" className="text-[10px]">
                            {formatArchiveSectionLabel(section)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button disabled={busy} onClick={handleConfirm}>
            {busy && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            确认并生成档案
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
