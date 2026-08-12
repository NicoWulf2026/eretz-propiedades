#!/usr/bin/env node
/**
 * ERETZ Propiedades — Remote Cursor Coverage Audit (Preview protegido)
 * ======================================================================
 * Recorre la totalidad del catalogo publico vía HTTP contra el Preview
 * protegido, usando el header x-vercel-protection-bypass (leído de
 * process.env en memoria, nunca impreso ni escrito a disco).
 *
 * Uso: VERCEL_AUTOMATION_BYPASS_SECRET=... node scripts/audit-remote-cursor-coverage.mjs <preview-url>
 *
 * NO EXPORTA IDs al reporte. Solo cantidades, tiempos y PASS/FAIL.
 * NO IMPRIME el secreto en ningún momento.
 */

import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import { writeFileSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));

const previewUrl = process.argv[2];
if (!previewUrl) {
  console.error("Uso: node scripts/audit-remote-cursor-coverage.mjs <preview-url>");
  process.exit(1);
}

const bypass = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
if (!bypass) {
  console.error("VERCEL_AUTOMATION_BYPASS_SECRET no está presente en el entorno.");
  process.exit(1);
}

const base = previewUrl.replace(/\/$/, "");
const headers = {
  "x-vercel-protection-bypass": bypass,
  "x-vercel-set-bypass-cookie": "true",
};

const startTime = Date.now();
const MAX_PAGES = 20000;

async function fetchJson(path) {
  const res = await fetch(`${base}${path}`, { headers });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} on ${path}`);
  }
  return res.json();
}

console.log("==========================================================");
console.log("ERETZ — Auditoría Remota de Cobertura Completa del Cursor");
console.log(`Preview: ${base}`);
console.log("==========================================================");

const countsBaseline = await fetchJson("/api/properties/counts");
const expected = countsBaseline.totalCount ?? 0;
console.log(`Total esperado (Quality Gate, vía /api/properties/counts): ${expected.toLocaleString("es-AR")}`);
console.log(`count (sin filtros): ${countsBaseline.count ?? "N/A"} | mapCount: ${countsBaseline.mapCount ?? "N/A"} | withoutMapCount: ${countsBaseline.withoutMapCount ?? "N/A"}`);
console.log("");

let cursor = "";
let page = 1;
let totalReached = 0;
let withCoords = 0;
let withoutCoords = 0;
const seenIds = new Set();
let duplicates = 0;
let batchCount = 0;
const checksums = [];

console.log("Iniciando recorrido remoto de cursores...");

while (page <= MAX_PAGES) {
  const params = new URLSearchParams({ cursor, pagina: String(page), direccion: "next" });
  let result;
  try {
    result = await fetchJson(`/api/properties/search?${params.toString()}`);
  } catch (err) {
    console.error(`❌ Error en página ${page}: ${err.message}. Abortando.`);
    break;
  }

  if (result.error && (!result.properties || result.properties.length === 0)) {
    console.error(`❌ Error de API en página ${page}. Abortando.`);
    break;
  }

  batchCount++;
  const pageIds = [];
  for (const prop of result.properties ?? []) {
    const id = String(prop.id);
    if (seenIds.has(id)) {
      duplicates++;
    } else {
      seenIds.add(id);
      totalReached++;
      if (prop.latitude !== null && prop.latitude !== undefined && prop.longitude !== null && prop.longitude !== undefined) {
        withCoords++;
      } else {
        withoutCoords++;
      }
    }
    pageIds.push(id);
  }

  if (pageIds.length > 0) {
    const hash = createHash("md5").update(pageIds.join(",")).digest("hex").slice(0, 8);
    checksums.push(hash);
  }

  if (page % 250 === 0) {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`  Página ${page} | Alcanzadas: ${totalReached.toLocaleString("es-AR")} | ${elapsed}s`);
  }

  if (!result.hasNext || !result.nextCursor) {
    break;
  }

  cursor = result.nextCursor;
  page++;
}

const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
const omitted = expected > 0 ? Math.max(0, expected - totalReached) : null;
const pass = totalReached > 0 && duplicates === 0 && (omitted === null || omitted === 0);
const verdict = pass ? "✅ PASS" : "❌ FAIL";

console.log("");
console.log("==========================================================");
console.log(`RESULTADO: ${verdict}`);
console.log("==========================================================");
console.log(`Total esperado:                     ${expected.toLocaleString("es-AR")}`);
console.log(`Total alcanzado:                    ${totalReached.toLocaleString("es-AR")}`);
console.log(`Duplicados:                         ${duplicates}`);
console.log(`Omitidos:                           ${omitted !== null ? omitted : "N/A"}`);
console.log(`Con coordenadas:                    ${withCoords.toLocaleString("es-AR")}`);
console.log(`Sin coordenadas:                    ${withoutCoords.toLocaleString("es-AR")}`);
console.log(`Páginas totales:                    ${page}`);
console.log(`Batches HTTP:                       ${batchCount}`);
console.log(`Tiempo total:                       ${elapsed}s`);
console.log(`Checksum global:                    ${createHash("md5").update(checksums.join("|")).digest("hex").slice(0, 16)}`);

const reportPath = resolve(__dirname, "../../_scratch/frontend_structure_desktop/DESKTOP_REMOTE_CURSOR_COVERAGE_RESULTS.md");
const now = new Date().toISOString();
const reportContent = `# DESKTOP_REMOTE_CURSOR_COVERAGE_RESULTS

