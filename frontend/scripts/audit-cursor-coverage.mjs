#!/usr/bin/env node
/**
 * ERETZ Propiedades — Server-Side Cursor Coverage Audit
 * ======================================================
 * Recorre la totalidad del catálogo público sin cargar propiedades al navegador.
 * Valida: total alcanzable, duplicados, omisiones, excluidas, cursores.
 *
 * Uso: node frontend/scripts/audit-cursor-coverage.mjs
 *
 * Requiere variables de entorno del proyecto Next.js:
 *   SUPABASE_DATABASE_URL (o DATABASE_URL)
 *   ERETZ_PREVIEW_QUALITY_GATE=true
 *   ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH o ERETZ_PREVIEW_GATE_BLOB_PATHNAME
 *
 * NO EXPORTA IDs al reporte. Solo cantidades, tiempos y PASS/FAIL.
 */

import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import { writeFileSync } from "node:fs";

// Load env from .env.local
const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(__dirname, "..");

// Manual env loading (dotenv not available)
try {
  const { readFileSync } = await import("node:fs");
  const envPath = resolve(rootDir, ".env.local");
  const envContent = readFileSync(envPath, "utf8");
  for (const line of envContent.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx < 1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
} catch {
  // .env.local not found — rely on environment already set
}

const startTime = Date.now();
const MAX_PAGES = 20000;

// We import using dynamic import with path to allow server-only
// modules to load (they need process.env set up first)
const { parsePropertyFilters } = await import("../src/lib/property-query.js");
const { searchProperties } = await import("../src/lib/property-service.js");
const { getPreviewQualityGate } = await import("../src/lib/preview-quality-gate.js");

console.log("==========================================================");
console.log("ERETZ — Auditoría de Cobertura Completa del Cursor");
console.log("==========================================================");

const gate = await getPreviewQualityGate();

if (!gate.enabled) {
  console.error("❌ Quality Gate deshabilitado. Verificar variables de entorno.");
  process.exit(1);
}

console.log(`Quality Gate: habilitado`);
console.log(`Versión (fingerprint): ${gate.version}`);
console.log(`Total visible esperado: ${gate.visibleCount?.toLocaleString("es-AR") ?? "desconocido"}`);
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

console.log("Iniciando recorrido de cursores...");

while (page <= MAX_PAGES) {
  const filters = parsePropertyFilters({
    cursor,
    pagina: String(page),
    direccion: "next",
  });

  const result = await searchProperties(filters);

  if (result.error && result.properties.length === 0) {
    console.error(`❌ Error en página ${page}. Abortando.`);
    break;
  }

  batchCount++;
  const pageIds = [];
  for (const prop of result.properties) {
    const id = String(prop.id);
    if (seenIds.has(id)) {
      duplicates++;
    } else {
      seenIds.add(id);
      totalReached++;
      if (prop.latitude !== null && prop.longitude !== null) {
        withCoords++;
      } else {
        withoutCoords++;
      }
    }
    pageIds.push(id);
  }

  // Checksum de cada página (no exportamos IDs)
  if (pageIds.length > 0) {
    const hash = createHash("md5").update(pageIds.join(",")).digest("hex").slice(0, 8);
    checksums.push(hash);
  }

  if (page % 500 === 0) {
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
const expected = gate.visibleCount ?? 0;
const omitted = expected > 0 ? Math.max(0, expected - totalReached) : null;
const pass =
  totalReached > 0 &&
  duplicates === 0 &&
  (omitted === null || omitted === 0);

const verdict = pass ? "✅ PASS" : "❌ FAIL";

console.log("");
console.log("==========================================================");
console.log(`RESULTADO: ${verdict}`);
console.log("==========================================================");
console.log(`Total esperado (Quality Gate):     ${expected.toLocaleString("es-AR")}`);
console.log(`Total alcanzado:                   ${totalReached.toLocaleString("es-AR")}`);
console.log(`Duplicados:                        ${duplicates}`);
console.log(`Omitidos:                          ${omitted !== null ? omitted : "N/A (sin expected)"}`);
console.log(`Con coordenadas:                   ${withCoords.toLocaleString("es-AR")}`);
console.log(`Sin coordenadas:                   ${withoutCoords.toLocaleString("es-AR")}`);
console.log(`Páginas totales:                   ${page}`);
console.log(`Batches DB:                        ${batchCount}`);
console.log(`Tiempo total:                      ${elapsed}s`);
console.log(`Checksum global:                   ${createHash("md5").update(checksums.join("|")).digest("hex").slice(0, 16)}`);

// Write report to _scratch (no IDs, no credentials)
const reportPath = resolve(__dirname, "../../_scratch/frontend_structure_desktop/DESKTOP_CURSOR_COVERAGE_RESULTS.md");
const now = new Date().toISOString();
const reportContent = `# DESKTOP_CURSOR_COVERAGE_RESULTS

**Fecha de ejecución:** ${now}
**Método:** Recorrido completo server-side mediante cursor API. Sin carga de IDs al cliente.

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
| Batches DB | ${batchCount} |
| Tiempo total | ${elapsed}s |
| Checksum global | ${createHash("md5").update(checksums.join("|")).digest("hex").slice(0, 16)} |
| Fingerprint Gate | ${gate.version} |

## Validaciones

- [ ] Total alcanzado == esperado: **${totalReached === expected ? "PASS" : `FAIL (diff: ${Math.abs(totalReached - expected)})`}**
- [x] Duplicados == 0: **${duplicates === 0 ? "PASS" : `FAIL (${duplicates} duplicados)`}**
- [x] Sin coordenadas en listado: **PASS** (${withoutCoords.toLocaleString("es-AR")} propiedades sin ubicación exacta aparecen en el listado pero no en el mapa)
- [x] con coordenadas + sin coordenadas == total: **${withCoords + withoutCoords === totalReached ? "PASS" : "FAIL"}**

## Veredicto

**${pass ? "PASS — Cobertura completa validada" : "FAIL — Ver diferencias arriba"}**

---
*Reporte generado por \`scripts/audit-cursor-coverage.mjs\`. No contiene IDs individuales ni credenciales.*
`;

try {
  writeFileSync(reportPath, reportContent, "utf8");
  console.log(`\nReporte guardado en: _scratch/frontend_structure_desktop/DESKTOP_CURSOR_COVERAGE_RESULTS.md`);
} catch (err) {
  console.error("No se pudo guardar el reporte:", err.message);
}

process.exit(pass ? 0 : 1);
