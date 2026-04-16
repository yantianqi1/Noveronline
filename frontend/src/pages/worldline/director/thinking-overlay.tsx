import { Badge } from "@/components/ui/badge";

interface ThinkingOverlayProps {
  visible: boolean;
  thinkingInfo: {
    agent?: string;
    question?: string;
    factors?: string[];
  } | null;
}

export function ThinkingOverlay({
  visible,
  thinkingInfo,
}: ThinkingOverlayProps) {
  if (!visible || !thinkingInfo) return null;

  return (
    <div className="mt-3 flex gap-2.5 items-start rounded-xl bg-amber-50/90 backdrop-blur-sm border border-amber-600/35 shadow-lg p-3 max-h-[360px] overflow-y-auto">
      {/* Animated dots */}
      <div className="flex gap-1.5 items-center pt-1.5 shrink-0">
        <span className="block w-2 h-2 rounded-full bg-amber-600 animate-bounce" />
        <span
          className="block w-2 h-2 rounded-full bg-amber-600 animate-bounce"
          style={{ animationDelay: "0.16s" }}
        />
        <span
          className="block w-2 h-2 rounded-full bg-amber-600 animate-bounce"
          style={{ animationDelay: "0.32s" }}
        />
      </div>
      {/* Body */}
      <div className="flex-1 min-w-0">
        <p className="text-base font-bold text-amber-900 tracking-tight">
          {thinkingInfo.agent || "system"} 正在决策
        </p>
        {thinkingInfo.question && (
          <p className="mt-1.5 text-sm text-stone-600 leading-relaxed break-words">
            {thinkingInfo.question}
          </p>
        )}
        {thinkingInfo.factors && thinkingInfo.factors.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2.5">
            {thinkingInfo.factors.map((factor) => (
              <Badge key={factor} variant="outline" className="text-xs">
                {factor}
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
