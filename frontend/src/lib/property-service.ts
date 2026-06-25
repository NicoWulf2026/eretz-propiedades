import { mockProperties } from "@/lib/property-data";
import { getPropertiesFromSupabase } from "@/lib/property-supabase-service";
import type { Property, PropertyOperation } from "@/types/property";

export type PropertyDataSource = "supabase" | "mock";

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
  try {
    // Sprint F: limit reducido a 50 para evitar timeout en unidad de red.
    // Con limit=300 → 600 IDs → 6 chunks paralelos → ~19s (excede timeout de 12s anterior).
    // Con limit=50 → 150 IDs → 2 chunks → ~10s (dentro del nuevo timeout de 25s).
    // TODO: aumentar cuando se mueva a local o se mejore la infraestructura.
    const supabaseProperties = await getPropertiesFromSupabase({ limit: 50 });

    if (supabaseProperties.length > 0) {
      return {
        properties: supabaseProperties,
        source: "supabase",
      };
    }
  } catch (error) {
    if (process.env.NODE_ENV === "development") {
      console.error("[Supabase] Falling back to mock properties after error:", error);
    }
  }

  return {
    properties: mockProperties,
    source: "mock",
  };
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
