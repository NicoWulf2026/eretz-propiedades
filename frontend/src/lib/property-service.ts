import { mockProperties } from "@/lib/property-data";
import { getPropertiesFromSupabase } from "@/lib/property-supabase-service";
import type { Property, PropertyOperation } from "@/types/property";

export type PropertyDataSource = "supabase" | "mock" | "error";

type PropertyResult = {
  properties: Property[];
  source: PropertyDataSource;
};

type GetPropertiesOptions = {
  includeSource?: false;
};

type GetPropertiesWithSourceOptions = {
  includeSource: true;
};

async function resolveProperties(): Promise<PropertyResult> {
  const isDev = process.env.NODE_ENV === "development";

  try {
    // Sprint F: limit reducido a 50 para evitar timeout en unidad de red.
    // TODO: aumentar cuando se mueva a local o se mejore la infraestructura.
    // throwOnError distingue una FALLA real (lanza -> estado de error) de una
    // carga exitosa con 0 resultados (devuelve [] -> empty state normal).
    const supabaseProperties = await getPropertiesFromSupabase({
      limit: 50,
      throwOnError: true,
    });

    // Carga exitosa (incluso con 0 propiedades): fuente real, sin mock.
    return {
      properties: supabaseProperties,
      source: "supabase",
    };
  } catch (error) {
    if (isDev) {
      console.error("[Supabase] error real cargando propiedades; usando mock en dev:", error);
      // Solo en desarrollo: mock para poder trabajar local.
      return {
        properties: mockProperties,
        source: "mock",
      };
    }

    // Producción/beta: NUNCA mostrar datos demo. Estado de error confiable.
    return {
      properties: [],
      source: "error",
    };
  }
}

export async function getProperties(): Promise<Property[]>;
export async function getProperties(
  options: GetPropertiesWithSourceOptions,
): Promise<PropertyResult>;
export async function getProperties(
  options?: GetPropertiesOptions | GetPropertiesWithSourceOptions,
) {
  const result = await resolveProperties();

  if (options?.includeSource) {
    return result;
  }

  return result.properties;
}

export async function getFeaturedProperties(): Promise<Property[]> {
  const properties = await getProperties();
  const featured = properties.filter((property) => property.badges.includes("Destacado"));

  return featured.length > 0 ? featured : properties;
}

export async function getPropertiesByOperation(
  operation: PropertyOperation,
): Promise<Property[]> {
  const properties = await getProperties();

  return properties.filter((property) => property.operation === operation);
}
