import { NextResponse } from "next/server";
import { insertSignal, persistenceRequired } from "@/lib/db-writer";
import { withObservability } from "@/lib/observability/route";
import { CUOTA_REPORTES, revisarAbuso } from "@/lib/abuse/guard";

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

async function handlePOST(request: Request) {
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

  // Recién acá, con la entrada ya validada: no se gasta cuota en un cuerpo
  // malformado, y la huella se calcula sobre el contenido ya limpio.
  const veredicto = revisarAbuso(request, {
    endpoint: "reports",
    limite: CUOTA_REPORTES.limite,
    ventanaMs: CUOTA_REPORTES.ventanaMs,
    huella: [propiedadId, motivo, detalle],
    dedupeMs: CUOTA_REPORTES.dedupeMs,
  });
  if (veredicto.tipo === "limitado") return veredicto.respuesta;
  if (veredicto.tipo === "duplicado") {
    // El mismo reporte otra vez no es un error de quien lo manda -un doble
    // clic, un reintento- y no tiene sentido guardarlo dos veces. Se acusa
    // recibo igual: decirle "duplicado" a alguien que reporta un problema real
    // suena a que no se le dio curso.
    return NextResponse.json({ status: "received", motivo, persisted: false, deduplicated: true });
  }

  // Persiste como señal (estado 'nuevo') vía el rol writer dedicado si está
  // configurado; nunca modifica ni oculta la publicación. Sin writer, acusa recibo.
  const { persisted } = await insertSignal("reportes_publicacion", {
    propiedad_id: Number(propiedadId), motivo, detalle, email, estado: "nuevo",
  });
  // En entorno real, si no se persistió NO devolvemos éxito falso.
  if (!persisted && persistenceRequired()) {
    return NextResponse.json({ error: "persistence_unavailable" }, { status: 503 });
  }
  return NextResponse.json({ status: "received", motivo, persisted });
}

export const POST = withObservability("/api/reports", handlePOST);
