/**
 * PresetEditor — modal dialog for creating/editing writing presets.
 */

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import type { PresetItem } from "./use-writer-state";

interface PresetEditorProps {
  visible: boolean;
  preset: PresetItem | null;
  onSave: (data: Record<string, unknown>) => void;
  onClose: () => void;
}

export function PresetEditor({ visible, preset, onSave, onClose }: PresetEditorProps) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [systemPrompt, setSystemPrompt] = React.useState("");

  const isNew = !preset;

  React.useEffect(() => {
    if (preset) {
      setName(preset.name || "");
      setDescription(preset.description || "");
      setSystemPrompt(preset.system_prompt || "");
    } else {
      setName("");
      setDescription("");
      setSystemPrompt("");
    }
  }, [preset]);

  function handleSave() {
    if (!name.trim() || !systemPrompt.trim()) return;
    onSave({
      name,
      description,
      system_prompt: systemPrompt,
      preset_id: preset?.preset_id || null,
    });
  }

  return (
    <Dialog open={visible} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{isNew ? "新建写作预设" : "编辑写作预设"}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-2">
          <div className="space-y-1.5">
            <Label>预设名称</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：仙侠凝练风"
            />
          </div>
          <div className="space-y-1.5">
            <Label>说明</Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="简要说明此预设的风格特点"
            />
          </div>
          <div className="space-y-1.5">
            <Label>写作提示词 (System Prompt)</Label>
            <Textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="输入写作层的系统提示词..."
              className="min-h-[200px]"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
