import * as React from "react";

import { ArchiveLibraryPicker } from "@/components/archive-library-picker";
import type { ArchiveEntry } from "@/types/archive";
import { SimulationRoster } from "./simulation-roster";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface Archive {
  archive_id: string;
  entity_name?: string;
  [key: string]: unknown;
}

interface Agent {
  agent_id: string;
  display_name?: string;
  agent_kind?: string;
}

interface SelectionPanelProps {
  selectedArchives: Archive[];
  archiveProjectFilter: string;
  sessionId: string;
  preparedAgents: Agent[];
  busy: boolean;
  onUpdateSelectedArchives: (archives: Archive[]) => void;
  onUpdateArchiveProjectFilter: (filter: string) => void;
  onSelectAgent: (agent: { agent_id: string }) => void;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function SelectionPanel({
  selectedArchives,
  archiveProjectFilter,
  sessionId,
  preparedAgents,
  onUpdateSelectedArchives,
  onUpdateArchiveProjectFilter,
  onSelectAgent,
}: SelectionPanelProps) {
  const [selectedAgentIds, setSelectedAgentIds] = React.useState<string[]>([]);

  const panelKicker = sessionId
    ? "AGENTS / 演员名册"
    : preparedAgents.length
      ? "PREPARE / 整备名册"
      : "SELECTION / 源档案";

  const panelTitle = sessionId
    ? "当前世界线参演对象"
    : preparedAgents.length
      ? "LLM 整备后的参演对象"
      : "选择进入世界线的角色与组织";

  const showPicker = !sessionId && !preparedAgents.length;

  return (
    <article className="p-4 flex flex-col gap-3 min-h-full border border-stone-200 rounded-lg bg-white/95">
      {/* Header */}
      <header className="flex flex-wrap items-baseline gap-1.5 gap-x-2">
        <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
          {panelKicker}
        </p>
        <h2 className="text-[0.95rem] font-semibold text-stone-800 m-0">
          {panelTitle}
        </h2>
      </header>

      {/* Pre-session: archive picker */}
      {showPicker && (
        <div className="flex-1 min-h-[500px] flex flex-col">
          <ArchiveLibraryPicker
            projectId={archiveProjectFilter || ""}
            onProjectIdChange={onUpdateArchiveProjectFilter}
            selectedIds={selectedArchives.map((a) => a.archive_id)}
            multiSelect
            onSelect={(archive: ArchiveEntry) => {
              const exists = selectedArchives.some(
                (a) => a.archive_id === (archive as unknown as Archive).archive_id,
              );
              if (exists) {
                onUpdateSelectedArchives(
                  selectedArchives.filter(
                    (a) => a.archive_id !== (archive as unknown as Archive).archive_id,
                  ),
                );
              } else {
                onUpdateSelectedArchives([
                  ...selectedArchives,
                  archive as unknown as Archive,
                ]);
              }
            }}
          />
        </div>
      )}

      {/* Post-session: agent roster */}
      {!showPicker && (
        <div className="flex-1 min-h-0 flex flex-col gap-3">
          {/* Compact archive summary */}
          <div className="flex gap-2 items-start p-2.5 px-3.5 rounded-lg bg-amber-50/70 border border-amber-300/20 shrink-0">
            <span className="font-mono text-[0.68rem] text-stone-400 shrink-0 mt-0.5">
              源档案
            </span>
            <div className="flex gap-1.5 flex-wrap">
              {selectedArchives.map((a) => (
                <span
                  key={a.archive_id}
                  className="text-xs px-2 py-0.5 rounded-full bg-amber-200/25 text-stone-600"
                >
                  {a.entity_name || a.archive_id}
                </span>
              ))}
              {!selectedArchives.length && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-200/12 text-stone-400">
                  无已选档案
                </span>
              )}
            </div>
          </div>

          <SimulationRoster
            sessionId={sessionId}
            agentsOverride={preparedAgents}
            selectedAgentIds={selectedAgentIds}
            onUpdateSelectedAgentIds={setSelectedAgentIds}
            onFocus={onSelectAgent}
          />
        </div>
      )}
    </article>
  );
}
