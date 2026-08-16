import { NextResponse } from "next/server";
import {
  type CoverageRow, existingKeys, insertBatch, isCoverageWriterConfigured,
  isPreviewEnvironment, preflight, stagingStats,
} from "@/lib/coverage-writer";

// Endpoint TEMPORAL del rollout de Agency Coverage. Existe sólo mientras dura la
// incorporación y se retira después, junto con la credencial.
//
// Cuatro compuertas, y las cuatro tienen que abrir:
//   1. VERCEL_ENV debe ser preview. En production responde 404, no 403: no se
//      anuncia que existe.
//   2. La credencial temporal tiene que estar configurada. Sin ella, no-op.
//   3. Vercel Deployment Protection ya cubre el deployment entero; esta ruta no
//      la reemplaza ni la debilita.
//   4. El servidor fija `fuente`; el cliente no puede escribir en nombre de otro
//      import aunque lo mande en el cuerpo.
//
// Nunca devuelve ni loguea la connection string.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_ROWS_PER_REQUEST = 250;

function notFound() {
  // 404 y no 403: en Production la ruta no debe existir para quien la pruebe.
  return NextResponse.json({ error: "not found" }, { status: 404 });
}

function guard(): NextResponse | null {
  if (!isPreviewEnvironment()) return notFound();
  if (!isCoverageWriterConfigured()) {
    return NextResponse.json(
      { error: "coverage writer no configurado en este entorno" }, { status: 503 });
  }
  return null;
}

/** GET: preflight y estado. No escribe nada. */
export async function GET() {
  const blocked = guard();
  if (blocked) return blocked;

  const pre = await preflight();
  const stats = pre.ok ? await stagingStats() : null;
  return NextResponse.json({
    environment: process.env.VERCEL_ENV ?? "local",
    preflight: pre,
    staging: stats,
    // El alcance esperado, para poder comparar de un vistazo.
    expected: {
      canSelectMain: true, canInsertStaging: true,
      canUpdateStaging: false, canDeleteStaging: false,
    },
  });
}

/**
 * POST: inserta un lote.
 *
 * Cuerpo: { rows: CoverageRow[], dryRun?: boolean }
 * El dedupe contra main y staging se hace acá, con el estado del momento, no
 * con el snapshot del crosswalk: entre el cruce y ahora pudo cargarse algo.
 */
export async function POST(request: Request) {
  const blocked = guard();
  if (blocked) return blocked;

  const pre = await preflight();
  if (!pre.ok) {
    return NextResponse.json({ error: "preflight falló", preflight: pre }, { status: 503 });
  }
  // Si el rol tuviera más alcance del previsto, no se escribe: es señal de que
  // los grants no quedaron como se diseñaron.
  if (pre.canUpdateStaging || pre.canDeleteStaging) {
    return NextResponse.json({
      error: "el rol tiene UPDATE/DELETE sobre staging; se esperaba sólo SELECT+INSERT",
      preflight: pre,
    }, { status: 409 });
  }

  let body: { rows?: unknown; dryRun?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  const rows = Array.isArray(body.rows) ? (body.rows as CoverageRow[]) : null;
  if (!rows) return NextResponse.json({ error: "falta rows[]" }, { status: 400 });
  if (rows.length > MAX_ROWS_PER_REQUEST) {
    return NextResponse.json(
      { error: `máximo ${MAX_ROWS_PER_REQUEST} filas por request` }, { status: 413 });
  }

  const { main, staging } = await existingKeys();
  const pending: CoverageRow[] = [];
  const skipped = { sinClave: 0, yaEnMain: 0, yaEnStaging: 0 };
  const seen = new Set<string>();

  for (const row of rows) {
    const key = String(row.nombre_normalizado ?? "").toLowerCase();
    if (!key) { skipped.sinClave += 1; continue; }
    if (main.has(key)) { skipped.yaEnMain += 1; continue; }
    if (staging.has(key) || seen.has(key)) { skipped.yaEnStaging += 1; continue; }
    seen.add(key);
    pending.push(row);
  }

  if (body.dryRun) {
    return NextResponse.json({ dryRun: true, recibidas: rows.length, aInsertar: pending.length, skipped });
  }

  const before = await stagingStats();
  const result = await insertBatch(pending);
  const after = await stagingStats();

  return NextResponse.json({
    recibidas: rows.length,
    aInsertar: pending.length,
    insertadas: result.inserted,
    skipped,
    error: result.error,
    staging: { before, after },
    // Si estos dos no coinciden hay duplicados y el cliente debe detenerse.
    duplicados: after.mine - after.distinct,
  });
}
