import { BookMarked, GitBranch, Library, Network } from "lucide-react";

export type ContextChipKind = "assets" | "graph" | "worldline" | "manuscript";

type WriterContextChipProps = {
  kind: ContextChipKind;
  label: string;
  title?: string;
  onClick?: () => void;
};

/**
 * Compact provenance chip for assets / graph / worldline / manuscript context.
 */
export function WriterContextChip({ kind, label, title, onClick }: WriterContextChipProps) {
  const Icon = iconFor(kind);
  const className = `writer-context-chip writer-context-chip-${kind}`;
  if (onClick) {
    return (
      <button type="button" className={className} title={title || label} onClick={onClick} data-kind={kind}>
        <Icon aria-hidden="true" size={12} />
        <span>{label}</span>
      </button>
    );
  }
  return (
    <span className={className} title={title || label} data-kind={kind}>
      <Icon aria-hidden="true" size={12} />
      <span>{label}</span>
    </span>
  );
}

function iconFor(kind: ContextChipKind) {
  switch (kind) {
    case "assets":
      return Library;
    case "graph":
      return Network;
    case "worldline":
      return GitBranch;
    default:
      return BookMarked;
  }
}
