import "server-only";

import postgres, { type Sql } from "postgres";

// Puente TEMPORAL de Agency Coverage. Se retira al terminar el rollout.
//
// Entra por `SUPABASE_DATABASE_URL` (rol `eretz_preview_ro`), que es la única
// conexión alcanzable: las variables de Preview son Sensitive y Vercel no las
// devuelve, así que la base sólo se consulta desde dentro de un deployment.
//
// La escritura no está activa en esa conexión. `eretz_preview_ro` es miembro de
// `eretz_agency_coverage_writer`, pero ese rol es NOLOGIN y NOINHERIT: sus
// privilegios sólo existen mientras una transacción haga `SET LOCAL ROLE`. Al
// terminar la transacción se apagan solos.
//
// `SET LOCAL` y no `SET`: la conexión pasa por un pooler, donde un cambio de rol
// persistente sobreviviría a la transacción y quedaría activo para el siguiente
// que tome esa misma conexión física.

const ROL_ESCRITOR = "eretz_agency_coverage_writer";
export const SOURCE_NAME = "roomix_agency_coverage";

let pool: Sql | null = null;

export function isPreviewEnvironment(): boolean {
  if (!process.env.VERCEL) return true;
  return process.env.VERCEL_ENV === "preview";
}

function url(): string {
  return process.env.SUPABASE_DATABASE_URL?.trim() || "";
}

export function isConfigured(): boolean {
  return url().length > 0;
}

export function safeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : "unknown error";
  return raw
    .replace(/postgres(?:ql)?:\/\/[^\s]*/gi, "<dsn>")
    .replace(/password[^\s,;]*/gi, "<redacted>")
    .slice(0, 300);
}

function db(): Sql | null {
  const u = url();
  if (!u) return null;
  if (!pool) {
    pool = postgres(u, {
      max: 1, idle_timeout: 20, connect_timeout: 10, max_lifetime: 300,
      prepare: false, ssl: "require",
      connection: { application_name: "eretz-agency-bridge" },
      onnotice: () => undefined,
    });
  }
  return pool;
}

/** Lectura simple, sin elevar rol. */
async function read<T>(query: string): Promise<T[]> {
  const sql = db();
  if (!sql) throw new Error("sin conexión configurada");
  return (await sql.unsafe<T[]>(query)) as unknown as T[];
}

/**
 * Ejecuta algo con el rol de escritura activo.
 *
 * El `SET LOCAL ROLE` va dentro de la misma transacción que el trabajo, y se
 * revierte al cerrarla pase lo que pase.
 */
async function withWriter<T>(fn: (tx: Sql) => Promise<T>): Promise<T> {
  const sql = db();
  if (!sql) throw new Error("sin conexión configurada");
  return sql.begin(async (tx) => {
    // El rol de entrada trae `default_transaction_read_only` activo, asi que la
    // transaccion nace de solo lectura y el INSERT falla aunque el privilegio
    // exista. Se levanta por transaccion, nunca en la sesion: en un pooler un
    // cambio persistente lo heredaria la proxima consulta que tome esa misma
    // conexion fisica. Tiene que ir ANTES de cualquier otra sentencia.
    await tx.unsafe("set local transaction_read_only = off");
    await tx.unsafe(`set local role ${ROL_ESCRITOR}`);
    return fn(tx as unknown as Sql);
  }) as Promise<T>;
}

/** Lectura con el rol del puente activo, para lo que `eretz_preview_ro` no ve. */
function readAsWriter<T>(query: string): Promise<T[]> {
  return withWriter(async (tx) => (await tx.unsafe<T[]>(query)) as unknown as T[]);
}

const IDENTIDAD = `
  select session_user::text as session_user,
         current_user::text as current_user,
         has_table_privilege('public.inmobiliarias_main','SELECT')      as main_select,
         has_table_privilege('public.inmobiliarias_main','INSERT')      as main_insert,
         has_table_privilege('public.inmobiliarias_staging','SELECT')   as staging_select,
         has_table_privilege('public.inmobiliarias_staging','INSERT')   as staging_insert,
         has_table_privilege('public.inmobiliarias_staging','UPDATE')   as staging_update,
         has_table_privilege('public.inmobiliarias_staging','DELETE')   as staging_delete`;

