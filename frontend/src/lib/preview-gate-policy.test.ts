import { describe, expect, it } from "vitest";
import {
  countPreviewEntries,
  filterPreviewRows,
  isPreviewClassificationVisible,
  parsePreviewGateRuntimeCsv,
} from "@/lib/preview-gate-policy";

const manifest = `property_id,classification,preview_visible
1,PUBLICABLE_COMPLETE,true
2,PUBLICABLE_INCOMPLETE,true
3,REVIEW_REQUIRED,false
4,SOURCE_UNAVAILABLE,false
5,INVALID,false
`;

describe("preview quality gate policy", () => {
  it("allows only complete and incomplete properties", () => {
    expect(isPreviewClassificationVisible("PUBLICABLE_COMPLETE")).toBe(true);
    expect(isPreviewClassificationVisible("PUBLICABLE_INCOMPLETE")).toBe(true);
    expect(isPreviewClassificationVisible("REVIEW_REQUIRED")).toBe(false);
    expect(isPreviewClassificationVisible("SOURCE_UNAVAILABLE")).toBe(false);
    expect(isPreviewClassificationVisible("INVALID")).toBe(false);
  });

  it("fails closed for direct access, maps and page windows", () => {
    const entries = parsePreviewGateRuntimeCsv(manifest);
    const rows = [1, 2, 3, 4, 5, 999].map((id) => ({ id }));
    expect(filterPreviewRows(rows, entries)).toEqual([{ id: 1 }, { id: 2 }]);
    expect(entries.get("3")?.visible).toBe(false);
    expect(entries.get("999")?.visible).toBeUndefined();
  });

  it("reconciles visible, excluded and classification counts", () => {
    expect(countPreviewEntries(parsePreviewGateRuntimeCsv(manifest))).toEqual({
      counts: {
        INVALID: 1,
        REVIEW_REQUIRED: 1,
        SOURCE_UNAVAILABLE: 1,
        PUBLICABLE_INCOMPLETE: 1,
        PUBLICABLE_COMPLETE: 1,
      },
      visible: 2,
      excluded: 3,
      total: 5,
    });
  });

  it("rejects duplicate or inconsistent manifests", () => {
    expect(() => parsePreviewGateRuntimeCsv(`${manifest}1,PUBLICABLE_COMPLETE,true\n`)).toThrow(/Duplicate/);
    expect(() => parsePreviewGateRuntimeCsv(manifest.replace("3,REVIEW_REQUIRED,false", "3,REVIEW_REQUIRED,true"))).toThrow(/Inconsistent/);
  });
});
