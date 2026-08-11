import "server-only";

import postgres, { type Sql } from "postgres";

// Conexión de ESCRITURA aislada y opcional, separada de la conexión de sólo
// lectura de la app. Usa un rol dedicado (eretz_app_writer) con INSERT únicamente
// sobre las tablas de señal, vía ERETZ_WRITE_DATABASE_URL. Si esa variable no está
// configurada (p. ej. preview de sólo lectura), las escrituras son un no-op y los
// endpoints igualmente devuelven su acuse (sin persistir). Nunca usa el rol RO ni
// BYPASSRLS global.

let writer: Sql | null = null;

function writerUrl(): string {
  return process.env.ERETZ_WRITE_DATABASE_URL?.trim() || "";
}

function writerDb(): Sql | null {
  const url = writerUrl();
  if (!url) return null;
  if (!writer) {
    writer = postgres(url, {
      max: 1,
      idle_timeout: 20,
      connect_timeout: 10,
      max_lifetime: 300,
      prepare: false,
      ssl: "require",
      connection: { application_name: "eretz-app-writer" },
      onnotice: () => undefined,
    });
  }
  return writer;
}

// Whitelist ESTRICTA: sólo estas tablas y columnas puede insertar la app. Evita
// cualquier inyección de identificadores (tabla/columnas son literales tipados).
const WRITABLE = {
  perfil_claims: ["tipo", "entidad_id", "nombre", "email", "telefono", "rol", "mensaje", "estado"],
  reportes_publicacion: ["propiedad_id", "motivo", "detalle", "email", "estado"],
} as const;

export type WritableTable = keyof typeof WRITABLE;
export type WriteResult = { persisted: boolean; reason?: "no_writer" | "error" };

export function isWriterConfigured(): boolean {
  return Boolean(writerUrl());
}

// La persistencia es OBLIGATORIA en entornos reales (Preview/Production). En esos
// entornos, si no se pudo persistir, el endpoint devuelve 503 en vez de un éxito
// falso. En dev/test la persistencia no es obligatoria (permite no-op/mocks).
export function persistenceRequired(): boolean {
  return (
    process.env.ERETZ_PERSISTENCE_REQUIRED === "1" ||
    process.env.VERCEL === "1" ||
    process.env.NODE_ENV === "production"
  );
}

// Inserta una fila de señal. `reason` distingue "no_writer" (no configurado) de
// "error" (falló la escritura). Nunca loguea la URL ni la password: sólo el
// mensaje de error del driver.
export async function insertSignal(
  table: WritableTable,
  data: Record<string, unknown>,
): Promise<WriteResult> {
  const sql = writerDb();
  if (!sql) return { persisted: false, reason: "no_writer" };
  const cols = WRITABLE[table].filter((c) => data[c] !== undefined && data[c] !== null && data[c] !== "");
  if (cols.length === 0) return { persisted: false, reason: "error" };
  try {
    const colList = cols.join(", ");
    const placeholders = cols.map((_, i) => `$${i + 1}`).join(", ");
    const values = cols.map((c) => data[c]);
    await sql.begin(async (tx) => {
      await tx.unsafe(`INSERT INTO public.${table} (${colList}) VALUES (${placeholders})`, values as never[]);
    });
    return { persisted: true };
  } catch (error) {
    // Sólo el mensaje del driver — nunca la connection string ni la password.
    console.error("ERETZ insertSignal failed", table, error instanceof Error ? error.message : "unknown error");
    return { persisted: false, reason: "error" };
  }
}
