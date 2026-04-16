import * as React from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2 } from "lucide-react";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface InspirationResult {
  overview?: string;
  next_beats?: string[];
  conflict_upgrades?: string[];
}

interface InspirationPanelProps {
  sessionId: string;
  inspirationPrompt: string;
  inspirationResult: InspirationResult | null;
  inspirationError: string;
  inspirationBusy: boolean;
  onUpdatePrompt: (value: string) => void;
  onGenerateInspiration: () => void;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function InspirationPanel({
  sessionId,
  inspirationPrompt,
  inspirationResult,
  inspirationError,
  inspirationBusy,
  onUpdatePrompt,
  onGenerateInspiration,
}: InspirationPanelProps) {
  return (
    <article className="border border-stone-200 rounded-lg p-4 bg-white/95">
      <h2 className="text-base font-semibold text-stone-800">剧情灵感面板</h2>
      <p className="text-xs text-stone-500 mt-1">
        输入创作者灵感，结合当前世界线返回下一步剧情推进建议。
      </p>

      <div className="mt-2">
        <label className="block text-sm font-medium text-stone-700 mb-1">
          创作灵感
        </label>
        <Textarea
          value={inspirationPrompt}
          onChange={(e) => onUpdatePrompt(e.target.value)}
          placeholder="例如：我希望主角在两难之间选择一条看似错误但更具戏剧性的道路。"
          rows={4}
        />
      </div>

      <div className="mt-2">
        <Button
          disabled={!sessionId || inspirationBusy}
          onClick={onGenerateInspiration}
        >
          {inspirationBusy && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          生成剧情灵感
        </Button>
      </div>

      {inspirationResult && (
        <div className="mt-2 border border-stone-200 bg-amber-50/70 rounded-lg p-3">
          <div className="font-bold text-sm text-stone-800 mb-1">总览</div>
          <p className="text-sm text-stone-600">
            {inspirationResult.overview || "暂无总览"}
          </p>

          <div className="font-bold text-sm text-stone-800 mt-3 mb-1">
            下一步剧情
          </div>
          {(inspirationResult.next_beats || []).map((item, idx) => (
            <div
              key={`beat_${idx}`}
              className="border-t border-dashed border-stone-200 py-1.5 text-sm text-stone-600"
            >
              {idx + 1}. {item}
            </div>
          ))}

          <div className="font-bold text-sm text-stone-800 mt-3 mb-1">
            冲突升级建议
          </div>
          {(inspirationResult.conflict_upgrades || []).map((item, idx) => (
            <div
              key={`conflict_${idx}`}
              className="border-t border-dashed border-stone-200 py-1.5 text-sm text-stone-600"
            >
              {idx + 1}. {item}
            </div>
          ))}
        </div>
      )}

      {inspirationError && (
        <p className="mt-3 text-sm text-red-700">{inspirationError}</p>
      )}
    </article>
  );
}
