import { NextResponse } from "next/server";
import { insertSignal, persistenceRequired } from "@/lib/db-writer";
import { realEstateExists } from "@/lib/property-service";
import type { ClaimStatus } from "@/types/property";

export const dynamic = "force-dynamic";

// Recibe un reclamo de perfil. NUNCA auto-aprueba: la respuesta es siempre
// "pending" (o "needs_review" si faltan señales de confianza). La persistencia
// real vive en public.perfil_claims (ver migración 20260809000000_perfil_claims)
// y requiere un rol con INSERT; el preview de sólo lectura no escribe, así que el
// reclamo se valida y acusa recibo sin auto-modificar el perfil.
type ClaimInput = {
  tipo?: string;
  entidadId?: string | number;
  nombre?: string;
  email?: string;
  telefono?: string;
  rol?: string;
  mensaje?: string;
};

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function clean(value: unknown, max: number): string {
  return typeof value === "string" ? value.replace(/[<>]/g, "").trim().slice(0, max) : "";
}

export async function POST(request: Request) {
  let body: ClaimInput;
  try {
    body = (await request.json()) as ClaimInput;
  } catch {
    return NextResponse.json({ error: "Solicitud inválida." }, { status: 400 });
  }

  // Un `tipo` desconocido se rechaza en vez de asumir "inmobiliaria": aceptarlo
  // silenciosamente guardaba el reclamo contra una entidad que el usuario nunca
  // nombró.
  if (body.tipo !== undefined && body.tipo !== "agente" && body.tipo !== "inmobiliaria") {
    return NextResponse.json({ error: "Tipo de perfil inválido." }, { status: 422 });
  }
  const tipo = body.tipo === "agente" ? "agente" : "inmobiliaria";
  const entidadId = String(body.entidadId ?? "");
  const nombre = clean(body.nombre, 120);
  const email = clean(body.email, 160);
  const telefono = clean(body.telefono, 40);
  const rol = clean(body.rol, 80);
  const mensaje = clean(body.mensaje, 1000);

  if (!/^\d+$/.test(entidadId) || nombre.length < 2 || !EMAIL.test(email)) {
    return NextResponse.json({ error: "Completá nombre y un email válido." }, { status: 422 });
  }

  // El perfil reclamado tiene que existir. Sin esta comprobación cualquier id
  // numérico entraba en la cola de revisión. Un fallo de base no puede leerse
  // como "no existe": ahí devolvemos 503 para no rechazar un reclamo legítimo.
  if (tipo === "inmobiliaria") {
    let exists: boolean;
    try {
      exists = await realEstateExists(entidadId);
    } catch {
      return NextResponse.json({ error: "persistence_unavailable" }, { status: 503 });
    }
    if (!exists) {
      return NextResponse.json({ error: "No encontramos ese perfil." }, { status: 404 });
    }
  }

  // Sin teléfono ni rol el reclamo entra con menos señales de confianza.
  const status: ClaimStatus = telefono && rol ? "pending" : "needs_review";

  // Persiste como señal en public.perfil_claims vía el rol writer dedicado (si
  // está configurado). Nunca auto-aprueba ni modifica el perfil. Si no hay writer
  // (preview de sólo lectura), se acusa recibo sin persistir.
  const { persisted } = await insertSignal("perfil_claims", {
    tipo, entidad_id: Number(entidadId), nombre, email, telefono, rol, mensaje, estado: status,
  });
  // En entorno real, si no se persistió NO devolvemos éxito falso.
  if (!persisted && persistenceRequired()) {
    return NextResponse.json({ error: "persistence_unavailable" }, { status: 503 });
  }
  return NextResponse.json({ status, tipo, persisted });
}
