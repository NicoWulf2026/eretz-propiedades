import "server-only";

import { readFileSync } from "node:fs";
import { isAbsolute, relative, resolve } from "node:path";
import {
  countPreviewEntries,
  parsePreviewGateRuntimeCsv,
  type PreviewGateEntry,
} from "@/lib/preview-gate-policy";

type PreviewQualityGate = {
  enabled: boolean;
  entries: ReadonlyMap<string, PreviewGateEntry>;
  visibleCount: number | null;
  totalCount: number | null;
  isVisible: (id: string | number) => boolean;
};

let cached: PreviewQualityGate | null = null;

export function getPreviewQualityGate(): PreviewQualityGate {
  if (cached) return cached;
  if (process.env.ERETZ_PREVIEW_QUALITY_GATE !== "true") {
    cached = {
      enabled: false,
      entries: new Map(),
      visibleCount: null,
      totalCount: null,
      isVisible: () => true,
    };
    return cached;
  }
  const configuredPath = process.env.ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH?.trim();
  if (!configuredPath) throw new Error("Preview gate enabled without ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH");
  const manifestPath = isAbsolute(configuredPath)
    ? configuredPath
    : resolve(/* turbopackIgnore: true */ process.cwd(), configuredPath);
  const relativeToPublic = relative(
    resolve(/* turbopackIgnore: true */ process.cwd(), "public"),
    manifestPath,
  );
  if (relativeToPublic === "" || (!relativeToPublic.startsWith("..") && !isAbsolute(relativeToPublic))) {
    throw new Error("Preview gate manifest must not be stored under public/");
  }
  const entries = parsePreviewGateRuntimeCsv(readFileSync(manifestPath, "utf-8"));
  const counts = countPreviewEntries(entries);
  if (counts.total === 0) throw new Error("Preview gate manifest is empty");
  cached = {
    enabled: true,
    entries,
    visibleCount: counts.visible,
    totalCount: counts.total,
    isVisible: (id) => entries.get(String(id))?.visible === true,
  };
  return cached;
}
