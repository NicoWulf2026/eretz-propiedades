import "server-only";

import { get } from "@vercel/blob";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { gunzipSync } from "node:zlib";
import { isAbsolute, relative, resolve } from "node:path";
import {
  countPreviewEntries,
  parsePreviewGateRuntimeCsv,
  type PreviewGateEntry,
} from "@/lib/preview-gate-policy";
import { applyPublicQualityGateOverrides } from "@/lib/public-quality-gate-overrides";

const MAX_COMPRESSED_BYTES = 2_000_000;
const MAX_MANIFEST_BYTES = 16_000_000;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const FINGERPRINT_PATTERN = /^[a-f0-9]{16}$/;

export type PreviewQualityGate = {
  enabled: boolean;
  version: string;
  visibleCount: number | null;
  totalCount: number | null;
  isVisible: (id: string | number) => boolean;
};

let cached: Promise<PreviewQualityGate> | null = null;

function disabledGate(): PreviewQualityGate {
  return {
    enabled: false,
    version: "disabled",
    visibleCount: null,
    totalCount: null,
    isVisible: () => false,
  };
}

function decodeManifest(payload: Buffer, compressed: boolean) {
  if (payload.byteLength > (compressed ? MAX_COMPRESSED_BYTES : MAX_MANIFEST_BYTES)) {
    throw new Error("Preview gate manifest exceeds the allowed size");
  }
  const decoded = compressed ? gunzipSync(payload, { maxOutputLength: MAX_MANIFEST_BYTES }) : payload;
  if (decoded.byteLength > MAX_MANIFEST_BYTES) throw new Error("Preview gate manifest exceeds the allowed size");
  return decoded.toString("utf8");
}

async function loadFileManifest(configuredPath: string) {
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
  return decodeManifest(await readFile(manifestPath), manifestPath.endsWith(".gz"));
}

async function loadPrivateBlobManifest(pathname: string) {
  if (!pathname.endsWith(".csv.gz")) {
    throw new Error("Private preview gate blob must be a gzip-compressed CSV");
  }
  const expectedChecksum = process.env.ERETZ_PREVIEW_GATE_SHA256?.trim().toLowerCase() ?? "";
  if (!SHA256_PATTERN.test(expectedChecksum)) {
    throw new Error("Private preview gate requires an expected SHA-256 checksum");
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const result = await get(pathname, { access: "private", abortSignal: controller.signal });
    if (!result || result.statusCode !== 200 || !result.stream) {
      throw new Error("Private preview gate blob is unavailable");
    }
    if (result.blob.size && result.blob.size > MAX_COMPRESSED_BYTES) {
      throw new Error("Private preview gate blob exceeds the allowed size");
    }
    const payload = Buffer.from(await new Response(result.stream).arrayBuffer());
    const checksum = createHash("sha256").update(payload).digest("hex");
    if (checksum !== expectedChecksum) {
      throw new Error("Private preview gate checksum mismatch");
    }
    return decodeManifest(payload, true);
  } finally {
    clearTimeout(timeout);
  }
}

function buildGate(content: string, expectedFingerprint = ""): PreviewQualityGate {
  const entries: ReadonlyMap<string, PreviewGateEntry> = applyPublicQualityGateOverrides(
    parsePreviewGateRuntimeCsv(content),
  );
  const counts = countPreviewEntries(entries);
  if (counts.total === 0) throw new Error("Preview gate manifest is empty");
  const version = createHash("sha256").update(content).digest("hex").slice(0, 16);
  if (expectedFingerprint && version !== expectedFingerprint) {
    throw new Error("Preview gate fingerprint mismatch");
  }
  return {
    enabled: true,
    version,
    visibleCount: counts.visible,
    totalCount: counts.total,
    isVisible: (id) => entries.get(String(id))?.visible === true,
  };
}

async function loadGate(): Promise<PreviewQualityGate> {
  if (process.env.ERETZ_PREVIEW_QUALITY_GATE !== "true") return disabledGate();
  const filePath = process.env.ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH?.trim() ?? "";
  const blobPathname = process.env.ERETZ_PREVIEW_GATE_BLOB_PATHNAME?.trim() ?? "";
  if (Boolean(filePath) === Boolean(blobPathname)) {
    throw new Error("Preview gate requires exactly one private manifest source");
  }
  if (filePath) return buildGate(await loadFileManifest(filePath));
  const expectedFingerprint = process.env.ERETZ_PREVIEW_GATE_FINGERPRINT?.trim().toLowerCase() ?? "";
  if (!FINGERPRINT_PATTERN.test(expectedFingerprint)) {
    throw new Error("Private preview gate requires an expected fingerprint");
  }
  return buildGate(await loadPrivateBlobManifest(blobPathname), expectedFingerprint);
}

export function getPreviewQualityGate(): Promise<PreviewQualityGate> {
  if (!cached) cached = loadGate();
  return cached;
}
