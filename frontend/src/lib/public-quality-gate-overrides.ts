import type { PreviewGateEntry } from "@/lib/preview-gate-policy";

export const REVIEW_REQUIRED_PUBLIC_GATE_IDS = [
  "151674", "151676", "151677", "151678", "151679", "151680", "151682", "151683",
  "151684", "151685", "151687", "151688", "151691", "151692", "151693", "151694",
  "151695", "151696", "151697", "151698", "151699", "151700", "151701", "151702",
  "151703", "151704", "151705", "151706", "151707", "151708", "151709", "151710",
  "151711", "151712", "151713", "151714", "151715", "151716", "151717", "151718",
] as const;

export function applyPublicQualityGateOverrides(
  entries: ReadonlyMap<string, PreviewGateEntry>,
) {
  const effective = new Map(entries);
  for (const id of REVIEW_REQUIRED_PUBLIC_GATE_IDS) {
    if (!effective.has(id)) {
      throw new Error(`Public quality gate manifest is missing required property ${id}`);
    }
    effective.set(id, { classification: "REVIEW_REQUIRED", visible: false });
  }
  return effective;
}
