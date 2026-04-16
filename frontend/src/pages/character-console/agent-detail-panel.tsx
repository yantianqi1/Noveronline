import * as React from "react";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

import {
  buildSelectedAgentDetailSections,
  type AgentData,
  type DetailSection,
} from "./agent-detail-presentation";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface AgentDetailPanelProps {
  selectedAgent: AgentData | null;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function AgentDetailPanel({ selectedAgent }: AgentDetailPanelProps) {
  const detailSections = React.useMemo(
    () => buildSelectedAgentDetailSections(selectedAgent),
    [selectedAgent],
  );

  return (
    <Card className="flex flex-col gap-2 p-2.5">
      <h2 className="text-sm font-semibold">对象详情</h2>
      <p className="text-xs text-muted-foreground">
        展示当前对象的结构化档案字段，直接来自 worldline agent state。
      </p>

      {!selectedAgent ? (
        <div className="flex min-h-[120px] items-center justify-center text-xs text-muted-foreground">
          选择对象后，这里会显示身份、动机、关系与行动倾向。
        </div>
      ) : (
        <ScrollArea className="max-h-[calc(100vh-500px)] min-h-0">
          <div className="flex flex-col gap-2">
            {detailSections.map((section) => (
              <div
                key={section.key}
                className="rounded-lg border bg-muted/20 p-2.5"
              >
                <div className="text-xs font-bold text-primary">
                  {section.label}
                </div>

                {section.variant === "text" && (
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                    {section.text}
                  </p>
                )}

                {section.variant === "entries" && (
                  <dl className="mt-1 flex flex-col gap-1.5">
                    {section.entries?.map((entry) => (
                      <div key={entry.label} className="flex flex-col gap-0.5">
                        <dt className="text-[11px] text-muted-foreground">{entry.label}</dt>
                        <dd className="text-sm leading-relaxed">{entry.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}

                {section.variant === "items" && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {section.items?.map((item) => (
                      <span
                        key={item}
                        className="rounded-full bg-primary/8 px-2.5 py-0.5 text-[13px] text-primary"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </Card>
  );
}
