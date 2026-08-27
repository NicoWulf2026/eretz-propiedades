// Importa el manifiesto del Quality Gate a la relación de elegibilidad.
//
// El riesgo que este script existe para no correr: dejar una ventana en la que
// la versión activa apunte a una carga incompleta. Si eso pasara, la base
// diría que hay menos propiedades visibles de las que hay —o, peor, si alguien
// hubiera escrito la consulta con LEFT JOIN, que hay más—.
//
// Por eso el orden es siempre el mismo y nunca se abrevia:
//
//   1. descargar y verificar checksum del manifiesto;
//   2. parsear, aplicando las mismas reglas que el runtime;
//   3. cargar TODAS las filas bajo la versión nueva, al lado de la vigente;
//   4. comparar lo cargado contra lo esperado;
//   5. recién ahí mover el puntero, en una transacción.
//
// Ante cualquier fallo antes del paso 5, la versión anterior sigue activa y
// nada cambió. Ante un fallo en el paso 5, la transacción revierte. En ningún
// caso el resultado es "se ven más propiedades".

import { createHash } from "node:crypto";
import { exigirDestinoSeguro } from "./db-target-guard.mjs";

/** Cuántas filas por INSERT. 257k filas de a una son 257k viajes. */
export const TAMANO_DE_LOTE = 5_000;

export const CLASIFICACIONES_VISIBLES = Object.freeze([
  "PUBLICABLE_COMPLETE",
  "PUBLICABLE_INCOMPLETE",
]);

export const CLASIFICACIONES = Object.freeze([
  "INVALID",
  "REVIEW_REQUIRED",
  "SOURCE_UNAVAILABLE",
  ...CLASIFICACIONES_VISIBLES,
]);

export function esVisible(clasificacion) {
  return CLASIFICACIONES_VISIBLES.includes(clasificacion);
}

/** La versión es el hash del contenido, igual que la calcula el runtime. */
export function versionDeManifiesto(contenido) {
  return createHash("sha256").update(contenido).digest("hex").slice(0, 16);
}

