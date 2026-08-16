import postgres, { type Sql } from "postgres";

// Puente TEMPORAL de Agency Coverage.
//
// Usa `ERETZ_WRITE_DATABASE_URL` (rol `eretz_app_writer`), pero únicamente para
// invocar tres funciones SECURITY DEFINER. El rol conserva exactamente sus
// grants anteriores — INSERT sobre perfil_claims y reportes_publicacion — y no
// tiene SELECT/INSERT/UPDATE/DELETE directos sobre inmobiliarias_main ni
// inmobiliarias_staging. Este módulo tampoco los necesita: toda la escritura
// ocurre dentro de las funciones, que son las dueñas del alcance.
//
// Por eso acá no hay ningún SQL contra esas tablas. Si alguna vez aparece uno,
// está mal por dos motivos a la vez: el rol lo rechazaría, y saltearía el
// dedupe y el advisory lock que las funciones ya implementan.

let bridge: Sql | null = null;

const ENV_VAR = "ERETZ_WRITE_DATABASE_URL";
export const SOURCE_NAME = "roomix_agency_coverage";

// Las tres únicas sentencias que este módulo puede ejecutar. Son constantes del
// módulo: no se concatenan, no se derivan y nada del request participa en su
// construcción. Lo único que viaja desde afuera son los dos parámetros ligados
// de `stage`.
const RPC = {
  preflight: "select public.eretz_agency_coverage_preflight_v1() as result",
  snapshot: "select * from public.eretz_agency_coverage_snapshot_v1()",
  stage: "select * from public.eretz_agency_coverage_stage_v1($1, $2)",
  // El preflight corre DENTRO de una función SECURITY DEFINER, así que
  // `current_user` es el dueño (postgres) y los privilegios que informa son los
  // del dueño, no los del rol que llama. Esto se ejecuta fuera de toda función,
  // donde `current_user` sí es el rol de la conexión, y es la única forma de
  // confirmar que `eretz_app_writer` no tiene acceso directo a las tablas.
  // Consulta sólo el catálogo: nombra las tablas como texto y no lee ni una
  // fila de ninguna de las dos.
  identity: `select session_user::text as session_user,
                    current_user::text as current_user,
                    has_table_privilege('public.inmobiliarias_main', 'SELECT') as main_select,
                    has_table_privilege('public.inmobiliarias_staging', 'SELECT') as staging_select,
                    has_table_privilege('public.inmobiliarias_staging', 'INSERT') as staging_insert,
                    has_table_privilege('public.inmobiliarias_staging', 'UPDATE') as staging_update,
                    has_table_privilege('public.inmobiliarias_staging', 'DELETE') as staging_delete`,
} as const;

// Claves admitidas en el payload. La función decide qué columnas escribe; esto
// es defensa en profundidad para que no viaje nada que no sea del import.
// `fuente` no está: la fija el servidor.
const PAYLOAD_KEYS = [
  "nombre", "nombre_limpio", "nombre_normalizado", "web", "url_listado",
  "direccion", "barrio", "ciudad", "provincia", "pais", "telefono",
  "estado_scraping", "needs_manual_review", "revision_notas",
  "url_perfil_zonaprop", "metadata_zonaprop",
] as const;

export type CoveragePayload = Partial<Record<(typeof PAYLOAD_KEYS)[number], unknown>>;

function bridgeUrl(): string {
  return process.env[ENV_VAR]?.trim() || "";
}

export function isCoverageBridgeConfigured(): boolean {
  return bridgeUrl().length > 0;
}

/** Preview y sólo Preview. Production nunca, ni por accidente de configuración. */
export function isPreviewEnvironment(): boolean {
  // Fuera de Vercel (desarrollo local) se permite; en Vercel debe ser preview.
  if (!process.env.VERCEL) return true;
  return process.env.VERCEL_ENV === "preview";
}

function db(): Sql | null {
  const url = bridgeUrl();
  if (!url) return null;
  if (!bridge) {
    bridge = postgres(url, {
      max: 1,
      idle_timeout: 20,
      connect_timeout: 10,
      max_lifetime: 300,
      prepare: false,
      ssl: "require",
      connection: { application_name: "eretz-agency-coverage-bridge" },
      onnotice: () => undefined,
    });
  }
  return bridge;
}

/** Nunca deja escapar la connection string ni fragmentos de ella. */
export function safeError(error: unknown): string {
  const raw = error instanceof Error ? error.message : "unknown error";
  return raw
    .replace(/postgres(?:ql)?:\/\/[^\s]*/gi, "<dsn>")
    .replace(/password[^\s,;]*/gi, "<redacted>")
    .slice(0, 300);
}

