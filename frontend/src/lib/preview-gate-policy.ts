export const PREVIEW_GATE_CLASSIFICATIONS = [
  "INVALID",
  "REVIEW_REQUIRED",
  "SOURCE_UNAVAILABLE",
  "PUBLICABLE_INCOMPLETE",
  "PUBLICABLE_COMPLETE",
] as const;

export type PreviewGateClassification = (typeof PREVIEW_GATE_CLASSIFICATIONS)[number];

export type PreviewGateEntry = {
  classification: PreviewGateClassification;
  visible: boolean;
};

const visibleClassifications = new Set<PreviewGateClassification>([
  "PUBLICABLE_COMPLETE",
  "PUBLICABLE_INCOMPLETE",
]);

export function isPreviewClassificationVisible(classification: PreviewGateClassification) {
  return visibleClassifications.has(classification);
}

function isClassification(value: string): value is PreviewGateClassification {
  return (PREVIEW_GATE_CLASSIFICATIONS as readonly string[]).includes(value);
}

export function parsePreviewGateRuntimeCsv(content: string) {
  const lines = content.trim().split(/\r?\n/);
  if (lines.shift() !== "property_id,classification,preview_visible") {
    throw new Error("Invalid preview gate manifest header");
  }
  const entries = new Map<string, PreviewGateEntry>();
  for (const [index, line] of lines.entries()) {
    if (!line) continue;
    const [id, classification, visible, ...extra] = line.split(",");
    const classificationValue = classification ?? "";
    if (!/^\d+$/.test(id ?? "") || !isClassification(classificationValue) || extra.length) {
      throw new Error(`Invalid preview gate manifest row ${index + 2}`);
    }
    if (entries.has(id)) throw new Error(`Duplicate preview gate property ${id}`);
    const expectedVisible = isPreviewClassificationVisible(classificationValue);
    if ((visible === "true") !== expectedVisible) {
      throw new Error(`Inconsistent preview visibility for property ${id}`);
    }
    entries.set(id, { classification: classificationValue, visible: expectedVisible });
  }
  return entries;
}

export function filterPreviewRows<T extends { id: string | number }>(
  rows: T[],
  entries: ReadonlyMap<string, PreviewGateEntry>,
) {
  return rows.filter((row) => entries.get(String(row.id))?.visible === true);
}

export function countPreviewEntries(entries: ReadonlyMap<string, PreviewGateEntry>) {
  const counts = Object.fromEntries(
    PREVIEW_GATE_CLASSIFICATIONS.map((classification) => [classification, 0]),
  ) as Record<PreviewGateClassification, number>;
  let visible = 0;
  for (const entry of entries.values()) {
    counts[entry.classification] += 1;
    if (entry.visible) visible += 1;
  }
  return { counts, visible, excluded: entries.size - visible, total: entries.size };
}