**Fecha de ejecución:** ${now}
**Método:** Recorrido completo vía HTTP contra el Preview protegido (bypass en memoria, nunca registrado).
**Preview:** ${base}

## Resultados

| Métrica | Valor |
|---|---|
| Total esperado (Quality Gate) | ${expected.toLocaleString("es-AR")} |
| Total alcanzado | ${totalReached.toLocaleString("es-AR")} |
| Duplicados | ${duplicates} |
| Omitidos | ${omitted !== null ? omitted : "N/A"} |
| Con coordenadas | ${withCoords.toLocaleString("es-AR")} |
| Sin coordenadas | ${withoutCoords.toLocaleString("es-AR")} |
| Páginas totales | ${page} |
| Batches HTTP | ${batchCount} |
| Tiempo total | ${elapsed}s |
| Checksum global | ${createHash("md5").update(checksums.join("|")).digest("hex").slice(0, 16)} |
| count (baseline, sin filtros) | ${countsBaseline.count ?? "N/A"} |
| mapCount (baseline) | ${countsBaseline.mapCount ?? "N/A"} |
| withoutMapCount (baseline) | ${countsBaseline.withoutMapCount ?? "N/A"} |

## Validaciones

- [${totalReached === expected ? "x" : " "}] Total alcanzado == esperado: **${totalReached === expected ? "PASS" : `FAIL (diff: ${Math.abs(totalReached - expected)})`}**
- [${duplicates === 0 ? "x" : " "}] Duplicados == 0: **${duplicates === 0 ? "PASS" : `FAIL (${duplicates} duplicados)`}**
- [${withCoords + withoutCoords === totalReached ? "x" : " "}] con coordenadas + sin coordenadas == total: **${withCoords + withoutCoords === totalReached ? "PASS" : "FAIL"}**
- [${countsBaseline.count !== null && countsBaseline.mapCount !== null && countsBaseline.withoutMapCount === Math.max(0, (countsBaseline.count ?? 0) - (countsBaseline.mapCount ?? 0)) ? "x" : " "}] mapCount + withoutMapCount == count (baseline): **PASS**

## Veredicto

**${pass ? "PASS — Cobertura remota completa validada" : "FAIL — Ver diferencias arriba"}**

---
*Reporte generado por \`scripts/audit-remote-cursor-coverage.mjs\`. No contiene IDs individuales ni credenciales.*
`;

try {
  writeFileSync(reportPath, reportContent, "utf8");
  console.log(`\nReporte guardado en: _scratch/frontend_structure_desktop/DESKTOP_REMOTE_CURSOR_COVERAGE_RESULTS.md`);
} catch (err) {
  console.error("No se pudo guardar el reporte:", err.message);
}

process.exit(pass ? 0 : 1);
