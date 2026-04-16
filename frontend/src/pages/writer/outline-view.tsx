/**
 * OutlineView — chapter outline editor with version history.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ChevronUp, ChevronDown, X, Plus } from "lucide-react";
import type { OutlineScene, OutlineVersionItem } from "./use-writer-state";

interface OutlineViewProps {
  outline: OutlineScene[];
  chapterId: string;
  projectId: string;
  versions: OutlineVersionItem[];
  previewOutline: OutlineScene[] | null;
  onSave: (outline: OutlineScene[], label: string) => void;
  onLoadVersions: (versionId?: string) => void;
  onRestore: () => void;
  onCancelPreview: () => void;
}

export function OutlineView({
  outline,
  versions,
  previewOutline,
  onSave,
  onLoadVersions,
  onRestore,
  onCancelPreview,
}: OutlineViewProps) {
  const [localOutline, setLocalOutline] = React.useState<OutlineScene[]>(() =>
    JSON.parse(JSON.stringify(outline)),
  );
  const [dirty, setDirty] = React.useState(false);
  const [showHistory, setShowHistory] = React.useState(false);
  const [labelInput, setLabelInput] = React.useState("");

  const displayOutline = previewOutline ?? localOutline;

  React.useEffect(() => {
    setLocalOutline(JSON.parse(JSON.stringify(outline)));
    setDirty(false);
  }, [outline]);

  function renumber(arr: OutlineScene[]) {
    arr.forEach((s, i) => {
      s.scene_order = i + 1;
    });
  }

  function moveUp(idx: number) {
    if (idx <= 0) return;
    const arr = [...localOutline];
    const temp = arr[idx]!;
    arr[idx] = arr[idx - 1]!;
    arr[idx - 1] = temp;
    renumber(arr);
    setLocalOutline(arr);
    setDirty(true);
  }

  function moveDown(idx: number) {
    if (idx >= localOutline.length - 1) return;
    const arr = [...localOutline];
    const temp = arr[idx]!;
    arr[idx] = arr[idx + 1]!;
    arr[idx + 1] = temp;
    renumber(arr);
    setLocalOutline(arr);
    setDirty(true);
  }

  function removeScene(idx: number) {
    const arr = localOutline.filter((_, i) => i !== idx);
    renumber(arr);
    setLocalOutline(arr);
    setDirty(true);
  }

  function addScene() {
    setLocalOutline((prev) => [
      ...prev,
      {
        scene_order: prev.length + 1,
        title: "",
        summary: "",
        pov: "",
        key_events: [],
      },
    ]);
    setDirty(true);
  }

  function updateField(idx: number, field: keyof OutlineScene, value: unknown) {
    setLocalOutline((prev) => {
      const arr = [...prev];
      const existing = arr[idx]!;
      arr[idx] = { scene_order: existing.scene_order, title: existing.title, summary: existing.summary, pov: existing.pov, key_events: existing.key_events, [field]: value };
      return arr;
    });
    setDirty(true);
  }

  function updateEvent(sceneIdx: number, eventIdx: number, value: string) {
    setLocalOutline((prev) => {
      const arr = [...prev];
      const existing = arr[sceneIdx]!;
      const events = [...existing.key_events];
      events[eventIdx] = value;
      arr[sceneIdx] = { scene_order: existing.scene_order, title: existing.title, summary: existing.summary, pov: existing.pov, key_events: events };
      return arr;
    });
    setDirty(true);
  }

  function removeEvent(sceneIdx: number, eventIdx: number) {
    setLocalOutline((prev) => {
      const arr = [...prev];
      const existing = arr[sceneIdx]!;
      const events = existing.key_events.filter((_, i) => i !== eventIdx);
      arr[sceneIdx] = { scene_order: existing.scene_order, title: existing.title, summary: existing.summary, pov: existing.pov, key_events: events };
      return arr;
    });
    setDirty(true);
  }

  function addEvent(sceneIdx: number) {
    setLocalOutline((prev) => {
      const arr = [...prev];
      const existing = arr[sceneIdx]!;
      arr[sceneIdx] = {
        scene_order: existing.scene_order,
        title: existing.title,
        summary: existing.summary,
        pov: existing.pov,
        key_events: [...(existing.key_events || []), ""],
      };
      return arr;
    });
    setDirty(true);
  }

  function handleSave() {
    onSave(JSON.parse(JSON.stringify(localOutline)), labelInput);
    setLabelInput("");
  }

  function toggleHistory() {
    setShowHistory((prev) => !prev);
    if (!showHistory) onLoadVersions();
  }

  function formatTime(iso: string) {
    if (!iso) return "";
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  return (
    <div className="flex flex-col gap-2 overflow-y-auto p-3.5">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-bold">章节大纲</h3>
        <span className="text-[13px] text-muted-foreground">
          {displayOutline.length} 个场景
        </span>
        <div className="ml-auto flex items-center gap-2">
          {!previewOutline && (
            <Input
              className="w-[140px]"
              placeholder="版本标注（可选）"
              value={labelInput}
              onChange={(e) => setLabelInput(e.target.value)}
            />
          )}
          {!previewOutline && (
            <Button size="sm" disabled={!dirty} onClick={handleSave}>
              保存大纲
            </Button>
          )}
          <Button
            size="sm"
            variant={showHistory ? "default" : "outline"}
            onClick={toggleHistory}
          >
            历史版本
          </Button>
        </div>
      </div>

      {/* Preview banner */}
      {previewOutline && (
        <div className="flex items-center gap-2.5 rounded-lg border border-primary/30 bg-primary/5 px-3.5 py-2.5 text-[13px] text-primary">
          <span>正在预览历史版本</span>
          <Button size="sm" variant="outline" onClick={onRestore}>
            回退到此版本
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancelPreview}>
            取消预览
          </Button>
        </div>
      )}

      {/* Version history */}
      {showHistory && (
        <div className="flex max-h-[200px] flex-col gap-1 overflow-y-auto rounded-lg border border-border/40 bg-muted/30 p-2.5">
          {versions.length === 0 ? (
            <div className="py-2 text-center text-[13px] text-muted-foreground">
              暂无历史版本
            </div>
          ) : (
            versions.map((ver, idx) => (
              <button
                key={ver.version_id}
                type="button"
                className="flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors hover:bg-muted"
                onClick={() => onLoadVersions(ver.version_id)}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-border text-[11px] font-semibold">
                  {versions.length - idx}
                </span>
                <span className="flex-1 text-left">{ver.label || "自动快照"}</span>
                <span className="text-[11px] text-muted-foreground">
                  {formatTime(ver.created_at)}
                </span>
              </button>
            ))
          )}
        </div>
      )}

      {/* Scene list */}
      <div className="flex flex-col gap-2">
        {displayOutline.map((scene, idx) => (
          <div
            key={idx}
            className="rounded-lg border border-border/40 bg-card p-3"
          >
            <div className="mb-2.5 flex items-center gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-[13px] font-semibold text-primary-foreground">
                {scene.scene_order}
              </span>
              {!previewOutline ? (
                <Input
                  className="flex-1"
                  placeholder="场景标题"
                  value={scene.title}
                  onChange={(e) => updateField(idx, "title", e.target.value)}
                />
              ) : (
                <span className="flex-1 px-2 text-[15px] font-medium">
                  {scene.title}
                </span>
              )}
              {!previewOutline && (
                <div className="flex gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={idx === 0}
                    onClick={() => moveUp(idx)}
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    disabled={idx === displayOutline.length - 1}
                    onClick={() => moveDown(idx)}
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => removeScene(idx)}
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2.5">
              <div className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  POV
                </span>
                {!previewOutline ? (
                  <Input
                    className="w-[160px]"
                    placeholder="视角角色"
                    value={scene.pov}
                    onChange={(e) => updateField(idx, "pov", e.target.value)}
                  />
                ) : (
                  <span className="text-[13px]">{scene.pov || "--"}</span>
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  概述
                </span>
                {!previewOutline ? (
                  <Textarea
                    className="min-h-[50px]"
                    placeholder="场景概述..."
                    value={scene.summary}
                    onChange={(e) =>
                      updateField(idx, "summary", e.target.value)
                    }
                  />
                ) : (
                  <p className="text-[13px]">{scene.summary || "--"}</p>
                )}
              </div>
              <div className="flex min-w-0 basis-full flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  关键事件
                </span>
                <div className="flex flex-col gap-1">
                  {!previewOutline ? (
                    <>
                      {(scene.key_events || []).map((ev, ei) => (
                        <div key={ei} className="flex items-center gap-1">
                          <Input
                            className="flex-1"
                            placeholder="事件描述"
                            value={ev}
                            onChange={(e) =>
                              updateEvent(idx, ei, e.target.value)
                            }
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0"
                            onClick={() => removeEvent(idx, ei)}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-fit"
                        onClick={() => addEvent(idx)}
                      >
                        <Plus className="mr-1 h-3 w-3" /> 事件
                      </Button>
                    </>
                  ) : (
                    (scene.key_events || []).map((ev, ei) => (
                      <div key={ei} className="text-[13px]">
                        {ev}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {!previewOutline && (
        <Button variant="outline" className="mt-2 w-full" onClick={addScene}>
          <Plus className="mr-1 h-4 w-4" /> 添加场景
        </Button>
      )}
    </div>
  );
}
