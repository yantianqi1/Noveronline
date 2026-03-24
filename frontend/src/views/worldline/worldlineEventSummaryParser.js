const ACTION_LABEL = "主动行动 ";
const FOCUS_LABEL = "；本轮围绕";
const VARIABLE_LABEL = "变量触发 ";

export function parseSummaryArtifacts(summary = "") {
  return {
    actionEffects: parseActionEffects(summary),
    variableEffects: parseVariableEffects(summary),
  };
}

function parseVariableEffects(summary) {
  const segment = sliceSegment(summary, VARIABLE_LABEL, [`；${ACTION_LABEL}`, FOCUS_LABEL]);
  return splitItems(segment).map((item) => {
    const [name, ...descriptionParts] = item.split(":");
    const trimmedName = name?.trim() || "变量";
    const description = descriptionParts.join(":").trim() || trimmedName;
    return { name: trimmedName, description };
  });
}

function parseActionEffects(summary) {
  const segment = sliceSegment(summary, ACTION_LABEL, [FOCUS_LABEL]);
  return splitItems(segment)
    .map((item) => item.match(/^(.*?)执行[“"](.*?)[”"]$/))
    .filter(Boolean)
    .map((match) => ({
      actor: match[1].trim(),
      action: match[2].trim(),
      intent: "",
      target: "",
    }));
}

function sliceSegment(summary, label, endings) {
  const start = summary.indexOf(label);
  if (start < 0) {
    return "";
  }
  const contentStart = start + label.length;
  const contentEnd = endings
    .map((ending) => summary.indexOf(ending, contentStart))
    .filter((index) => index >= 0)
    .sort((left, right) => left - right)[0];
  return summary.slice(contentStart, contentEnd ?? summary.length).trim();
}

function splitItems(segment) {
  if (!segment) {
    return [];
  }
  return segment.split("；").map((item) => item.trim()).filter(Boolean);
}
