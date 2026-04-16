import * as React from "react";

import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface LogEntry {
  time: string;
  text: string;
}

interface InteractionLogPanelProps {
  logs: LogEntry[];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function InteractionLogPanel({ logs }: InteractionLogPanelProps) {
  return (
    <Card className="flex flex-col gap-2 p-2.5">
      <h2 className="text-sm font-semibold">交互日志</h2>

      <ScrollArea className="max-h-[460px]">
        {logs.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            暂无日志，执行第一条动作后会记录在这里。
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {logs.map((item, idx) => (
              <div
                key={idx}
                className="rounded-lg border bg-muted/20 p-2"
              >
                <div className="font-mono text-[10px] text-muted-foreground">
                  {item.time}
                </div>
                <div className="text-xs">{item.text}</div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </Card>
  );
}