export function checksumDeContenido(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

/**
 * Parsea el CSV con las MISMAS reglas que el runtime.
 *
 * Se rechaza el manifiesto entero y no la fila: un manifiesto al que le falta
 * una fila no es un manifiesto con una fila menos, es un manifiesto del que no
 * sabemos qué más le falta.
 */
export function parsearManifiesto(contenido) {
  const lineas = String(contenido ?? "").trim().split(/\r?\n/);
  if (lineas.shift() !== "property_id,classification,preview_visible") {
    throw new Error("Encabezado de manifiesto inválido");
  }
  const filas = [];
  const vistos = new Set();
  for (const [i, linea] of lineas.entries()) {
    if (!linea) continue;
    const [id, clasificacion, visible, ...sobra] = linea.split(",");
    if (!/^\d+$/.test(id ?? "") || !CLASIFICACIONES.includes(clasificacion) || sobra.length) {
      throw new Error(`Fila inválida ${i + 2}`);
    }
    if (vistos.has(id)) throw new Error(`Propiedad duplicada ${id}`);
    const esperado = esVisible(clasificacion);
    if ((visible === "true") !== esperado) {
      throw new Error(`Visibilidad incoherente para ${id}`);
    }
    vistos.add(id);
    filas.push({ propertyId: id, classification: clasificacion, visible: esperado });
  }
  if (!filas.length) throw new Error("Manifiesto vacío");
  return filas;
}

/** Parte las filas en lotes de tamaño acotado, preservando el orden. */
export function enLotes(filas, tamano = TAMANO_DE_LOTE) {
  const lotes = [];
  for (let i = 0; i < filas.length; i += tamano) lotes.push(filas.slice(i, i + tamano));
  return lotes;
}

export const MOTIVOS_NO_ACTIVAR = Object.freeze({
  FALTAN_FILAS: "se cargaron menos filas de las esperadas",
  SOBRAN_FILAS: "se cargaron más filas de las esperadas",
  VISIBLES_DISTINTOS: "la cantidad de visibles no coincide",
  SIN_VISIBLES: "el manifiesto no deja ninguna propiedad visible",
  CAIDA_SOSPECHOSA: "la cantidad de visibles cae más de lo tolerado",
});

/**
 * Decide si la versión recién cargada puede activarse.
 *
 * La comprobación que más importa no es la de integridad —esa ya la hizo el
 * checksum— sino la última: una caída brusca de visibles suele ser un
 * manifiesto mal generado aguas arriba, y activarlo vaciaría el catálogo sin
 * que nada hubiera fallado técnicamente. Ante la duda no se activa; la versión
 * anterior sigue sirviendo, que es un estado correcto y conocido.
 *
 * @param {object} p
 * @param {number} p.esperadoFilas
 * @param {number} p.esperadoVisibles
 * @param {number} p.cargadoFilas
 * @param {number} p.cargadoVisibles
 * @param {number|null} [p.visiblesPrevios]  visibles de la versión activa;
 *        null cuando es la primera importación y no hay con qué comparar
 * @param {number} [p.caidaTolerada]    fracción de caída aceptable (0.2 = 20%)
 */
export function decidirActivacion({
  esperadoFilas,
  esperadoVisibles,
  cargadoFilas,
  cargadoVisibles,
  visiblesPrevios = null,
  caidaTolerada = 0.2,
} = {}) {
  if (cargadoFilas < esperadoFilas) {
    return { activar: false, motivo: MOTIVOS_NO_ACTIVAR.FALTAN_FILAS };
  }
  if (cargadoFilas > esperadoFilas) {
    return { activar: false, motivo: MOTIVOS_NO_ACTIVAR.SOBRAN_FILAS };
  }
  if (cargadoVisibles !== esperadoVisibles) {
    return { activar: false, motivo: MOTIVOS_NO_ACTIVAR.VISIBLES_DISTINTOS };
  }
  if (cargadoVisibles === 0) {
    return { activar: false, motivo: MOTIVOS_NO_ACTIVAR.SIN_VISIBLES };
  }
  if (
    visiblesPrevios !== null &&
    visiblesPrevios > 0 &&
    cargadoVisibles < visiblesPrevios * (1 - caidaTolerada)
  ) {
    return {
      activar: false,
      motivo: MOTIVOS_NO_ACTIVAR.CAIDA_SOSPECHOSA,
      detalle: { visiblesPrevios, cargadoVisibles },
    };
  }
  return { activar: true };
}

/** Resumen de lo que se va a cargar, sin tocar la base. */
export function planDeImportacion(contenido, { checksum } = {}) {
  const filas = parsearManifiesto(contenido);
  return {
    version: versionDeManifiesto(contenido),
    checksum: checksum ?? null,
    filas,
    totalFilas: filas.length,
    totalVisibles: filas.reduce((n, f) => n + (f.visible ? 1 : 0), 0),
    lotes: enLotes(filas).length,
  };
}

// --- ejecución -------------------------------------------------------------
// Necesita una conexión. El guard corre PRIMERO: importar contra la base
// equivocada es exactamente el accidente que no queremos.

export async function importar({ sql, contenido, checksum, env = process.env }) {
  exigirDestinoSeguro(env, { requiereDdl: true });

  const plan = planDeImportacion(contenido, { checksum });

  const previos = await sql`
    select m.visible_count
    from eretz_gate.active_manifest a
    join eretz_gate.manifest m on m.manifest_version = a.manifest_version
  `;
  const visiblesPrevios = previos.length ? Number(previos[0].visible_count) : null;

  // Paso 3: cargar al lado de la vigente. Si esta versión ya estaba cargada a
  // medias por un intento anterior, se limpia antes: media carga es peor que
  // ninguna.
  await sql`delete from eretz_gate.eligibility where manifest_version = ${plan.version}`;
  for (const lote of enLotes(plan.filas)) {
    await sql`
      insert into eretz_gate.eligibility ${sql(
        lote.map((f) => ({
          manifest_version: plan.version,
          property_id: f.propertyId,
          classification: f.classification,
          visible: f.visible,
        })),
      )}
    `;
  }

  // Paso 4: contar lo que quedó en la base, no lo que creímos mandar.
  const [conteo] = await sql`
    select count(*)::int as filas,
           count(*) filter (where visible)::int as visibles
    from eretz_gate.eligibility
    where manifest_version = ${plan.version}
  `;

  const veredicto = decidirActivacion({
    esperadoFilas: plan.totalFilas,
    esperadoVisibles: plan.totalVisibles,
    cargadoFilas: Number(conteo.filas),
    cargadoVisibles: Number(conteo.visibles),
    visiblesPrevios,
  });

  if (!veredicto.activar) {
    // No se borra lo cargado: queda para inspeccionar por qué no coincidió.
    // Lo que no cambia es cuál está activa.
    return { activada: false, version: plan.version, ...veredicto };
  }

  // Paso 5: el swap, en una transacción.
  await sql.begin(async (tx) => {
    await tx`
      insert into eretz_gate.manifest
        (manifest_version, checksum_sha256, row_count, visible_count)
      values (${plan.version}, ${plan.checksum}, ${plan.totalFilas}, ${plan.totalVisibles})
      on conflict (manifest_version) do update
        set row_count = excluded.row_count,
            visible_count = excluded.visible_count,
            imported_at = now()
    `;
    await tx`
      insert into eretz_gate.active_manifest (unica, manifest_version)
      values (true, ${plan.version})
      on conflict (unica) do update
        set manifest_version = excluded.manifest_version, activated_at = now()
    `;
    await tx`
      update eretz_gate.manifest set activated_at = now()
      where manifest_version = ${plan.version}
    `;
  });

  return { activada: true, version: plan.version, filas: plan.totalFilas, visibles: plan.totalVisibles };
}