export type Preflight = {
  base: Record<string, unknown>;
  elevado: Record<string, unknown> | null;
  setRoleOk: boolean;
  error?: string;
  pruebas: Array<Record<string, unknown>>;
};

/**
 * Comprueba el mecanismo entero antes de escribir nada.
 *
 * Lo permitido se verifica intentándolo y revirtiendo, no leyendo el catálogo:
 * un grant puede existir y una policy de RLS bloquear igual. Lo prohibido se
 * verifica intentándolo también — si no falla, no está prohibido.
 */
export async function preflight(): Promise<Preflight> {
  const base = (await read<Record<string, unknown>>(IDENTIDAD))[0] ?? {};

  let elevado: Record<string, unknown> | null = null;
  let setRoleOk = false;
  let error: string | undefined;
  try {
    elevado = await withWriter(async (tx) => {
      const r = await tx.unsafe<Array<Record<string, unknown>>>(IDENTIDAD);
      return r[0] ?? {};
    });
    setRoleOk = elevado?.current_user === ROL_ESCRITOR;
  } catch (e) {
    error = safeError(e);
  }

  const casos: Array<{ nombre: string; sql: string; esperado: "permitido" | "denegado" }> = [
    { nombre: "SELECT main", esperado: "permitido",
      sql: "select 1 from public.inmobiliarias_main limit 1" },
    { nombre: "SELECT staging", esperado: "permitido",
      sql: "select 1 from public.inmobiliarias_staging limit 1" },
    { nombre: "INSERT staging", esperado: "permitido",
      sql: `insert into public.inmobiliarias_staging (nombre, fuente)
            values ('__eretz_preflight_rollback__', '${SOURCE_NAME}')` },
    { nombre: "INSERT main", esperado: "denegado",
      sql: "insert into public.inmobiliarias_main (nombre) values ('__eretz_preflight_rollback__')" },
    { nombre: "UPDATE staging", esperado: "denegado",
      sql: "update public.inmobiliarias_staging set nombre = nombre where false" },
    { nombre: "DELETE staging", esperado: "denegado",
      sql: "delete from public.inmobiliarias_staging where false" },
    { nombre: "CREATE TABLE", esperado: "denegado",
      sql: "create table public.__eretz_preflight_should_not_exist (id int)" },
  ];

  const pruebas: Array<Record<string, unknown>> = [];
  for (const caso of casos) {
    let real: "permitido" | "denegado" = "denegado";
    let detalle = "";
    try {
      // La transacción se aborta a propósito: ni siquiera lo permitido queda
      // escrito. El INSERT de prueba nunca llega a existir.
      await withWriter(async (tx) => {
        await tx.unsafe(caso.sql);
        throw new Error("__ERETZ_ROLLBACK__");
      });
      real = "permitido";
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("__ERETZ_ROLLBACK__")) {
        real = "permitido";
      } else {
        real = "denegado";
        detalle = safeError(e);
      }
    }
    pruebas.push({ caso: caso.nombre, esperado: caso.esperado, real,
                   correcto: real === caso.esperado, detalle });
  }

  return { base, elevado, setRoleOk, error, pruebas };
}

/**
 * Recuentos globales, calculados en la base.
 *
 * Va elevado: `eretz_preview_ro` por sí solo no puede leer staging. El SELECT
 * sobre staging existe únicamente mientras el rol del puente está activo.
 */
export function stats(): Promise<Array<Record<string, unknown>>> {
  return readAsWriter(`
    select 'main' as tabla, count(*)::int as total,
           count(*) filter (where nombre_normalizado is null)::int as sin_normalizar,
           count(distinct lower(coalesce(nombre_normalizado, nombre)))::int as claves
      from public.inmobiliarias_main
    union all
    select 'staging', count(*)::int,
           count(*) filter (where nombre_normalizado is null)::int,
           count(distinct lower(coalesce(nombre_normalizado, nombre)))::int
      from public.inmobiliarias_staging`);
}

export function stagingPorFuente(): Promise<Array<Record<string, unknown>>> {
  return readAsWriter(`
    select coalesce(fuente, '(sin fuente)') as fuente, count(*)::int as filas
      from public.inmobiliarias_staging group by 1 order by 2 desc`);
}

