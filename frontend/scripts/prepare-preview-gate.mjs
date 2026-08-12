import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { isAbsolute, relative, resolve } from "node:path";
import { gzipSync } from "node:zlib";

const [inputArgument, outputArgument] = process.argv.slice(2);
if (!inputArgument || !outputArgument) {
  throw new Error("Usage: npm run preview:gate:prepare -- <input.csv> <output.csv.gz>");
}

const input = resolve(inputArgument);
const output = resolve(outputArgument);
if (!output.endsWith(".csv.gz")) throw new Error("Output must end in .csv.gz");
const publicDirectory = resolve(process.cwd(), "public");
const relativeToPublic = relative(publicDirectory, output);
if (relativeToPublic === "" || (!relativeToPublic.startsWith("..") && !isAbsolute(relativeToPublic))) {
  throw new Error("Output must remain outside public/");
}

const content = await readFile(input, "utf8");
const lines = content.trim().split(/\r?\n/);
if (lines.shift() !== "property_id,classification,preview_visible") {
  throw new Error("Invalid preview gate manifest header");
}

const classifications = new Set([
  "INVALID",
  "REVIEW_REQUIRED",
  "SOURCE_UNAVAILABLE",
  "PUBLICABLE_INCOMPLETE",
  "PUBLICABLE_COMPLETE",
]);
const visibleClassifications = new Set(["PUBLICABLE_INCOMPLETE", "PUBLICABLE_COMPLETE"]);
const ids = new Set();
let visible = 0;
for (const [index, line] of lines.entries()) {
  if (!line) continue;
  const [id, classification, previewVisible, ...extra] = line.split(",");
  if (!/^\d+$/.test(id ?? "") || !classifications.has(classification) || extra.length) {
    throw new Error(`Invalid preview gate row ${index + 2}`);
  }
  if (ids.has(id)) throw new Error(`Duplicate preview gate property at row ${index + 2}`);
  ids.add(id);
  const expectedVisible = visibleClassifications.has(classification);
  if ((previewVisible === "true") !== expectedVisible) {
    throw new Error(`Inconsistent preview visibility at row ${index + 2}`);
  }
  if (expectedVisible) visible += 1;
}
if (!ids.size) throw new Error("Preview gate manifest is empty");

const payload = Buffer.from(content.endsWith("\n") ? content : `${content}\n`);
const compressed = gzipSync(payload, { level: 9 });
await writeFile(output, compressed, { flag: "wx" });

console.log(JSON.stringify({
  output,
  version: createHash("sha256").update(content).digest("hex").slice(0, 16),
  entries: ids.size,
  visible,
  sourceBytes: payload.byteLength,
  compressedBytes: compressed.byteLength,
}, null, 2));
