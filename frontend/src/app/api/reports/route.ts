import { NextResponse } from "next/server";
import { insertSignal } from "@/lib/db-writer";

export const dynamic = "force-dynamic";

// Recibe un reporte de problema en una publicación. Es una SEÑAL: no modifica ni
// oculta la publicación. Persistencia real en public.reportes_publicacion (ver
// migración 20260809020000) con un rol con INSERT; el preview de sólo lectura
// valida y acusa recibo sin escribir.
const MOTIVOS = new Set(["no_disponible", "precio_incorrecto", "duplicada", "datos_erroneos", "otro"]);
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function clean(value: unknown, max: number): string {
  return typeof value === "string" ? value.replace(/[<>]/g, "").trim().slice(0, max) : "";
}

export async function POST(request: Request) {
  let body: { propiedadId?: string | number; motivo?: string; detalle?: string; email?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Solicitud inválida." }, { status: 400 });
  }
  const propiedadId = String(body.propiedadId ?? "");
  const motivo = clean(body.motivo, 40);
  const detalle = clean(body.detalle, 1000);
  const email = clean(body.email, 160);

  if (!/^\d+$/.test(propiedadId) || !MOTIVOS.has(motivo)) {
    return NextResponse.json({ error: "Elegí un motivo válido." }, { status: 422 });
  }
  if (email && !EMAIL.test(email)) {
    return NextResponse.json({ error: "El email no es válido." }, { status: 422 });
  }

  // Persiste como señal (estado 'nuevo') vía el rol writer dedicado si está
  // configurado; nunca modifica ni oculta la publicación. Sin writer, acusa recibo.
  const { persisted } = await insertSignal("reportes_publicacion", {
    propiedad_id: Number(propiedadId), motivo, detalle, email, estado: "nuevo",
  });
  return NextResponse.json({ status: "received", motivo, persisted });
}
