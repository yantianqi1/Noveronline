/**
 * Parse structured artifacts (action effects, variable effects) from
 * free-form Chinese event summary text.
 *
 * Ported from: src-vue/views/worldline/worldlineEventSummaryParser.js
 */

const ACTION_LABEL = "主动行动 ";
const FOCUS_LABEL = "；本轮围绕";
const VARIABLE_LABEL = "变量触发 ";

export interface ParsedVariableEffect {
  name: string;
  description: string;
}

export interface ParsedActionEffect {
  actor: string;
  action: string;
  intent: string;
  target: string;
}

export interface SummaryArtifacts {
  actionEffects: ParsedActionEffect[];
  variableEffects: ParsedVariableEffect[];
}

export function parseSummaryArtifacts(summary = ""): SummaryArtifacts {
  return {
    actionEffects: parseActionEffects(summary),
    variableEffects: parseVariableEffects(summary),
  };
}

function parseVariableEffects(summary: string): ParsedVariableEffect[] {
  const segment = sliceSegment(summary, VARIABLE_LABEL, [
    `；${ACTION_LABEL}`,
    FOCUS_LABEL,
  ]);
  return splitItems(segment).map((item) => {
    const [name, ...descParts] = item.split(":");
    const trimmedName = name?.trim() || "变量";
    const description = descParts.join(":").trim() || trimmedName;
    return { name: trimmedName, description };
  });
}

function parseActionEffects(summary: string): ParsedActionEffect[] {
  const segment = sliceSegment(summary, ACTION_LABEL, [FOCUS_LABEL]);
  return splitItems(segment)
    .map((item) => item.match(/^(.*?)执行[""](.*?)[""]$/))
    .filter(Boolean)
    .map((match) => ({
      actor: match![1]!.trim(),
      action: match![2]!.trim(),
      intent: "",
      target: "",
    }));
}

function sliceSegment(
  summary: string,
  label: string,
  endings: string[],
): string {
  const start = summary.indexOf(label);
  if (start < 0) return "";
  const contentStart = start + label.length;
  const contentEnd = endings
    .map((e) => summary.indexOf(e, contentStart))
    .filter((i) => i >= 0)
    .sort((a, b) => a - b)[0];
  return summary.slice(contentStart, contentEnd ?? summary.length).trim();
}

function splitItems(segment: string): string[] {
  if (!segment) return [];
  return segment
    .split("；")
    .map((s) => s.trim())
    .filter(Boolean);
}
