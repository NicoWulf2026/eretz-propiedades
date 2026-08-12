import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@vercel/blob", () => ({ get: vi.fn() }));

afterEach(() => {
  delete process.env.ERETZ_PREVIEW_QUALITY_GATE;
  delete process.env.ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH;
  delete process.env.ERETZ_PREVIEW_GATE_BLOB_PATHNAME;
  delete process.env.ERETZ_PREVIEW_GATE_SHA256;
  delete process.env.ERETZ_PREVIEW_GATE_FINGERPRINT;
  vi.resetModules();
});

describe("preview quality gate runtime", () => {
  it("fails closed while the gate is disabled", async () => {
    const { getPreviewQualityGate } = await import("@/lib/preview-quality-gate");
    const gate = await getPreviewQualityGate();
    expect(gate.enabled).toBe(false);
    expect(gate.isVisible(1)).toBe(false);
  });

  it("requires exactly one private manifest source", async () => {
    process.env.ERETZ_PREVIEW_QUALITY_GATE = "true";
    const { getPreviewQualityGate } = await import("@/lib/preview-quality-gate");
    await expect(getPreviewQualityGate()).rejects.toThrow(/exactly one private manifest source/);
  });

  it("requires an expected fingerprint for a private Blob source", async () => {
    process.env.ERETZ_PREVIEW_QUALITY_GATE = "true";
    process.env.ERETZ_PREVIEW_GATE_BLOB_PATHNAME = "quality-gate/version/preview-gate.csv.gz";
    const { getPreviewQualityGate } = await import("@/lib/preview-quality-gate");
    await expect(getPreviewQualityGate()).rejects.toThrow(/expected fingerprint/);
  });
});
