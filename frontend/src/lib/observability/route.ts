import "server-only";

import {
  clavesDeQuery,
  logEvent,
  outcomeDe,
  redactar,
  requestIdDe,
  type Outcome,
} from "@/lib/observability/logger";
import { camposDeTiempos, crearAcumulador, ejecutarEn } from "@/lib/observability/request-timings";

// Envuelve un handler de ruta para que toda request deje exactamente una línea
// de log y toda respuesta lleve su `x-request-id`.
//
// El id importa más de lo que parece: hoy, cuando alguien reporta "me tira
// error al buscar", no hay forma de encontrar ESA request entre las demás. Con
// el id en la respuesta, la persona lo copia y el log se busca por igualdad.
//
// El envoltorio no cambia lo que devuelven las rutas. Las que ya capturan su
// error y responden 503 con un mensaje amable siguen haciéndolo; lo único que
// se agrega es que ese 503 deje rastro. Lo que sí cambia es el caso que hoy no
// está cubierto: si un handler lanza, en vez de la página de error genérica de
// Next ahora sale un 500 JSON con el id, que es lo que el cliente puede citar.

export type Handler = (request: Request) => Response | Promise<Response>;

/** Sólo lo que un cliente puede leer sin que le sirva para nada más. */
const MENSAJE_500 = "Tuvimos un problema procesando la solicitud.";

export function withObservability(route: string, handler: Handler): Handler {
  return async function observado(request: Request): Promise<Response> {
    const requestId = requestIdDe(request.headers);
    const inicio = Date.now();
    const { paramKeys, paramCount } = clavesDeQuery(request.url);

    let status = 500;
    let outcome: Outcome = "server_error";
    let errorName: string | undefined;
    let errorMessage: string | undefined;
    let respuesta: Response;

    // Contexto de sub-tiempos para esta request. La capa de datos registra
    // dentro sin recibir nada por parámetro: `readOnly` es el único punto por
    // el que pasan las consultas, y desde ahí llama a `registrarTiempo`.
    const tiempos = crearAcumulador();

    try {
      respuesta = await ejecutarEn(tiempos, () => handler(request));
      status = respuesta.status;
      outcome = outcomeDe(status);
    } catch (error) {
      errorName = error instanceof Error ? error.name : typeof error;
      errorMessage = error instanceof Error ? error.message : String(error);
      respuesta = new Response(JSON.stringify({ error: MENSAJE_500, requestId }), {
        status: 500,
        headers: { "content-type": "application/json" },
      });
      status = 500;
      outcome = "server_error";
    }

    logEvent({
      level: outcome === "server_error" ? "error" : outcome === "client_error" ? "warn" : "info",
      event: "http_request",
      requestId,
      route,
      method: request.method,
      status,
      outcome,
      durationMs: Date.now() - inicio,
      // `db_ms` junto a `durationMs` es lo que permite separar una request
      // lenta por la base de una lenta por otra cosa. `db_n` distingue una
      // consulta pesada de varias que se acumulan.
      ...camposDeTiempos(tiempos),
      paramKeys,
      paramCount,
      ...(errorName ? { errorName } : {}),
      ...(errorMessage ? { errorMessage: redactar(errorMessage, 300) } : {}),
    });

    // Un `Response` puede tener headers inmutables; se reconstruye sólo cuando
    // hace falta en vez de asumir que se puede escribir encima.
    try {
      respuesta.headers.set("x-request-id", requestId);
      return respuesta;
    } catch {
      // Headers inmutables: se reconstruye la respuesta copiando las entradas
      // una por una, porque `new Headers(x)` sólo acepta un Headers real.
      try {
        const headers = new Headers();
        respuesta.headers.forEach((valor, clave) => headers.set(clave, valor));
        headers.set("x-request-id", requestId);
        return new Response(respuesta.body, {
          status: respuesta.status,
          statusText: respuesta.statusText,
          headers,
        });
      } catch {
        // Si ni siquiera se pueden leer, se devuelve la respuesta como vino.
        // Perder el header de traza es molesto; romper la ruta por intentar
        // agregarlo sería mucho peor.
        return respuesta;
      }
    }
  };
}
