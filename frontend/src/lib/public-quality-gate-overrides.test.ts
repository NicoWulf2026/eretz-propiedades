import { describe, expect, it } from "vitest";
import {
  applyPublicQualityGateOverrides,
  REVIEW_REQUIRED_PUBLIC_GATE_IDS,
} from "@/lib/public-quality-gate-overrides";
import type { PreviewGateEntry } from "@/lib/preview-gate-policy";

describe("nominal public quality gate overrides", () => {
  it("moves every audited visible preserved case to review required", () => {
    const source = new Map<string, PreviewGateEntry>(
      REVIEW_REQUIRED_PUBLIC_GATE_IDS.map((id) => [
        id,
        { classification: "PUBLICABLE_INCOMPLETE", visible: true },
      ]),
    );

    const effective = applyPublicQualityGateOverrides(source);

    expect(REVIEW_REQUIRED_PUBLIC_GATE_IDS).toHaveLength(40);
    expect(new Set(REVIEW_REQUIRED_PUBLIC_GATE_IDS).size).toBe(40);
    for (const id of REVIEW_REQUIRED_PUBLIC_GATE_IDS) {
      expect(effective.get(id)).toEqual({ classification: "REVIEW_REQUIRED", visible: false });
    }
  });

  it("fails closed if the runtime manifest omits any required case", () => {
    expect(() => applyPublicQualityGateOverrides(new Map())).toThrow(
      /missing required property 151674/,
    );
  });
});
