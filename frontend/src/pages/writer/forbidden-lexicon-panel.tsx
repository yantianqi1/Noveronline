/**
 * ForbiddenLexiconPanel — 禁词 / 禁句资产管理（per-project）。
 *
 * 简洁 CRUD：顶部选择一份资产或新建，表格编辑 entries，保存即生效。
 * 资产存到 assets 表（asset_type='forbidden_lexicon'），供 book_run 的
 * LEXICON_AUDIT 阶段调用。
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Save, Trash2 } from "lucide-react";
import {
  deleteForbiddenLexicon,
  listForbiddenLexicons,
  upsertForbiddenLexicon,
  type ForbiddenLexiconEntry,
} from "@/api/writer-agent";

interface ForbiddenLexiconPanelProps {
  projectId: string;
}

const DEFAULT_ENTRY: ForbiddenLexiconEntry = {
  pattern: "",
  match_type: "literal",
  category: "word",
  severity: "block",
  note: "",
};

export function ForbiddenLexiconPanel({ projectId }: ForbiddenLexiconPanelProps) {
  const [lexicons, setLexicons] = React.useState<any[]>([]);
  const [currentId, setCurrentId] = React.useState<string | "__new__">("__new__");
  const [title, setTitle] = React.useState("");
  const [entries, setEntries] = React.useState<ForbiddenLexiconEntry[]>([]);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (projectId) reload();
  }, [projectId]);

  async function reload() {
    const resp = await listForbiddenLexicons(projectId, true);
    if (resp.success) {
      setLexicons((resp.data as any[]) || []);
    }
  }

  function selectLexicon(id: string | null) {
    const actualId = id || "__new__";
    setCurrentId(actualId);
    if (actualId === "__new__") {
      setTitle("");
      setEntries([]);
      return;
    }
    const asset = lexicons.find((l) => l.asset_id === actualId);
    if (!asset) return;
    setTitle(asset.title || "");
    const raw = asset.payload?.entries || [];
    setEntries(
      raw.map((e: any) =>
        typeof e === "string" ? { ...DEFAULT_ENTRY, pattern: e } : { ...DEFAULT_ENTRY, ...e },
      ),
    );
  }

  function addEntry() {
    setEntries((prev) => [...prev, { ...DEFAULT_ENTRY }]);
  }

  function removeEntry(index: number) {
    setEntries((prev) => prev.filter((_, i) => i !== index));
  }

  function updateEntry(index: number, patch: Partial<ForbiddenLexiconEntry>) {
    setEntries((prev) =>
      prev.map((e, i) => (i === index ? { ...e, ...patch } : e)),
    );
  }

  async function handleSave() {
    if (!title.trim() && currentId === "__new__") {
      alert("请填写标题");
      return;
    }
    const payload = entries.filter((e) => e.pattern.trim());
    setSaving(true);
    try {
      const resp = await upsertForbiddenLexicon({
        project_id: projectId,
        asset_id: currentId === "__new__" ? null : currentId,
        title: title.trim(),
        entries: payload,
      });
      if (resp.success) {
        await reload();
        const created = resp.data as { asset_id?: string } | undefined;
        if (currentId === "__new__" && created?.asset_id) {
          setCurrentId(created.asset_id);
        }
      } else {
        alert(`保存失败：${resp.error || "未知错误"}`);
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (currentId === "__new__") return;
    if (!confirm("确认删除这份禁词表？")) return;
    const resp = await deleteForbiddenLexicon(currentId, projectId);
    if (resp.success) {
      setCurrentId("__new__");
      setTitle("");
      setEntries([]);
      await reload();
    }
  }

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-base">
          <span>禁用词 / 禁用句库</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => selectLexicon("__new__")}>
              新建
            </Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              <Save className="w-3 h-3 mr-1" />
              保存
            </Button>
            {currentId !== "__new__" && (
              <Button size="sm" variant="destructive" onClick={handleDelete}>
                <Trash2 className="w-3 h-3" />
              </Button>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <Label className="text-xs">选择资产</Label>
          <Select value={currentId} onValueChange={selectLexicon}>
            <SelectTrigger>
              <SelectValue placeholder="选择或新建禁词表" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__new__">＋ 新建禁词表</SelectItem>
              {lexicons.map((l) => (
                <SelectItem key={l.asset_id} value={l.asset_id}>
                  {l.title} ({l.payload?.entries?.length ?? "?"} 条)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label className="text-xs">标题</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="如：通用禁词 / 本书风格禁用"
          />
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <Label className="text-xs">规则（共 {entries.length} 条）</Label>
            <Button size="sm" variant="ghost" onClick={addEntry}>
              <Plus className="w-3 h-3 mr-1" /> 添加
            </Button>
          </div>
          <div className="space-y-1 max-h-96 overflow-y-auto">
            {entries.map((entry, i) => (
              <div key={i} className="grid grid-cols-[1fr_auto_auto_auto_2fr_auto] gap-1 items-center text-xs">
                <Input
                  value={entry.pattern}
                  onChange={(e) => updateEntry(i, { pattern: e.target.value })}
                  placeholder="禁词 / 正则 / 短语"
                  className="h-7 text-xs"
                />
                <Select
                  value={entry.match_type}
                  onValueChange={(v: any) => updateEntry(i, { match_type: v })}
                >
                  <SelectTrigger className="h-7 text-xs w-20">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="literal">字面</SelectItem>
                    <SelectItem value="regex">正则</SelectItem>
                    <SelectItem value="phrase">短语</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={entry.category}
                  onValueChange={(v: any) => updateEntry(i, { category: v })}
                >
                  <SelectTrigger className="h-7 text-xs w-16">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="word">词</SelectItem>
                    <SelectItem value="sentence">句</SelectItem>
                    <SelectItem value="stylistic">文风</SelectItem>
                  </SelectContent>
                </Select>
                <Select
                  value={entry.severity}
                  onValueChange={(v: any) => updateEntry(i, { severity: v })}
                >
                  <SelectTrigger className="h-7 text-xs w-16">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="block">必改</SelectItem>
                    <SelectItem value="warn">警告</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  value={entry.note || ""}
                  onChange={(e) => updateEntry(i, { note: e.target.value })}
                  placeholder="备注"
                  className="h-7 text-xs"
                />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeEntry(i)}
                  className="h-7 w-7 p-0"
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
            ))}
            {entries.length === 0 && (
              <div className="text-xs text-muted-foreground text-center py-4">
                暂无规则，点击 + 添加
              </div>
            )}
          </div>
        </div>

        <div className="text-[10px] text-muted-foreground">
          · 字面匹配做全字符串比对；正则支持完整 PCRE；短语模式将空格视为"任意空白"。
          · 必改命中会在 book_run 的 LEXICON_AUDIT 阶段被 rewrite_span 工具自动改写。
        </div>
      </CardContent>
    </Card>
  );
}
