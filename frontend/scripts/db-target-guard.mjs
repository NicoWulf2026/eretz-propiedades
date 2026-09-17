// Guarda contra ejecutar DDL, benchmarks o SQL experimental sobre la base
// equivocada.
//
// Existe por un caso concreto y ya ocurrido: en este proyecto "Preview" era un
// entorno de despliegue de Vercel conectado a la MISMA base que tiene las
// 257.073 publicaciones reales. `eretz_preview_ro` no es otra base: es un rol
// dentro de la única que hay. Cualquiera que leyera "Preview DB" en un runbook
// y ejecutara una migración habría estado tocando el dato real, convencido de
// lo contrario.
//
// Por eso la guarda no pregunta "¿es producción?" sino al revés: **exige
// demostrar que es el destino esperado**. Sin prueba, aborta. Un chequeo que
// falla abierto no sirve para esto.
//
// Y no se confía en NODE_ENV: es una variable de proceso que cualquiera fija, y
// no dice nada sobre a qué host apunta la cadena de conexión.

/** Usuarios con los que no se corre SQL experimental, aunque el host sea correcto. */
export const USUARIOS_PROHIBIDOS = Object.freeze([
  "postgres", "supabase_admin", "service_role", "neondb_owner", "rdsadmin",
]);

/** Lo que se necesita saber de una cadena de conexión, sin la contraseña. */
export function identidadDeDsn(dsn) {
  const m = /^([a-z][a-z0-9+.-]*):\/\/([^:/@]+)(?::[^@]*)?@([^:/?]+)(?::(\d+))?\/([^?]*)/i.exec(
    String(dsn ?? ""),
  );
  if (!m) return null;
  return {
    esquema: m[1].toLowerCase(),
    usuario: m[2].toLowerCase(),
    host: m[3].toLowerCase(),
    puerto: m[4] ? Number(m[4]) : null,
    base: decodeURIComponent(m[5] ?? "").toLowerCase(),
  };
}

/**
 * El identificador de proyecto Supabase que hay dentro de un host.
 *
 * Sirve tanto para `db.<ref>.supabase.co` como para los hosts del pooler, que
 * llevan el ref en el usuario y no en el host. Se devuelve null cuando no se
 * puede determinar: null significa "no sé", y "no sé" tiene que abortar.
 */
export function refDeProyecto({ host, usuario } = {}) {
  const porHost = /^(?:db|aws-[^.]+)\.([a-z0-9]{20})\.supabase\.(?:co|com)$/i.exec(host ?? "");
  if (porHost) return porHost[1].toLowerCase();
  const enHost = /\b([a-z]{20})\b/.exec(host ?? "");
  if (enHost && /supabase/i.test(host ?? "")) return enHost[1].toLowerCase();
  const porUsuario = /^[^.]+\.([a-z0-9]{20})$/i.exec(usuario ?? "");
  if (porUsuario) return porUsuario[1].toLowerCase();
  return null;
}

export const MOTIVOS = Object.freeze({
  SIN_DSN: "no se recibió ninguna cadena de conexión",
  DSN_INVALIDO: "la cadena de conexión no se pudo interpretar",
  SIN_EXPECTATIVA: "no se declaró qué destino se espera (ERETZ_DB_TARGET_EXPECT)",
  ES_PRODUCCION: "el destino coincide con el proyecto marcado como producción",
  DESTINO_DISTINTO: "el destino no coincide con el esperado",
  REF_DESCONOCIDA: "no se pudo determinar el proyecto del destino",
  USUARIO_PROHIBIDO: "el usuario de la conexión tiene privilegio excesivo",
});

/**
 * Decide si se puede correr contra este destino.
 *
 * Todos los parámetros son opcionales a propósito: que falten es exactamente
 * uno de los casos que hay que atrapar, no un error de tipos.
 *
 * @param {object} [opciones]
 * @param {string} [opciones.dsn]              cadena de conexión
 * @param {string} [opciones.esperado]         ref del proyecto que se espera
 * @param {string} [opciones.produccion]       ref del proyecto de producción
 * @param {boolean} [opciones.requiereDdl]     si va a ejecutar DDL
 * @returns {{permitido: boolean, motivo?: string, detalle?: object}}
 */
export function evaluarDestino({ dsn, esperado, produccion, requiereDdl = true } = {}) {
  if (!dsn) return { permitido: false, motivo: MOTIVOS.SIN_DSN };

  const id = identidadDeDsn(dsn);
  if (!id) return { permitido: false, motivo: MOTIVOS.DSN_INVALIDO };

  const detalle = { host: id.host, usuario: id.usuario, base: id.base };

  // Se exige la declaración ANTES de mirar nada más. Sin expectativa no hay
  // nada contra qué comparar, y "parece de preview" no es una comprobación.
  if (!esperado) return { permitido: false, motivo: MOTIVOS.SIN_EXPECTATIVA, detalle };

  const ref = refDeProyecto(id);
  detalle.ref = ref;
  if (!ref) return { permitido: false, motivo: MOTIVOS.REF_DESCONOCIDA, detalle };

  // El ref de producción se rechaza aunque coincida con lo esperado: si alguien
  // declara producción como destino esperado, lo que hay es un error de
  // configuración, no un permiso.
  if (produccion && ref === produccion.toLowerCase()) {
    return { permitido: false, motivo: MOTIVOS.ES_PRODUCCION, detalle };
  }

  if (ref !== esperado.toLowerCase()) {
    return { permitido: false, motivo: MOTIVOS.DESTINO_DISTINTO, detalle };
  }

  if (requiereDdl && USUARIOS_PROHIBIDOS.includes(id.usuario)) {
    return { permitido: false, motivo: MOTIVOS.USUARIO_PROHIBIDO, detalle };
  }

  return { permitido: true, detalle };
}

/**
 * Lee el entorno y aborta si el destino no está demostrado.
 *
 * @param {Record<string, string|undefined>} [env]
 * @param {{requiereDdl?: boolean}} [opciones]
 */
export function exigirDestinoSeguro(env = process.env, { requiereDdl = true } = {}) {
  const veredicto = evaluarDestino({
    dsn: env.ERETZ_DB_TARGET_URL || env.SUPABASE_DATABASE_URL,
    esperado: env.ERETZ_DB_TARGET_EXPECT,
    produccion: env.ERETZ_DB_PRODUCTION_REF,
    requiereDdl,
  });
  if (!veredicto.permitido) {
    const d = veredicto.detalle ?? {};
    // Se imprime host, usuario y ref; nunca la contraseña.
    throw new Error(
      `Destino de base no autorizado: ${veredicto.motivo}. ` +
        `host=${d.host ?? "?"} usuario=${d.usuario ?? "?"} ref=${d.ref ?? "?"}`,
    );
  }
  return veredicto.detalle;
}
