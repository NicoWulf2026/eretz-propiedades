import { NextResponse } from "next/server";
import {
  type CoveragePayload, callEcho, callFuncdef, callIdentity, callPreflight, callStage,
  isCoverageBridgeConfigured, isPreviewEnvironment, safeError,
  snapshotKeys, snapshotSummary,
} from "@/lib/coverage-writer";

// Endpoint TEMPORAL del rollout de Agency Coverage. Existe sólo mientras dura
// la incorporación y se retira después, junto con el puente de base.
//
// Cuatro compuertas, y las cuatro tienen que abrir:
//   1. VERCEL_ENV debe ser preview. En production responde 404, no 403: no se
//      anuncia que existe.
//   2. El puente tiene que estar configurado. Sin él, no-op.
//   3. Vercel Deployment Protection ya cubre el deployment entero; esta ruta no
//      la reemplaza ni la debilita.
//   4. El request no elige nada: ni función, ni tabla, ni columna. `op` es una
//      unión cerrada de tres valores que mapean a sentencias constantes, y la
//      fuente la fija la función en el servidor.
//
// Nunca devuelve ni loguea la connection string.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_ITEMS_PER_REQUEST = 250;

function guard(): NextResponse | null {
  // 404 y no 403: en Production la ruta no debe existir para quien la pruebe.
  if (!isPreviewEnvironment()) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!isCoverageBridgeConfigured()) {
    return NextResponse.json({ error: "puente no configurado" }, { status: 503 });
  }
  return null;
}

/**
 * GET: preflight, identidad y snapshot. Ninguno escribe.
 *
 * `op` es una unión cerrada de tres valores. Cualquier otro cae en el caso por
 * defecto: no hay forma de nombrar desde el request una función, tabla o
 * columna que no esté escrita en el módulo.
 */
export async function GET(request: Request) {
  const blocked = guard();
  if (blocked) return blocked;

  const op = new URL(request.url).searchParams.get("op");

  if (op === "echo") {
    return NextResponse.json({ echo: await callEcho({ nombre: "prueba", x: 1 }) });
  }
  if (op === "def") {
    return NextResponse.json({ def: await callFuncdef() });
  }
  if (op === "keys") {
    return NextResponse.json({ keys: await snapshotKeys() });
  }
  if (op === "snapshot") {
    return NextResponse.json({ snapshot: await snapshotSummary() });
  }

  const [pre, ident, snap] = await Promise.all([
    callPreflight(), callIdentity(), snapshotSummary(),
  ]);
  return NextResponse.json({
    environment: process.env.VERCEL_ENV ?? "local",
    preflight: pre,
    // Lo que informa el preflight son los privilegios del DUEÑO de la función,
    // no los del rol que llama. Esto último es lo que dice `identity`.
    identity: ident,
    snapshot: snap,
  });
}

type Item = { candidateKey?: unknown; payload?: unknown };

/**
 * POST: stagea un lote.
 *
 * Cuerpo: { items: [{ candidateKey, payload }], dryRun?: boolean }
 *
 * El dedupe no se hace acá. Lo hace `stage_v1` contra el estado real en el
 * momento de cada insert, bajo advisory lock por candidate key. Replicarlo del
 * lado del cliente daría una segunda respuesta que puede discrepar de la
 * primera, y la que manda es la de la función.
 */
export async function POST(request: Request) {
  const blocked = guard();
  if (blocked) return blocked;

  let body: { items?: unknown; dryRun?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  const items = Array.isArray(body.items) ? (body.items as Item[]) : null;
  if (!items) return NextResponse.json({ error: "falta items[]" }, { status: 400 });
  if (items.length > MAX_ITEMS_PER_REQUEST) {
    return NextResponse.json(
      { error: `máximo ${MAX_ITEMS_PER_REQUEST} items por request` }, { status: 413 });
  }

  const prepared: Array<{ key: string; payload: CoveragePayload }> = [];
  let sinClave = 0;
  for (const it of items) {
    const key = typeof it?.candidateKey === "string" ? it.candidateKey.trim() : "";
    const payload = it?.payload;
    if (!key || !payload || typeof payload !== "object") { sinClave += 1; continue; }
    prepared.push({ key, payload: payload as CoveragePayload });
  }

  if (body.dryRun) {
    return NextResponse.json({
      dryRun: true, recibidos: items.length, aProcesar: prepared.length, sinClave,
    });
  }

  const results: Array<Record<string, unknown>> = [];
  let errores = 0;
  for (const { key, payload } of prepared) {
    try {
      const r = await callStage(key, payload);
      if (!r.ok) errores += 1;
      results.push({ candidateKey: key, ok: r.ok, error: r.error, rows: r.rows });
    } catch (error) {
      errores += 1;
      results.push({ candidateKey: key, ok: false, error: safeError(error) });
    }
  }

  // El snapshot posterior es la verificación del lote: lo que diga la base, no
  // lo que el cliente crea haber insertado.
  const after = await snapshotSummary();

  return NextResponse.json({
    recibidos: items.length, procesados: prepared.length, sinClave, errores,
    results, snapshot: after,
  });
}
