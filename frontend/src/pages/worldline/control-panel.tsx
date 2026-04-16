import * as React from "react";
import { Plus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ArchiveLibraryPicker } from "@/components/archive-library-picker";
import type { ArchiveEntry } from "@/types/archive";
import { AutoTaskPanel } from "./auto-task-panel";
import { VariableLockPanel } from "./variable-lock-panel";
import {
  buildWorldlineSessionSummary,
  resolveWorldlineSessionStatus,
  type SessionStatus,
} from "./control-panel-view-model";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface Archive {
  archive_id: string;
  entity_name?: string;
  [key: string]: unknown;
}

interface WorldVariable {
  variable_id: string;
  name: string;
  description: string;
  impact_axis?: string;
  source?: string;
}

interface TaskSnapshot {
  branch_title?: string;
  status?: string;
  progress?: number;
  error?: string;
  message?: string;
  stop_reason?: string;
}

interface ControlPanelProps {
  selectedArchives: Archive[];
  archiveProjectFilter: string;
  showArchivePicker: boolean;
  sessionLabel: string;
  variablesText: string;
  singleVariable: string;
  createMode: string;
  goalText: string;
  maxSteps: number;
  sessionId: string;
  sessionScope: string;
  task: TaskSnapshot | null;
  feedback: string;
  error: string;
  busy: boolean;
  worldVariables: WorldVariable[];
  lockedVariableIds: Set<string>;
  onUpdateSelectedArchives: (archives: Archive[]) => void;
  onUpdateArchiveProjectFilter: (filter: string) => void;
  onUpdateSessionLabel: (value: string) => void;
  onUpdateVariablesText: (value: string) => void;
  onUpdateSingleVariable: (value: string) => void;
  onUpdateCreateMode: (value: string) => void;
  onUpdateGoalText: (value: string) => void;
  onUpdateMaxSteps: (value: number) => void;
  onCreateSession: () => void;
  onStartAutoEvolve: () => void;
  onAdvanceStep: () => void;
  onInjectVariable: () => void;
  onToggleLock: (variableId: string) => void;
  onLockAll: () => void;
  onUnlockAll: () => void;
}

/* ================================================================ */
/*  Constants                                                        */
/* ================================================================ */

const CREATE_MODE_OPTIONS = [
  { value: "manual", label: "手动", copy: "逐步推进" },
  { value: "first_round", label: "首轮自动", copy: "先跑 1 步" },
  { value: "continuous", label: "持续自动", copy: "按步数上限推进" },
] as const;

