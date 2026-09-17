import "server-only";

import { NextResponse } from "next/server";
import {
  claveDeCliente,
  esDuplicado,
  huellaDeContenido,
  limitarTasa,
  type AlmacenDeConteo,
} from "@/lib/abuse/rate-limit";

// Guarda compartida por los endpoints que aceptan texto de cualquiera.
//
// Se separa de las rutas para que las dos decidan igual y para que el día que
// el almacén pase a ser compartido no haya que tocar ningún endpoint.

export type VeredictoAbuso =
  | { tipo: "ok" }
  | { tipo: "limitado"; respuesta: NextResponse }
  | { tipo: "duplicado" };

export type OpcionesGuarda = {
  /** Separa la cuota por endpoint: reportar no consume la de reclamar. */
  endpoint: string;
  limite: number;
  ventanaMs: number;
  /** Lo que define "el mismo envío". Sin esto no se deduplica. */
  huella?: ReadonlyArray<string | number | null | undefined>;
  dedupeMs?: number;
  almacen?: AlmacenDeConteo;
  ahora?: number;
};

export function revisarAbuso(request: Request, opciones: OpcionesGuarda): VeredictoAbuso {
  const { endpoint, limite, ventanaMs, almacen, ahora } = opciones;
  const clave = claveDeCliente(request.headers, endpoint);
  const tasa = limitarTasa(clave, { limite, ventanaMs, almacen, ahora });

  if (!tasa.permitido) {
    // El mensaje no dice cuál es el límite ni cuánto falta para la ventana
    // completa: eso le ahorra trabajo a quien esté probando dónde está el
    // borde. `Retry-After` es lo que un cliente honesto necesita.
    return {
      tipo: "limitado",
      respuesta: NextResponse.json(
        { error: "Recibimos varios envíos seguidos. Probá de nuevo en un momento." },
        { status: 429, headers: { "Retry-After": String(tasa.reintentarEnSeg) } },
      ),
    };
  }

  if (opciones.huella && opciones.dedupeMs) {
    const fp = huellaDeContenido([endpoint, ...opciones.huella]);
    if (esDuplicado(fp, { ventanaMs: opciones.dedupeMs, almacen, ahora })) {
      return { tipo: "duplicado" };
    }
  }

  return { tipo: "ok" };
}

/** Cuotas por endpoint. Conservadoras: se pueden aflojar con datos de uso. */
export const CUOTA_REPORTES = { limite: 5, ventanaMs: 10 * 60_000, dedupeMs: 60 * 60_000 };
export const CUOTA_RECLAMOS = { limite: 3, ventanaMs: 30 * 60_000, dedupeMs: 24 * 60 * 60_000 };