export type RpcResult = { ok: boolean; rows: Array<Record<string, unknown>>; error?: string };

async function run(
  name: keyof typeof RPC,
  params: unknown[] = [],
): Promise<RpcResult> {
  const sql = db();
  if (!sql) return { ok: false, rows: [], error: "puente no configurado" };
  try {
    const rows = await sql.unsafe<Array<Record<string, unknown>>>(
      RPC[name], params as never[]);
    return { ok: true, rows: Array.from(rows) };
  } catch (error) {
    return { ok: false, rows: [], error: safeError(error) };
  }
}

/** `select public.eretz_agency_coverage_preflight_v1()`. No escribe. */
export function callPreflight(): Promise<RpcResult> {
  return run("preflight");
}

/** `select * from public.eretz_agency_coverage_snapshot_v1()`. No escribe. */
export function callSnapshot(): Promise<RpcResult> {
  return run("snapshot");
}

/** Identidad y privilegios REALES del rol de la conexión. Sólo catálogo. */
export function callIdentity(): Promise<RpcResult> {
  return run("identity");
}

export type SnapshotSummary = {
  ok: boolean;
  main: number;
  staging: number;
  stagingPorFuente: Record<string, number>;
  mias: number;
  miasDistintas: number;
  duplicadas: number;
  error?: string;
};

/**
 * El snapshot completo son varios MB: traerlo entero a esta máquina después de
 * cada lote no es viable. Se agrega acá, dentro de la función, y sólo viajan
 * los recuentos. `duplicadas` es el detector: si el total de filas de esta
 * fuente supera a sus nombres normalizados distintos, hay duplicado y el
 * rollout tiene que frenar.
 */
export async function snapshotSummary(): Promise<SnapshotSummary> {
  const r = await callSnapshot();
  const empty = {
    main: 0, staging: 0, stagingPorFuente: {}, mias: 0, miasDistintas: 0, duplicadas: 0,
  };
  if (!r.ok) return { ok: false, ...empty, error: r.error };

  let main = 0, staging = 0;
  const porFuente: Record<string, number> = {};
  const mineNorms = new Set<string>();
  let mias = 0;

  for (const row of r.rows) {
    if (row.source_table === "main") { main += 1; continue; }
    staging += 1;
    const fuente = String(row.fuente ?? "(sin fuente)");
    porFuente[fuente] = (porFuente[fuente] ?? 0) + 1;
    if (fuente !== SOURCE_NAME) continue;
    mias += 1;
    const norm = String(row.nombre_normalizado ?? row.nombre ?? "").toLowerCase();
    if (norm) mineNorms.add(norm);
  }

  return {
    ok: true, main, staging, stagingPorFuente: porFuente,
    mias, miasDistintas: mineNorms.size, duplicadas: mias - mineNorms.size,
  };
}

/** Claves ya presentes, para el dedupe previo y la reconciliación final. */
export async function snapshotKeys(): Promise<{
  ok: boolean; main: string[]; staging: string[]; mias: string[]; error?: string;
}> {
  const r = await callSnapshot();
  if (!r.ok) return { ok: false, main: [], staging: [], mias: [], error: r.error };
  const main: string[] = [], staging: string[] = [], mias: string[] = [];
  for (const row of r.rows) {
    const norm = String(row.nombre_normalizado ?? row.nombre ?? "").toLowerCase().trim();
    if (!norm) continue;
    if (row.source_table === "main") { main.push(norm); continue; }
    staging.push(norm);
    if (row.fuente === SOURCE_NAME) mias.push(norm);
  }
  return { ok: true, main, staging, mias };
}

/**
 * `select * from public.eretz_agency_coverage_stage_v1(candidate_key, payload)`.
 *
 * La función se encarga de todo lo que importa: advisory lock por candidate
 * key, detección de key ya staged, dedupe por nombre_normalizado y por web
 * contra main y contra staging, fuente fijada server-side, insert únicamente en
 * staging, nunca update, nunca delete. Acá no se replica nada de eso —
 * duplicarlo del lado del cliente sólo abriría la puerta a que las dos copias
 * discrepen.
 */
export function callStage(candidateKey: string, payload: CoveragePayload): Promise<RpcResult> {
  const clean: Record<string, unknown> = {};
  for (const k of PAYLOAD_KEYS) {
    if (payload[k] !== undefined) clean[k] = payload[k];
  }
  return run("stage", [candidateKey, JSON.stringify(clean)]);
}
