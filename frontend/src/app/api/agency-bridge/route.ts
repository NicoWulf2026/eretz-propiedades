import { NextResponse } from "next/server";
import {
  type Fila, insertar, isConfigured, isPreviewEnvironment, nombres,
  preflight, safeError, stagingPorFuente, stats,
} from "@/lib/agency-bridge";

// Ruta TEMPORAL del rollout de Agency Coverage. Se elimina al terminar.
//
// Sólo Preview: en Production responde 404, no 403, para no anunciarse.
// Deployment Protection ya cubre el deployment; esta ruta no la reemplaza.
// `op` es una unión cerrada: el request no elige tabla, columna ni consulta.
// Nunca devuelve la connection string.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_FILAS = 250;

function guard(): NextResponse | null {
  if (!isPreviewEnvironment()) return NextResponse.json({ error: "not found" }, { status: 404 });
  if (!isConfigured()) return NextResponse.json({ error: "sin conexión" }, { status: 503 });
  return null;
}

export async function GET(request: Request) {
  const blocked = guard();
  if (blocked) return blocked;

  const op = new URL(request.url).searchParams.get("op");
  try {
    if (op === "stats") {
      return NextResponse.json({ stats: await stats(), fuentes: await stagingPorFuente() });
    }
    if (op === "main" || op === "staging") {
      const filas = await nombres(op);
      return NextResponse.json({ total: filas.length, filas });
    }
    return NextResponse.json({
      environment: process.env.VERCEL_ENV ?? "local",
      preflight: await preflight(),
      stats: await stats(),
    });
  } catch (e) {
    return NextResponse.json({ error: safeError(e) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const blocked = guard();
  if (blocked) return blocked;

  let body: { filas?: unknown; dryRun?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "cuerpo inválido" }, { status: 400 });
  }

  const filas = Array.isArray(body.filas) ? (body.filas as Fila[]) : null;
  if (!filas) return NextResponse.json({ error: "falta filas[]" }, { status: 400 });
  if (filas.length > MAX_FILAS) {
    return NextResponse.json({ error: `máximo ${MAX_FILAS} filas` }, { status: 413 });
  }
  if (body.dryRun) return NextResponse.json({ dryRun: true, recibidas: filas.length });

  const antes = await stats();
  const r = await insertar(filas);
  const despues = await stats();
  return NextResponse.json({ recibidas: filas.length, ...r, antes, despues });
}
