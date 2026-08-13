import { getRealEstateDirectory, searchProperties } from "@/lib/property-service";
import { parsePropertyFilters } from "@/lib/property-query";
import type { PropertySummary } from "@/types/property";

// Datos del home. Todo sale de consultas reales al inventario permitido: no hay
// cifras hardcodeadas ni bloques de relleno. Si una ciudad no tiene inventario
// suficiente, su bloque simplemente no se renderiza.

// Sin portada: la referencia usa imagen curada por ciudad y ERETZ no tiene ese
// dataset. Usar la foto de un aviso cualquiera terminaba mostrando el logo de
// una inmobiliaria como si fuera la ciudad -el clasificador por URL no lo
// detecta cuando el logo esta alojado con nombre generico-, y no corresponde
// inventar imagenes. El bloque se resuelve con el dato real: nombre y conteo.
export type CityBlock = { name: string; count: number };
export type Carousel = { title: string; href: string; properties: PropertySummary[] };

// Ciudades y barrios de arranque. Son términos de búsqueda, no datos: el conteo
// y las fotos vienen de la base. Los que devuelvan 0 se descartan.
const CITY_SEEDS = [
  "Capital Federal", "Córdoba", "Rosario", "La Plata",
  "Mar del Plata", "Mendoza", "Salta", "Neuquén",
];
const NEIGHBOURHOOD_SEEDS = [
  "Palermo", "Belgrano", "Recoleta", "Caballito", "Villa Urquiza",
  "Núñez", "Almagro", "Villa Crespo", "Nueva Córdoba", "San Telmo",
  "Puerto Madero", "Colegiales",
];

async function cityBlock(name: string): Promise<CityBlock> {
  const result = await searchProperties(parsePropertyFilters({ ubicaciones: name }));
  return { name, count: result.count ?? 0 };
}

export async function getHomeCities(): Promise<CityBlock[]> {
  const blocks = await Promise.all(CITY_SEEDS.map(cityBlock));
  return blocks.filter((b) => b.count > 0).sort((a, b) => b.count - a.count);
}

export async function getHomeNeighbourhoods(): Promise<CityBlock[]> {
  const blocks = await Promise.all(NEIGHBOURHOOD_SEEDS.map(cityBlock));
  return blocks.filter((b) => b.count > 0).sort((a, b) => b.count - a.count);
}

async function carousel(title: string, location: string, extra: Record<string, string> = {}): Promise<Carousel> {
  const params = { ubicaciones: location, imagenes: "si", orden: "reciente", ...extra };
  const result = await searchProperties(parsePropertyFilters(params));
  const query = new URLSearchParams(params).toString();
  return { title, href: `/propiedades?${query}`, properties: result.properties.slice(0, 12) };
}

export async function getHomeCarousels(cities: CityBlock[]): Promise<Carousel[]> {
  const top = cities.slice(0, 3);
  const lists = await Promise.all([
    ...top.map((c) => carousel(`Lo último en ${c.name}`, c.name)),
    carousel("En venta con crédito", "Argentina", { operacion: "venta", credito: "si" }),
  ]);
  return lists.filter((l) => l.properties.length >= 4);
}

export async function getHomeAgencies(limit = 8) {
  const directory = await getRealEstateDirectory("");
  return directory.items.slice(0, limit);
}
