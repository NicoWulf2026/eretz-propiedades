// Errores de la publicación.
//
// Un modelo cerrado en vez de `Error` suelto, por un motivo concreto: quien
// llama tiene que poder DECIDIR según el error —reintentar, pedir permiso,
// mostrar un campo en rojo— y con excepciones genéricas eso se hace comparando
// mensajes, que es frágil y se rompe al traducir.
//
// Ninguno lleva stacktrace ni detalles internos. El `detail` es para una
// persona, no para depurar: nada de nombres de tabla, consultas ni rutas.

export const PUBLICATION_ERRORS = [
  /** El borrador no cumple las reglas. Trae qué campos. */
  "VALIDATION_ERROR",
  /** El actor no puede hacer esto sobre este recurso. */
  "PERMISSION_DENIED",
  "DRAFT_NOT_FOUND",
  /** Alguien más lo modificó desde que se leyó. */
  "CONFLICT",
  /** Mismo `idempotencyKey` ya procesado. NO es un fallo: ver abajo. */
  "DUPLICATE_SUBMISSION",
  /** El contenido queda bloqueado por moderación. */
  "MODERATION_BLOCKED",
  /** Se alcanzó el límite de publicaciones gratuitas. */
  "LIMIT_REACHED",
  /** Reservados para cuando exista infraestructura. */
  "STORAGE_UNAVAILABLE",
  "PERSISTENCE_UNAVAILABLE",
] as const;
export type PublicationErrorCode = (typeof PUBLICATION_ERRORS)[number];

export type CampoConError = { field: string; code: string; message: string };

export type PublicationError = {
  code: PublicationErrorCode;
  /** Mensaje para mostrar. En castellano, sin jerga interna. */
  detail: string;
  /** Sólo en VALIDATION_ERROR. */
  fields?: CampoConError[];
};

/**
 * Resultado de una operación. Explícito en vez de excepciones.
 *
 * Con excepciones, olvidarse de un `catch` produce una pantalla en blanco. Con
 * un resultado, el compilador obliga a mirar el caso de error antes de tocar el
 * valor.
 */
export type Resultado<T> = { ok: true; value: T } | { ok: false; error: PublicationError };

export const ok = <T>(value: T): Resultado<T> => ({ ok: true, value });

export const fallo = (
  code: PublicationErrorCode,
  detail: string,
  fields?: CampoConError[],
): Resultado<never> => ({ ok: false, error: { code, detail, ...(fields ? { fields } : {}) } });

/**
 * ¿Este error se resuelve editando el formulario?
 *
 * Separa lo que la persona puede arreglar de lo que no. Un error de permisos no
 * mejora por corregir un campo, y mostrarlo junto a los de validación haría que
 * lo intentara.
 */
export function esCorregiblePorElUsuario(code: PublicationErrorCode): boolean {
  return code === "VALIDATION_ERROR" || code === "MODERATION_BLOCKED";
}

/**
 * `DUPLICATE_SUBMISSION` no se muestra como error.
 *
 * Significa que el envío YA se procesó: la persona apretó dos veces, o volvió
 * atrás y reenvió. Mostrarle un error la haría pensar que no se guardó y
 * volvería a intentar. Es un éxito con otro nombre.
 */
export function esExitoDisfrazado(code: PublicationErrorCode): boolean {
  return code === "DUPLICATE_SUBMISSION";
}
