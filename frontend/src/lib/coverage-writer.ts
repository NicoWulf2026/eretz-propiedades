import postgres, { type Sql } from "postgres";

// Escritor TEMPORAL de Agency Coverage.
//
// Sigue el patrón de db-writer.ts pero con credencial propia y aislada. No
// reutiliza ninguna de las dos conexiones existentes, y por razones distintas:
//
//   SUPABASE_DATABASE_URL  es el rol de sólo lectura. Cada operación abre una
//                          transacción READ ONLY, así que no puede insertar.
//   ERETZ_WRITE_DATABASE_URL  es eretz_app_writer, creado para claims/reportes.
//                          Ampliarlo para esta campaña le daría alcance sobre
//                          staging de forma permanente, que es justo lo que no
//                          se quiere.
//
// Por eso hay una tercera variable, que se habilita en Preview mientras dura el
// rollout y se retira después. Si no está configurada, todo esto es un no-op.

let writer: Sql | null = null;

const ENV_VAR = "ERETZ_AGENCY_COVERAGE_DATABASE_URL";
export const SOURCE_NAME = "roomix_coverage_v1";

// Whitelist estricta, igual que en db-writer: tabla y columnas son literales
// tipados, nunca vienen del request.
const TABLE = "inmobiliarias_staging" as const;
const COLUMNS = [
  "nombre", "nombre_limpio", "nombre_normalizado", "web", "url_listado",
  "direccion", "barrio", "ciudad", "provincia", "pais", "telefono",
  "fuente", "estado_scraping", "needs_manual_review", "revision_notas",
  "url_perfil_zonaprop", "metadata_zonaprop",
] as const;

export type CoverageRow = Partial<Record<(typeof COLUMNS)[number], unknown>>;

function coverageUrl(): string {
  return process.env[ENV_VAR]?.trim() || "";
}

export function isCoverageWriterConfigured(): boolean {
  return coverageUrl().length > 0;
}

/** Preview y sólo Preview. Production nunca, ni por accidente de configuración. */
export function isPreviewEnvironment(): boolean {
  const env = process.env.VERCEL_ENV;
  // Fuera de Vercel (desarrollo local) se permite; en Vercel debe ser preview.
  if (!process.env.VERCEL) return true;
  return env === "preview";
}

function coverageDb(): Sql | null {
  const url = coverageUrl();
  if (!url) return null;
  if (!writer) {
    writer = postgres(url, {
      max: 1,
      idle_timeout: 20,
      connect_timeout: 10,
      max_lifetime: 300,
      prepare: false,
      ssl: "require",
      connection: { application_name: "eretz-agency-coverage" },
      onnotice: () => undefined,
    });
  }
  return writer;
}

/** Nunca deja escapar la connection string ni fragmentos de ella. */
function safeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : "unknown error";
  return raw
    .replace(/postgres(?:ql)?:\/\/[^\s]*/gi, "<dsn>")
    .replace(/password[^\s,;]*/gi, "<redacted>")
    .slice(0, 200);
}

export type Preflight = {
  ok: boolean;
  role?: string;
  canSelectMain?: boolean;
  canInsertStaging?: boolean;
  canUpdateStaging?: boolean;
  canDeleteStaging?: boolean;
  stagingSchema?: string;
  uniqueIndexes?: string[];
  error?: string;
};

