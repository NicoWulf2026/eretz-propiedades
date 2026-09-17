// Contrato de estado del sistema.
//
// NO hay endpoint. Es deliberado: un `/health` público que enumera dependencias
// y errores le dice a cualquiera qué usa el sistema y cuándo está débil, que es
// exactamente lo que alguien quiere saber antes de atacarlo. Este módulo define
// la FORMA del estado; quién la expone, a quién y con cuánto detalle es una
// decisión aparte que hoy no hace falta tomar.
//
// ---------------------------------------------------------------------------
// DEGRADADO ES UN ESTADO, NO UN ERROR SUAVE
// ---------------------------------------------------------------------------
//
// ERETZ puede funcionar con partes caídas, y la diferencia importa:
//
//   - Sin base, el catálogo no existe: no hay producto. `UNAVAILABLE`.
//   - Sin el manifiesto del Quality Gate, el Gate falla cerrado y el catálogo
//     se ve vacío. Eso NO es "sano con una advertencia": para quien entra es
//     indistinguible de estar caído. `UNAVAILABLE`.
//   - Sin el writer de reportes, el formulario devuelve 503 y todo lo demás
//     anda. `DEGRADED`.
//
// La regla que sale de ahí: una dependencia es crítica si sin ella la persona
// no puede hacer lo que vino a hacer. No si "es importante".

export const HEALTH_STATUSES = ["HEALTHY", "DEGRADED", "UNAVAILABLE"] as const;
export type HealthStatus = (typeof HEALTH_STATUSES)[number];

export type Dependencia = {
  nombre: string;
  /** Sin ella no hay producto. */
  critica: boolean;
  disponible: boolean;
  /** Qué falla, sin detalles que sirvan para atacar. */
  detalle: string | null;
};

export type EstadoDelSistema = {
  status: HealthStatus;
  /** Qué dependencias están caídas, por nombre. */
  afectadas: string[];
  resumen: string;
};

/**
 * Combina el estado de las dependencias.
 *
 * Sin dependencias declaradas devuelve `UNAVAILABLE`, no `HEALTHY`: una lista
 * vacía casi siempre significa que la comprobación no llegó a correr, y
 * reportar salud perfecta en ese caso es la forma de que un monitoreo roto
 * parezca un sistema sano.
 */
export function evaluarEstado(dependencias: readonly Dependencia[]): EstadoDelSistema {
  if (dependencias.length === 0) {
    return {
      status: "UNAVAILABLE",
      afectadas: [],
      resumen: "no se pudo evaluar ninguna dependencia",
    };
  }

  const caidas = dependencias.filter((d) => !d.disponible);
  const criticasCaidas = caidas.filter((d) => d.critica);
  const afectadas = caidas.map((d) => d.nombre).sort();

  if (criticasCaidas.length) {
    return {
      status: "UNAVAILABLE",
      afectadas,
      resumen: `sin ${criticasCaidas.map((d) => d.nombre).sort().join(", ")}`,
    };
  }
  if (caidas.length) {
    return { status: "DEGRADED", afectadas, resumen: `funciona sin ${afectadas.join(", ")}` };
  }
  return { status: "HEALTHY", afectadas: [], resumen: "todo disponible" };
}

/** ¿Puede alguien usar el sitio en este estado? */
export function permiteUso(s: HealthStatus): boolean {
  return s !== "UNAVAILABLE";
}

/**
 * Versión pública del estado.
 *
 * Devuelve el estado y nada más: ni nombres de dependencias, ni detalles de
 * error, ni versiones. Quien opera el sistema mira los logs, que ya llevan
 * request id; quien mira desde afuera sólo necesita saber si anda.
 */
export function estadoPublico(e: EstadoDelSistema): { status: HealthStatus } {
  return { status: e.status };
}
