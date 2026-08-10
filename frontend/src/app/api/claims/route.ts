import { NextResponse } from "next/server";
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

  // Sin teléfono ni rol el reclamo entra con menos señales de confianza.
  const status: ClaimStatus = telefono && rol ? "pending" : "needs_review";

  // Payload validado, listo para persistir en public.perfil_claims cuando exista
  // un rol con permiso de escritura. La verificación es humana; nunca se aprueba
  // automáticamente ni se modifica el perfil.
  const claim = { tipo, entidadId, nombre, email, telefono, rol, mensaje, estado: status } as const;
  return NextResponse.json({ status: claim.estado, tipo: claim.tipo });
}
