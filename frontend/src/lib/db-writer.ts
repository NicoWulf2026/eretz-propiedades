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

export function isWriterConfigured(): boolean {
  return Boolean(writerUrl());
}

// Inserta una fila de señal. Devuelve { persisted } — false si no hay writer
// configurado o si la escritura falla (el endpoint decide cómo responder).
export async function insertSignal(
  table: WritableTable,
  data: Record<string, unknown>,
): Promise<{ persisted: boolean }> {
  const sql = writerDb();
  if (!sql) return { persisted: false };
  const cols = WRITABLE[table].filter((c) => data[c] !== undefined && data[c] !== null && data[c] !== "");
  if (cols.length === 0) return { persisted: false };
  try {
    const colList = cols.join(", ");
    const placeholders = cols.map((_, i) => `$${i + 1}`).join(", ");
    const values = cols.map((c) => data[c]);
    await sql.begin(async (tx) => {
      await tx.unsafe(`INSERT INTO public.${table} (${colList}) VALUES (${placeholders})`, values as never[]);
    });
    return { persisted: true };
  } catch (error) {
    console.error("ERETZ insertSignal failed", table, error instanceof Error ? error.message : "unknown error");
    return { persisted: false };
  }
}
