import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { supabase } from "@/lib/supabase-client";
import type { Property, SupabaseProperty } from "@/types/property";

// Sprint F: 25s — el servidor corre desde unidad de red (D:) con latencia alta a Supabase.
// Con 12s el AbortController disparaba antes de que terminaran las queries.
// TODO: reducir cuando se mueva a unidad local o se optimice la infraestructura.
const FETCH_TIMEOUT_MS = 25000;

// Sprint F: columnas directas de propiedades (sin view v_propiedades_frontend_mapa).
// La view tiene timeout (57014) sobre 91k rows y filtro estado='activo' incorrecto (debe ser 'activa').
// ciudad/provincia son columnas directas; inmobiliaria_nombre y geocoding quedan null por ahora.
const FRONTEND_PROPERTY_COLUMNS = [
  "id",
  "inmobiliaria_id",
  "url",
  "titulo",
  "descripcion",
  "precio",
  "moneda",
  "precio_usd",
  "precio_ars",
  "expensas",
  "expensas_moneda",
  "tipo_propiedad",
  "operacion",
  "ambientes",
  "dormitorios",
  "banos",
  "toilettes",
  "cocheras",
  "antiguedad",
  "piso",
  "superficie_total",
  "superficie_cubierta",
  "superficie_terreno",
  "direccion",
  "barrio",
  "ciudad",
  "provincia",
  "pais",
  "latitud",
  "longitud",
  "imagenes",
  "video_url",
  "plano_url",
  "amenities",
  "agente_nombre",
  "agente_telefono",
  "fuente_extraccion",
  "cms_origen",
  "fecha_publicacion",
  "estado",
  "created_at",
  "updated_at",
  "apto_credito",
].join(",");

type GetPropertiesFromSupabaseOptions = {
  limit?: number;
  throwOnError?: boolean;
};

async function withQueryTimeout<T>(
  fn: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    return await fn(controller.signal);
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function getPropertiesFromSupabase(
  options: GetPropertiesFromSupabaseOptions = {},
): Promise<Property[]> {
  const limit = options.limit ?? 50;

  if (!supabase) {
    const message =
      "Supabase is not configured. Check NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.";
    console.error(message);

    if (options.throwOnError) {
      throw new Error(message);
    }

    return [];
  }

  // Asignar a client local para que TypeScript pueda narrowear dentro del closure async.
  const client = supabase;

  try {
    const rows = await withQueryTimeout(async (signal) => {
      // Sprint F: query única directa — ORDER BY id DESC LIMIT n.
      // Antes: arquitectura 2 fases (fetchIds → fetchChunks) = 3 queries seriales/paralelas
      // → latencia 19-38s en unidad de red → AbortError → fallback a mock.
      // Ahora: 1 sola query con índice en id → latencia esperada 5-12s.
      // Decision 13: sin filtro por estado (se muestran todas con badge visible).
      const { data, error } = await client
        .from("propiedades")
        .select(FRONTEND_PROPERTY_COLUMNS)
        .order("id", { ascending: false })
        .limit(limit)
        .abortSignal(signal);

      if (error) {
        throw new Error(error.message);
      }

      return (data ?? []) as unknown as SupabaseProperty[];
    });

    return rows.map(mapSupabasePropertyToProperty);
  } catch (err) {
    if (process.env.NODE_ENV === "development") {
      console.error("[Supabase] Unexpected error:", err);
    }

    if (options.throwOnError) {
      throw err;
    }

    return [];
  }
}
