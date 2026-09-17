// Qué necesita la aplicación de la base, y cómo comprobar que una base lo tiene.
//
// Existe porque el repositorio NO define `public.propiedades`. `MIGRATION_ORDER.md`
// remite a una "sanitized schema baseline" capturada por la auditoría, y esa
// baseline no está versionada. Las migraciones de `supabase/migrations/` son
// incrementales: dan por sentado que la tabla ya existe.
//
// Consecuencia práctica: hoy no se puede levantar un entorno desde cero
// usando sólo lo que hay en Git.
//
// Este archivo NO inventa el esquema faltante. Escribir un `CREATE TABLE
// propiedades` a partir de lo que el código consulta sería adivinar tipos,
// nulabilidad, defaults, claves e índices, y una base "parecida" es peor que
// no tener base: los benchmarks medirían otra cosa y nadie lo notaría.
//
// Lo que sí hace es declarar el CONTRATO —qué relaciones y columnas tiene que
// haber para que la aplicación funcione— derivado de lo que el código
// realmente consulta. Sirve para dos cosas:
//
//   1. verificar que una Preview recién creada sirve, antes de invertir horas
//      en cargarla y medirla;
//   2. detectar deriva entre entornos.

/**
 * Columnas que la aplicación lee de `public.propiedades`.
 *
 * Salen de `src/lib/property-sql.ts` y `src/lib/property-mapper.ts`. Si el
 * código empieza a leer una columna nueva y no se agrega acá, el verificador
 * dejará de proteger contra su ausencia: por eso hay un test que compara esta
 * lista contra lo que el SQL menciona.
 */
export const COLUMNAS_PROPIEDADES = Object.freeze([
  "id",
  "titulo",
  "operacion",
  "tipo_propiedad",
  "estado",
  "precio",
  "moneda",
  "expensas",
  "apto_credito",
  "provincia",
  "ciudad",
  "barrio",
  "direccion",
  "latitud",
  "longitud",
  "ambientes",
  "dormitorios",
  "banos",
  "cocheras",
  "antiguedad",
  "superficie_total",
  "superficie_cubierta",
  "superficie_terreno",
  "imagenes",
  "plano_url",
  "video_url",
  "agente_nombre",
  "fecha_publicacion",
  "created_at",
  "updated_at",
]);

export const COLUMNAS_INMOBILIARIAS = Object.freeze([
  "id",
  "nombre",
]);

/** Relaciones que tienen que existir para que la aplicación arranque. */
export const RELACIONES_REQUERIDAS = Object.freeze([
  { schema: "public", nombre: "propiedades", columnas: COLUMNAS_PROPIEDADES },
  { schema: "public", nombre: "inmobiliarias_main", columnas: COLUMNAS_INMOBILIARIAS },
]);

/** Extensiones de las que depende el comportamiento actual. */
export const EXTENSIONES_REQUERIDAS = Object.freeze(["postgis"]);

/**
 * Relaciones del Quality Gate. Se verifican aparte porque su ausencia no
 * impide que la aplicación funcione —sigue filtrando en Node— pero sí impide
 * el camino nuevo.
 */
export const RELACIONES_GATE = Object.freeze([
  { schema: "eretz_gate", nombre: "eligibility" },
  { schema: "eretz_gate", nombre: "manifest" },
  { schema: "eretz_gate", nombre: "active_manifest" },
  { schema: "eretz_gate", nombre: "visible_property_ids" },
]);

export const FALTA = Object.freeze({
  RELACION: "relacion_faltante",
  COLUMNA: "columna_faltante",
  EXTENSION: "extension_faltante",
});

/**
 * Compara lo que la base tiene contra lo que la aplicación necesita.
 *
 * Se le pasa lo observado en vez de consultarlo acá para poder probarlo sin
 * una base, y para que quien llame decida cómo obtenerlo.
 *
 * Todo es opcional: una base sin nada es una entrada válida, y justamente la
 * que no debe pasar por casualidad.
 *
 * @param {object} [observado]
 * @param {Array<{schema:string,nombre:string,columna:string}>} [observado.columnas]
 * @param {string[]} [observado.extensiones]
 * @param {boolean} [incluirGate]
 */
export function verificarContrato(observado = {}, incluirGate = false) {
  const columnas = observado.columnas ?? [];
  const extensiones = (observado.extensiones ?? []).map((e) => String(e).toLowerCase());

  const presentes = new Map();
  for (const c of columnas) {
    const clave = `${c.schema}.${c.nombre}`;
    if (!presentes.has(clave)) presentes.set(clave, new Set());
    presentes.get(clave).add(c.columna);
  }

  const faltas = [];

  for (const rel of RELACIONES_REQUERIDAS) {
    const clave = `${rel.schema}.${rel.nombre}`;
    const cols = presentes.get(clave);
    if (!cols) {
      faltas.push({ tipo: FALTA.RELACION, relacion: clave });
      continue;  // sin la relación, listar sus columnas faltantes es ruido
    }
    for (const columna of rel.columnas) {
      if (!cols.has(columna)) {
        faltas.push({ tipo: FALTA.COLUMNA, relacion: clave, columna });
      }
    }
  }

  for (const ext of EXTENSIONES_REQUERIDAS) {
    if (!extensiones.includes(ext)) {
      faltas.push({ tipo: FALTA.EXTENSION, extension: ext });
    }
  }

  if (incluirGate) {
    for (const rel of RELACIONES_GATE) {
      const clave = `${rel.schema}.${rel.nombre}`;
      if (!presentes.has(clave)) faltas.push({ tipo: FALTA.RELACION, relacion: clave });
    }
  }

  return { cumple: faltas.length === 0, faltas };
}

/** Consulta que junta lo necesario para verificar. Sólo lectura. */
export const SQL_OBSERVAR_COLUMNAS = `
  select table_schema as schema, table_name as nombre, column_name as columna
  from information_schema.columns
  where table_schema in ('public', 'eretz_gate')
`;

export const SQL_OBSERVAR_EXTENSIONES = `select extname from pg_extension`;

/** Resumen legible para un operador. */
export function describirFaltas(faltas) {
  if (!faltas.length) return "la base cumple el contrato de la aplicación";
  return faltas
    .map((f) => {
      if (f.tipo === FALTA.RELACION) return `falta la relación ${f.relacion}`;
      if (f.tipo === FALTA.COLUMNA) return `falta ${f.relacion}.${f.columna}`;
      return `falta la extensión ${f.extension}`;
    })
    .join("\n");
}