const STATUS_BADGE_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  ok: "default",
  warn: "secondary",
  danger: "destructive",
  default: "outline",
};

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function ControlPanel({
  selectedArchives,
  archiveProjectFilter,
  showArchivePicker,
  sessionLabel,
  variablesText,
  singleVariable,
  createMode,
  goalText,
  maxSteps,
  sessionId,
  sessionScope,
  task,
  feedback,
  error,
  busy,
  worldVariables,
  lockedVariableIds,
  onUpdateSelectedArchives,
  onUpdateArchiveProjectFilter,
  onUpdateSessionLabel,
  onUpdateVariablesText,
  onUpdateSingleVariable,
  onUpdateCreateMode,
  onUpdateGoalText,
  onUpdateMaxSteps,
  onCreateSession,
  onStartAutoEvolve,
  onAdvanceStep,
  onInjectVariable,
  onToggleLock,
  onLockAll,
  onUnlockAll,
}: ControlPanelProps) {
  const sessionStatus: SessionStatus = resolveWorldlineSessionStatus({
    sessionId,
    error,
  });
  const sessionSummary = buildWorldlineSessionSummary({
    selectedArchives,
    variablesText,
    sessionId,
    sessionScope,
  });

  // Expose `variablesText` (newline-joined string) as a list of rows so each
  // variable gets its own input. We sync back through `onUpdateVariablesText`
  // with `\n`-joined values, so downstream `parseVariables` keeps working.
  const variableLines = React.useMemo(
    () => variablesText.split("\n"),
    [variablesText],
  );

  function updateVariableAt(index: number, value: string) {
    const next = [...variableLines];
    next[index] = value;
    onUpdateVariablesText(next.join("\n"));
  }

  function addVariable() {
    onUpdateVariablesText([...variableLines, ""].join("\n"));
  }

  function removeVariableAt(index: number) {
    const next = variableLines.filter((_, i) => i !== index);
    onUpdateVariablesText(next.join("\n"));
  }

  const showContinuousSettings = createMode === "continuous";
  const createActionLabel =
    createMode === "manual"
      ? "启动世界线整备"
      : "整备完成后进入自动推演";

  const launchpadSectionIndex = showArchivePicker
    ? "02 / 启动整备"
    : "01 / 启动整备";

  const runtimeBase = (showArchivePicker ? 2 : 1) + (task || createMode !== "manual" ? 1 : 0);
  const runtimeSectionIndex = `${String(runtimeBase + 1).padStart(2, "0")} / 会话控制`;
  const lockSectionIndex = `${String(runtimeBase + 2).padStart(2, "0")} / 变量锁定`;

  return (
    <article className="border border-stone-200 rounded-lg bg-white/95 flex flex-col">
      {/* Header */}
      <header className="px-4 py-3 flex justify-between items-start gap-3">
        <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
          WORLDLINE
        </p>
        <Badge variant={STATUS_BADGE_VARIANTS[sessionStatus.tone] || "outline"}>
          {sessionStatus.label}
        </Badge>
      </header>

      {/* Source section (fallback for two-col/stacked) */}
      {showArchivePicker && (
        <section className="px-4 py-3 border-t border-amber-300/20 bg-gradient-to-b from-amber-50/85 to-white/95">
          <div className="flex flex-wrap items-baseline gap-1 gap-x-2">
            <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
              01 / 源档案
            </p>
            <h3 className="text-[0.95rem] font-semibold m-0">选择角色与组织</h3>
          </div>
          <div className="mt-2 min-h-[400px]">
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
        </section>
      )}

      {/* Launchpad section */}
      <section className="px-4 py-3 flex flex-col gap-3 border-t border-amber-300/20 bg-gradient-to-b from-amber-50/85 to-white/95">
        <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
          {launchpadSectionIndex}
        </p>

        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-3">
          {sessionSummary.map((item) => (
            <div
              key={item.label}
              className="flex flex-col justify-between gap-0.5 min-h-[48px] p-2.5 px-3 rounded-lg border border-stone-200 bg-white/95"
            >
              <span className="text-xs text-stone-400">{item.label}</span>
              <strong className="text-[0.95rem] font-semibold text-stone-800">
                {item.value}
              </strong>
            </div>
          ))}
          <div className="flex flex-col justify-between gap-0.5 min-h-[48px] p-2.5 px-3 rounded-lg border border-stone-200 bg-white/95">
            <span className="text-xs text-stone-400">会话编号</span>
            <strong className="font-mono text-xs leading-relaxed break-all text-stone-800">
              {sessionId || "未创建会话"}
            </strong>
          </div>
        </div>

        {/* Session label */}
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1">
            会话名称{" "}
            <span className="text-xs text-stone-400 font-normal">
              （方便后续识别）
            </span>
          </label>
          <Input
            value={sessionLabel}
            onChange={(e) => onUpdateSessionLabel(e.target.value)}
            placeholder="例如：主线剧情推演、第三章分支"
          />
        </div>

        {/* Variables list */}
        <div>
          <label className="block text-sm font-medium text-stone-700 mb-1.5">
            初始变量{" "}
            <span className="text-xs text-stone-400 font-normal">
              （每行一个，空行会自动忽略）
            </span>
          </label>
          <div className="flex flex-col gap-1.5">
            {variableLines.map((line, idx) => (
              <div
                key={idx}
                className="group flex items-center gap-2 rounded-lg border border-stone-200 bg-white/95 pl-2.5 pr-2 py-1 transition-colors focus-within:border-amber-400/60 focus-within:bg-amber-50/40"
              >
                <span className="font-mono text-[0.7rem] text-amber-700/80 tracking-widest shrink-0 w-6">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <input
                  type="text"
                  value={line}
                  onChange={(e) => updateVariableAt(idx, e.target.value)}
                  placeholder={
                    idx === 0
                      ? "例如：主要势力提前结盟"
                      : "继续添加一个变量…"
                  }
                  className="flex-1 min-w-0 h-7 bg-transparent border-0 outline-none text-sm text-stone-800 placeholder:text-stone-400"
                />
                {variableLines.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeVariableAt(idx)}
                    aria-label="删除此变量"
                    className="shrink-0 p-1 text-stone-300 hover:text-red-500 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={addVariable}
              className="self-start inline-flex items-center gap-1 px-2 py-1 text-xs text-amber-700 hover:text-amber-800 hover:bg-amber-50/70 rounded transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              添加变量
            </button>
          </div>
        </div>

        {/* Mode chips */}
        <div className="grid grid-cols-3 gap-2">
          {CREATE_MODE_OPTIONS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={cn(
                "border rounded-lg p-2.5 text-left flex flex-col gap-1 cursor-pointer transition-all",
                "border-stone-200 bg-amber-50/95 hover:border-amber-400/50",
                createMode === item.value &&
                  "border-amber-500/50 bg-amber-100/90",
              )}
              onClick={() => onUpdateCreateMode(item.value)}
            >
              <strong className="text-sm">{item.label}</strong>
              <span className="text-xs text-stone-500">{item.copy}</span>
            </button>
          ))}
        </div>

        {/* Continuous settings */}
        {showContinuousSettings && (
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-stone-700">
                最大自动步数
              </label>
              <Input
                type="number"
                min={1}
                value={maxSteps}
                onChange={(e) => onUpdateMaxSteps(Number(e.target.value) || 6)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-stone-700">
                最终条件
              </label>
              <Input
                value={goalText}
                onChange={(e) => onUpdateGoalText(e.target.value)}
                placeholder="例如：主角公开宗门证据"
              />
            </div>
          </div>
        )}
        {!showContinuousSettings && createMode === "first_round" && (
          <p className="text-xs text-stone-500 mt-1">
            首轮固定 1 步，达成目标或收束时自动停止。
          </p>
        )}

        {/* Create button */}
        <div className="p-3 rounded-lg border border-amber-400/30 bg-gradient-to-b from-amber-50/95 to-amber-100/90 shadow-sm">
          <Button
            disabled={busy || !selectedArchives.length}
            onClick={onCreateSession}
            className="w-full"
          >
            {createActionLabel}
          </Button>
          {sessionId && (
            <p className="font-mono text-[0.68rem] text-stone-400 mt-1.5 m-0">
              当前会话范围：{sessionScope || "项目范围"}
            </p>
          )}
        </div>
      </section>

      {/* Auto task panel */}
      {task && <AutoTaskPanel task={task} />}

      {/* Runtime section */}
      {sessionId && (
        <section className="px-4 py-3 flex flex-col gap-3 border-t border-amber-300/20 bg-gradient-to-b from-amber-50/85 to-white/95">
          <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
            {runtimeSectionIndex}
          </p>

          <div className="grid gap-3">
            <div className="flex gap-2 p-3 rounded-lg border border-stone-200 bg-white/95">
              <Button disabled={!sessionId || busy} onClick={onAdvanceStep}>
                推进一步
              </Button>
              {createMode !== "manual" && (
                <Button
                  variant="outline"
                  disabled={!sessionId || busy}
                  onClick={onStartAutoEvolve}
                >
                  按当前模式自动推进
                </Button>
              )}
            </div>

            <div className="p-3 rounded-lg border border-stone-200 bg-white/95">
              <label className="block text-sm font-medium text-stone-700 mb-1">
                临时注入变量
              </label>
              <div className="flex gap-2 items-stretch">
                <Input
                  value={singleVariable}
                  onChange={(e) => onUpdateSingleVariable(e.target.value)}
                  placeholder="例如：二号角色获得预知能力"
                  className="flex-1"
                />
                <Button
                  disabled={!sessionId || busy}
                  onClick={onInjectVariable}
                >
                  注入变量
                </Button>
              </div>
              <p className="text-xs text-stone-500 mt-1 m-0">
                中途注入新扰动条件
              </p>
            </div>
          </div>

          {/* Variable lock panel */}
          {worldVariables.length > 0 && (
            <VariableLockPanel
              sectionIndex={lockSectionIndex}
              worldVariables={worldVariables}
              lockedVariableIds={lockedVariableIds}
              onToggleLock={onToggleLock}
              onLockAll={onLockAll}
              onUnlockAll={onUnlockAll}
            />
          )}

          {/* Feedback */}
          <div
            className={cn(
              "flex flex-col gap-1.5 p-3 rounded-lg border",
              error
                ? "border-red-500/20 bg-red-50/50"
                : "border-blue-500/15 bg-blue-50/30",
            )}
          >
            <span className="font-mono text-[0.68rem] text-stone-400 tracking-widest">
              STATUS
            </span>
            <p
              className={cn(
                "text-sm m-0",
                error ? "text-red-700" : "text-stone-600",
              )}
            >
              {error || feedback}
            </p>
          </div>
        </section>
      )}
    </article>
  );
}
