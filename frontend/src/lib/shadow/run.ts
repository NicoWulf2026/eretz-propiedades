import "server-only";

// El único punto donde el modo sombra toca el camino de lectura.
//
// `ejecutarShadow` recibe el lote, lo evalúa, escribe una línea de log y **no
// devuelve nada**. Ese `void` es deliberado: sin valor de retorno, el sitio de
// llamada no tiene forma de usar el resultado para decidir algo, ni hoy ni
// cuando alguien lo edite dentro de seis meses.
//
// Todo lo que puede fallar está dentro de un `try`. Un error midiendo no puede
// romper una búsqueda: el modo sombra es un observador, y un observador que
// tira abajo lo que observa es peor que no tenerlo.

import { logEvent } from "@/lib/observability/logger";
import { Cronometro } from "@/lib/observability/timings";
import { advertencias, aplanarResumen, evaluarLote, type ParaEvaluar } from "./evaluate";
import { configuracionShadow } from "./flag";

/**
 * Correlación de las líneas del modo sombra.
 *
 * No es un id de request real, y por eso se llama así. Este punto de llamada
 * está en la capa de datos y no ve el `Request`, así que no puede tomar el id
 * que genera `withObservability`. Las dos líneas se cruzan por `route` y
 * cercanía temporal, que para un diagnóstico alcanza. Inventar un id por lote
 * daría la apariencia de una correlación que no existe.
 */
export const CORRELACION_SHADOW = "domain-shadow";

/**
 * Evalúa un lote en modo sombra. No devuelve nada y no muta nada.
 *
 * @param ruta de dónde salió el lote, para poder segmentar en los logs
 */
export function ejecutarShadow(lote: readonly ParaEvaluar[], ruta: string): void {
  const config = configuracionShadow();
  // Salida temprana: con la flag apagada no se construye nada, no se recorre
  // el lote y el costo es una comparación de strings.
  if (!config.activo) return;

  try {
    const cronometro = new Cronometro();
    const resumen = cronometro.medirSync("domain_shadow", () => evaluarLote(lote, config));
    if (!resumen || resumen.evaluadas === 0) return;

    const avisos = advertencias(resumen);
    logEvent({
      // `warn` cuando algo se sale de los umbrales diagnósticos. No cambia
      // nada: sólo hace que la línea se encuentre buscando por nivel.
      level: avisos.length ? "warn" : "info",
      event: "domain_shadow_summary",
      requestId: CORRELACION_SHADOW,
      route: ruta,
      ...cronometro.resumen().timings,
      ...aplanarResumen(resumen),
      ...(avisos.length ? { advertencias: avisos.map((a) => a.code).join(",") } : {}),
    });
  } catch (error) {
    // Se registra el fallo de la medición y se sigue. Nunca se propaga.
    logEvent({
      level: "warn",
      event: "domain_shadow_error",
      requestId: CORRELACION_SHADOW,
      route: ruta,
      // Sólo el nombre del error. El mensaje podría arrastrar un valor de la
      // propiedad que lo causó.
      errorName: error instanceof Error ? error.name : typeof error,
    });
  }
}
