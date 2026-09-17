import "server-only";

// Interruptor del modo sombra.
//
// ---------------------------------------------------------------------------
// QUÉ ES EL MODO SOMBRA
// ---------------------------------------------------------------------------
//
// Correr los motores del dominio —calidad de datos, moderación, puntaje— sobre
// las propiedades reales que ya pasan por la aplicación, **para medir qué
// dirían**, sin dejar que decidan nada.
//
// Ninguna propiedad se oculta. Ningún orden cambia. Ningún conteo cambia. El
// Quality Gate sigue siendo la única autoridad de visibilidad.
//
// Existe porque hay dieciocho módulos de dominio testeados contra casos que
// escribí yo, y eso demuestra que la lógica hace lo que dice — no que sus
// umbrales sean razonables sobre 257.073 publicaciones reales. La forma de
// saberlo sin arriesgar nada es calcular y no aplicar.
//
// ---------------------------------------------------------------------------
// APAGADO POR DEFECTO, Y SIN FORMA DE ENCENDERSE SOLO
// ---------------------------------------------------------------------------
//
// La variable ausente, vacía, mal escrita o con cualquier valor que no sea
// exactamente `"true"` deja el modo apagado. No hay `!== "false"`, que es la
// forma habitual de que algo se encienda por accidente.
//
// `server-only` arriba: si alguien lo importa desde un componente de cliente,
// el build falla. La evaluación mira datos de todo el catálogo y no tiene nada
// que hacer en el navegador.
//
// El prefijo NO es `NEXT_PUBLIC_`, a propósito: eso lo inlinearía en el bundle.

/** Nombre de la variable. Exportado para que los tests no lo repitan a mano. */
export const VAR_SHADOW = "ERETZ_DOMAIN_SHADOW_MODE";
export const VAR_MUESTREO = "ERETZ_DOMAIN_SHADOW_SAMPLE";

/**
 * ¿Está encendido el modo sombra?
 *
 * Sólo el string exacto `"true"`. Cualquier otra cosa —incluido `"1"`, `"TRUE"`
 * o `"yes"`— es apagado: un interruptor con varias formas de encenderse tiene
 * varias formas de encenderse por error.
 */
export function shadowActivo(env: NodeJS.ProcessEnv = process.env): boolean {
  return env[VAR_SHADOW] === "true";
}

/**
 * Fracción del catálogo a evaluar, de 0 a 1.
 *
 * Por defecto 1 **cuando el modo está encendido**: encenderlo y medir sobre el
 * 1% daría distribuciones con ruido que después nadie sabe interpretar. El
 * muestreo existe para bajarlo si la medición de costo lo justifica, no como
 * precaución por las dudas.
 *
 * Un valor inválido no apaga ni sube al 100%: devuelve 0. Es el único default
 * seguro para un número que no se entendió.
 */
export function fraccionDeMuestreo(env: NodeJS.ProcessEnv = process.env): number {
  const crudo = env[VAR_MUESTREO];
  if (crudo === undefined || crudo === "") return 1;
  const n = Number(crudo);
  if (!Number.isFinite(n) || n < 0 || n > 1) return 0;
  return n;
}

/**
 * Hash determinista de un id. FNV-1a de 32 bits.
 *
 * Determinista y no aleatorio a propósito: con `Math.random()` la misma
 * propiedad entraría en la muestra en una request y no en la siguiente, y
 * comparar dos mediciones dejaría de ser posible. Con hash del id, la muestra
 * es siempre el mismo subconjunto y los números se pueden comparar entre
 * corridas.
 */
export function hashDeId(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** ¿Esta propiedad entra en la muestra? */
export function entraEnMuestra(id: string, fraccion: number): boolean {
  if (fraccion >= 1) return true;
  if (fraccion <= 0) return false;
  return hashDeId(id) / 0x100000000 < fraccion;
}

export type ConfiguracionShadow = {
  activo: boolean;
  fraccion: number;
};

export function configuracionShadow(env: NodeJS.ProcessEnv = process.env): ConfiguracionShadow {
  const activo = shadowActivo(env);
  // Sin el modo encendido la fracción no se lee siquiera: no hay forma de que
  // una variable de muestreo mal puesta encienda algo.
  return { activo, fraccion: activo ? fraccionDeMuestreo(env) : 0 };
}