/** Comprueba que el rol tenga exactamente el alcance esperado y ni uno más. */
export async function preflight(): Promise<Preflight> {
  const sql = coverageDb();
  if (!sql) return { ok: false, error: "writer no configurado" };
  try {
    const rows = await sql.unsafe<Array<Record<string, unknown>>>(`
      select current_user as role,
             has_table_privilege('public.inmobiliarias_main', 'SELECT')      as can_select_main,
             has_table_privilege('public.${TABLE}', 'INSERT')                as can_insert_staging,
             has_table_privilege('public.${TABLE}', 'UPDATE')                as can_update_staging,
             has_table_privilege('public.${TABLE}', 'DELETE')                as can_delete_staging
    `);
    // De esto depende que `on conflict do nothing` sea una red real: sin índice
    // único no hay conflicto que detectar, y la idempotencia queda apoyada sólo
    // en el dedupe de aplicación. Conviene saberlo antes de escribir, no después.
    const idx = await sql.unsafe<Array<{ def: string }>>(`
      select pg_get_indexdef(i.oid) as def
        from pg_index x
        join pg_class c on c.oid = x.indrelid
        join pg_class i on i.oid = x.indexrelid
        join pg_namespace n on n.oid = c.relnamespace
       where n.nspname = 'public' and c.relname = '${TABLE}' and x.indisunique
    `);
    const r = rows[0] ?? {};
    return {
      uniqueIndexes: idx.map((v) => v.def),
      ok: Boolean(r.can_select_main) && Boolean(r.can_insert_staging),
      role: String(r.role ?? ""),
      canSelectMain: Boolean(r.can_select_main),
      canInsertStaging: Boolean(r.can_insert_staging),
      canUpdateStaging: Boolean(r.can_update_staging),
      canDeleteStaging: Boolean(r.can_delete_staging),
      stagingSchema: "public",
    };
  } catch (error) {
    return { ok: false, error: safeError(error) };
  }
}

/** Claves ya presentes, leídas en el momento y no de un snapshot del crosswalk. */
export async function existingKeys(): Promise<{ main: Set<string>; staging: Set<string> }> {
  const sql = coverageDb();
  if (!sql) return { main: new Set(), staging: new Set() };
  const main = await sql.unsafe<Array<{ k: string }>>(
    `select lower(coalesce(nombre_normalizado, nombre)) as k from public.inmobiliarias_main`);
  const staging = await sql.unsafe<Array<{ k: string }>>(
    `select lower(coalesce(nombre_normalizado, nombre)) as k from public.${TABLE}`);
  return {
    main: new Set(main.map((r) => r.k).filter(Boolean)),
    staging: new Set(staging.map((r) => r.k).filter(Boolean)),
  };
}

export type BatchResult = { inserted: number; skipped: number; error?: string };

/**
 * Inserta un lote. Cada lote va en su propia transacción, así que un fallo
 * revierte ese lote y no la campaña. `on conflict do nothing` hace que
 * reejecutar el mismo lote no duplique.
 */
export async function insertBatch(rows: CoverageRow[]): Promise<BatchResult> {
  const sql = coverageDb();
  if (!sql) return { inserted: 0, skipped: rows.length, error: "writer no configurado" };
  if (rows.length === 0) return { inserted: 0, skipped: 0 };

  let inserted = 0;
  let skipped = 0;
  try {
    await sql.begin(async (tx) => {
      for (const row of rows) {
        // La fuente la fija el servidor, no el request: nadie puede escribir
        // en nombre de otro import.
        const payload: CoverageRow = { ...row, fuente: SOURCE_NAME };
        const cols = COLUMNS.filter((c) => payload[c] !== undefined);
        if (cols.length === 0) { skipped += 1; continue; }
        const colList = cols.map((c) => `"${c}"`).join(", ");
        const placeholders = cols.map((_, i) => `$${i + 1}`).join(", ");
        const values = cols.map((c) => {
          const v = payload[c];
          return v !== null && typeof v === "object" ? JSON.stringify(v) : v;
        });
        const res = await tx.unsafe(
          `insert into public.${TABLE} (${colList}) values (${placeholders}) on conflict do nothing`,
          values as never[]);
        inserted += (res as unknown as { count?: number }).count ?? 0;
      }
    });
    return { inserted, skipped };
  } catch (error) {
    return { inserted: 0, skipped: rows.length, error: safeError(error) };
  }
}

export type StagingStats = { total: number; mine: number; distinct: number };

export async function stagingStats(): Promise<StagingStats> {
  const sql = coverageDb();
  if (!sql) return { total: 0, mine: 0, distinct: 0 };
  const rows = await sql.unsafe<Array<Record<string, unknown>>>(`
    select count(*)::int as total,
           count(*) filter (where fuente = '${SOURCE_NAME}')::int as mine,
           count(distinct lower(coalesce(nombre_normalizado, nombre)))
             filter (where fuente = '${SOURCE_NAME}')::int as distinct_count
      from public.${TABLE}`);
  const r = rows[0] ?? {};
  return {
    total: Number(r.total ?? 0),
    mine: Number(r.mine ?? 0),
    distinct: Number(r.distinct_count ?? 0),
  };
}
