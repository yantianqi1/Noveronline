import { cn } from "@/lib/utils";

const STATUS_LABELS: Record<string, string> = {
  canon: "正史",
  candidate: "候选",
  rejected: "已拒绝",
};
const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高置信",
  medium: "中置信",
  low: "低置信",
};

const STATUS_STYLES: Record<string, string> = {
  canon: "bg-amber-600/15 text-amber-800 border border-amber-600/30",
  candidate: "bg-amber-500/15 text-amber-700 border border-amber-500/30",
  rejected: "bg-gray-400/15 text-gray-600 border border-gray-400/25",
};

const CONFIDENCE_STYLES: Record<string, string> = {
  high: "bg-green-600/15 text-green-800 border border-green-600/25",
  medium: "bg-amber-600/15 text-amber-700 border border-amber-600/25",
  low: "bg-red-600/12 text-red-800 border border-red-600/25",
};

interface StatusRibbonProps {
  status?: string;
  confidence?: string;
}

export function StatusRibbon({
  status = "canon",
  confidence = "",
}: StatusRibbonProps) {
  const label =
    confidence && CONFIDENCE_LABELS[confidence]
      ? CONFIDENCE_LABELS[confidence]
      : STATUS_LABELS[status] || status;

  const style =
    confidence && CONFIDENCE_STYLES[confidence]
      ? CONFIDENCE_STYLES[confidence]
      : STATUS_STYLES[status] || STATUS_STYLES.canon;

  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide whitespace-nowrap leading-snug",
        style,
      )}
    >
      {label}
    </span>
  );
}
