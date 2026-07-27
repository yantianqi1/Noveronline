import { cn } from "@/lib/utils";

/**
 * CharacterSeal — the 角色印章 motif shared across the Worldline roster, the
 * Character Console descend/stage, and the dossier header.
 *
 * A near-square vermilion (or ink) block carrying the character's first
 * hanzi in the brush-calligraphy face. It is the site's most recognizable
 * signature: the same stamp appears on asset character cards and graph nodes.
 * Not a circular photo avatar — a seal, like a name chop pressed into paper.
 */

type SealTone = "vermilion" | "ink" | "gold";
type SealSize = "sm" | "md" | "lg" | "xl";

const SIZE_CLASSES: Record<SealSize, string> = {
  sm: "size-7 text-md rounded-control",
  md: "size-9 text-lg rounded-control",
  lg: "size-12 text-xl rounded-control",
  xl: "size-16 text-display rounded-control",
};

const TONE_CLASSES: Record<SealTone, string> = {
  vermilion: "bg-accent-wash text-accent ring-1 ring-inset ring-accent/25",
  ink: "bg-ink/[0.06] text-ink ring-1 ring-inset ring-ink/15",
  // Gold is reserved for candidate state — a seal for a character the
  // simulation proposed but the author has not confirmed yet.
  gold: "bg-gold/10 text-gold ring-1 ring-inset ring-gold/40",
};

function firstGlyph(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "？";
  return Array.from(trimmed)[0] ?? "？";
}

export function CharacterSeal({
  name,
  tone = "vermilion",
  size = "md",
  className,
  title,
}: {
  /** Character display name; the seal shows its first glyph. */
  name: string;
  tone?: SealTone;
  size?: SealSize;
  className?: string;
  /** Accessible label; defaults to the name. */
  title?: string;
}) {
  return (
    <span
      role="img"
      aria-label={title ?? name}
      title={title ?? name}
      className={cn(
        "grid shrink-0 select-none place-items-center font-brush",
        SIZE_CLASSES[size],
        TONE_CLASSES[tone],
        className,
      )}
    >
      {firstGlyph(name)}
    </span>
  );
}