/**
 * Lo mínimo para clasificar y deduplicar: identidad y nombre.
 *
 * Deliberadamente NO trae dirección, teléfono ni email. La auditoría y el
 * dedupe se deciden por nombre y origen; el resto sería mover datos de contacto
 * sin necesitarlos.
 */
export function nombres(tabla: "main" | "staging"): Promise<Array<Record<string, unknown>>> {
  const t = tabla === "main" ? "inmobiliarias_main" : "inmobiliarias_staging";
  return readAsWriter(`
    select id, nombre, nombre_normalizado, coalesce(fuente,'(sin fuente)') as fuente
      from public.${t} order by id`);
}

// Whitelist estricta. Tabla y columnas son literales tipados: nada del request
// participa en construir la sentencia.
const COLUMNAS = [
  "nombre", "nombre_limpio", "nombre_normalizado", "web", "url_listado",
  "direccion", "barrio", "ciudad", "provincia", "pais", "telefono",
  "estado_scraping", "needs_manual_review", "revision_notas",
  "url_perfil_zonaprop", "metadata_zonaprop",
] as const;

export type Fila = Partial<Record<(typeof COLUMNAS)[number], unknown>>;
export type Resultado = {
  insertadas: number;
  saltadas: Record<string, number>;
  detalle: Array<Record<string, unknown>>;
  error?: string;
};

/**
 * Inserta un lote en staging, deduplicando DENTRO de la transaccion.
 *
 * El dedupe no puede hacerse en el cliente. Entre que el cliente calcula su
 * lista y el servidor escribe, el estado puede cambiar; la unica comprobacion
 * que vale es la que ocurre bajo la misma transaccion que el insert.
 *
 * La clave se calcula con `lower(btrim(...))` sobre `nombre_normalizado` y, si
 * esta en NULL, sobre `nombre`. Ese fallback importa: 1.983 filas de main
 * tienen la columna vacia y compararlas solo por ella las volveria invisibles,
 * que es exactamente el defecto que produjo las 31 colisiones anteriores.
 *
 * `fuente` la fija el servidor.
 */
export async function insertar(filas: Fila[]): Promise<Resultado> {
  if (filas.length === 0) return { insertadas: 0, saltadas: {}, detalle: [] };
  try {
    return await withWriter(async (tx) => {
      let insertadas = 0;
      const saltadas: Record<string, number> = {};
      const detalle: Array<Record<string, unknown>> = [];

      for (const fila of filas) {
        const clave = String(fila.nombre_normalizado ?? fila.nombre ?? "")
          .trim().toLowerCase();
        if (!clave) {
          saltadas.sin_clave = (saltadas.sin_clave ?? 0) + 1;
          continue;
        }

        const previo = await tx.unsafe<Array<{ origen: string; id: string }>>(`
          select 'main' as origen, id::text as id
            from public.inmobiliarias_main
           where lower(btrim(coalesce(nombre_normalizado, nombre))) = $1
          union all
          select 'staging', id::text
            from public.inmobiliarias_staging
           where lower(btrim(coalesce(nombre_normalizado, nombre))) = $1
           limit 1`, [clave] as never[]);

        if (previo.length > 0) {
          const donde = `ya_en_${previo[0].origen}`;
          saltadas[donde] = (saltadas[donde] ?? 0) + 1;
          detalle.push({ clave, resultado: donde, id: previo[0].id });
          continue;
        }

        const cols = COLUMNAS.filter((c) => fila[c] !== undefined);
        if (cols.length === 0) {
          saltadas.sin_columnas = (saltadas.sin_columnas ?? 0) + 1;
          continue;
        }
        const lista = cols.map((c) => `"${c}"`).join(", ");
        const marcas = cols.map((_, i) => `$${i + 1}`).join(", ");
        const valores = cols.map((c) => {
          const v = fila[c];
          return v !== null && typeof v === "object" ? JSON.stringify(v) : v;
        });
        const res = await tx.unsafe(
          `insert into public.inmobiliarias_staging (${lista}, "fuente")
           values (${marcas}, '${SOURCE_NAME}')`, valores as never[]);
        const n = (res as unknown as { count?: number }).count ?? 0;
        insertadas += n;
        detalle.push({ clave, resultado: "insertada" });
      }
      return { insertadas, saltadas, detalle };
    });
  } catch (e) {
    return { insertadas: 0, saltadas: {}, detalle: [], error: safeError(e) };
  }
}
