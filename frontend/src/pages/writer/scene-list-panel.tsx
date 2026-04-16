/**
 * SceneListPanel — list of scenes for the current chapter.
 * Supports selection, add, and delete.
 */

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";
import type { SceneItem } from "./use-writer-state";

interface SceneListPanelProps {
  scenes: SceneItem[];
  selectedSceneId: string;
  onSelect: (sceneId: string) => void;
  onAdd: () => void;
  onDelete: (sceneId: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  review: "审阅中",
  final: "定稿",
};

const STATUS_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  draft: "secondary",
  review: "default",
  final: "default",
};

export function SceneListPanel({
  scenes,
  selectedSceneId,
  onSelect,
  onAdd,
  onDelete,
}: SceneListPanelProps) {
  return (
    <div className="mt-3 flex flex-col border-t border-border/40 pt-2">
      <div className="flex items-center justify-between px-1 pb-2">
        <span className="text-sm font-semibold">场景列表</span>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onAdd} title="添加场景">
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto">
        {scenes.map((scene) => (
          <div
            key={scene.scene_id}
            className={`group relative cursor-pointer rounded-md border px-3 py-2 text-sm transition-colors ${
              scene.scene_id === selectedSceneId
                ? "border-primary/40 bg-primary/5"
                : "border-border/40 bg-card hover:border-muted-foreground/30"
            }`}
            onClick={() => onSelect(scene.scene_id)}
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-muted-foreground font-semibold">
                {scene.scene_order}
              </span>
              <Badge variant={STATUS_VARIANTS[scene.status] || "outline"} className="text-[10px]">
                {STATUS_LABELS[scene.status] || scene.status}
              </Badge>
            </div>
            <div className="truncate text-[13px] font-medium">
              {scene.title || `场景 ${scene.scene_order}`}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {scene.word_count || 0} 字
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1.5 top-1.5 hidden h-5 w-5 group-hover:flex"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(scene.scene_id);
              }}
              title="删除"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        {scenes.length === 0 && (
          <div className="py-10 text-center text-xs text-muted-foreground">
            暂无场景，点击 + 添加
          </div>
        )}
      </div>
    </div>
  );
}
