import "server-only";

// Acumula tiempos por request, para poder decir en qué se fue una request lenta
// y no sólo cuánto tardó.
//
// ---------------------------------------------------------------------------
// POR QUÉ ASYNCLOCALSTORAGE Y NO UNA VARIABLE DE MÓDULO
// ---------------------------------------------------------------------------
//
// Las consultas a la base salen de `readOnly`, que está a varias llamadas de
// distancia del envoltorio de ruta. Pasar un cronómetro por parámetro obligaría
// a tocar las diecisiete llamadas y las firmas de toda la capa de datos.
//
// Un acumulador a nivel de módulo sería más simple y estaría MAL: el servidor
// atiende varias requests a la vez, así que las mediciones se mezclarían y cada
// request reportaría el trabajo de las otras. `AsyncLocalStorage` da un
// almacenamiento por cadena asíncrona, que es exactamente el alcance correcto.
//
// ---------------------------------------------------------------------------
// SI ALGO FALLA, NO HAY MEDICIÓN — PERO SÍ HAY RESPUESTA
// ---------------------------------------------------------------------------
//
// Todo lo de acá está pensado para degradar a "no medir". Fuera de una request,
// o si el almacenamiento no está disponible, `registrarTiempo` no hace nada y
// nadie se entera. Perder un número es aceptable; romper una búsqueda por
// intentar medirla, no.

import { AsyncLocalStorage } from "node:async_hooks";

export type AcumuladorDeRequest = {
  /** Milisegundos acumulados por etiqueta. */
  totales: Map<string, number>;
  /** Cuántas veces se registró cada etiqueta. */
  cuentas: Map<string, number>;
};

/** Tope de etiquetas distintas, por si alguien mide dentro de un bucle. */
export const MAXIMO_ETIQUETAS = 12;

const almacen = new AsyncLocalStorage<AcumuladorDeRequest>();

const NOMBRE_VALIDO = /^[a-z][a-z0-9_]{0,31}$/;

export function crearAcumulador(): AcumuladorDeRequest {
  return { totales: new Map(), cuentas: new Map() };
}

/**
 * Corre `fn` con ese acumulador como contexto.
 *
 * Separado de `crearAcumulador` para que el sitio de llamada pueda leer lo
 * acumulado después de que `fn` termine, sin envolver su propio manejo de
 * errores. El envoltorio de ruta ya tiene su `try`/`catch`, y meterlo adentro
 * de éste habría duplicado esa lógica.
 */
export function ejecutarEn<T>(acumulador: AcumuladorDeRequest, fn: () => T): T {
  return almacen.run(acumulador, fn);
}

/**
 * Suma una duración a la request en curso.
 *
 * Fuera de una request no hace nada, y ése es el caso de los tests unitarios y
 * de cualquier proceso que use la capa de datos por fuera de una ruta.
 */
export function registrarTiempo(etiqueta: string, ms: number): void {
  const acumulador = almacen.getStore();
  if (!acumulador) return;
  if (!NOMBRE_VALIDO.test(etiqueta) || !Number.isFinite(ms) || ms < 0) return;
  if (!acumulador.totales.has(etiqueta) && acumulador.totales.size >= MAXIMO_ETIQUETAS) return;

  acumulador.totales.set(etiqueta, (acumulador.totales.get(etiqueta) ?? 0) + ms);
  acumulador.cuentas.set(etiqueta, (acumulador.cuentas.get(etiqueta) ?? 0) + 1);
}

/**
 * Mide una operación asíncrona y la registra.
 *
 * Registra también cuando falla: una consulta que tarda cinco segundos y
 * después revienta es justamente la que hay que ver.
 */
export async function medirEnRequest<T>(etiqueta: string, fn: () => Promise<T>): Promise<T> {
  const inicio = Date.now();
  try {
    return await fn();
  } finally {
    registrarTiempo(etiqueta, Date.now() - inicio);
  }
}

/**
 * Campos escalares para la línea de log.
 *
 * Escalares porque `logEvent` descarta en silencio lo que no lo es. Se emite
 * el total y la cantidad: `db_ms=1900 db_n=3` dice mucho más que sólo el total,
 * porque distingue una consulta lenta de tres que se acumulan.
 */
export function camposDeTiempos(acumulador: AcumuladorDeRequest): Record<string, number> {
  const salida: Record<string, number> = {};
  for (const etiqueta of [...acumulador.totales.keys()].sort()) {
    salida[`${etiqueta}_ms`] = Math.round(acumulador.totales.get(etiqueta) as number);
    salida[`${etiqueta}_n`] = acumulador.cuentas.get(etiqueta) as number;
  }
  return salida;
}

/** ¿Se midió algo? Evita ensuciar la línea con nada. */
export function hayTiempos(acumulador: AcumuladorDeRequest): boolean {
  return acumulador.totales.size > 0;
}
