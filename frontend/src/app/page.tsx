import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SiteShell } from "@/components/layout/SiteShell";
import { HomeHero } from "@/components/home/HomeHero";
import {
  AboutSection, AgencyStrip, FeatureGrid, PlaceChips, PlaceGrid, PropertyCarousel,
} from "@/components/home/HomeSections";
import { getHomeAgencies, getHomeCarousels, getHomeCities, getHomeNeighbourhoods } from "@/lib/home-data";
import { getHomeInventory } from "@/lib/property-service";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Propiedades en Argentina",
  description: "Buscá propiedades de inmobiliarias de toda la Argentina en un solo lugar: mapa, filtros y contacto directo con quien publicó el aviso.",
  robots: { index: false, follow: false },
};

const OPERATIONS = [
  { value: "venta", label: "Comprar" },
  { value: "alquiler", label: "Alquilar" },
];

const TOOLS = [
  { icon: "◎", name: "Búsqueda en lenguaje natural", href: "/propiedades",
    text: "Escribí lo que buscás como se lo dirías a una persona y ERETZ lo traduce a filtros reales." },
  { icon: "▣", name: "Colecciones", href: "/colecciones",
    text: "Agrupá propiedades en listas propias que quedan guardadas en este dispositivo." },
  { icon: "⇄", name: "Comparador", href: "/comparar",
    text: "Poné hasta cuatro propiedades lado a lado y mirá precio, superficie y características juntas." },
];

const MAP_TOOLS = [
  { icon: "◧", name: "Mapa con zonas", href: "/propiedades?modo=map_only",
    text: "Dibujá un rectángulo, un polígono o un radio y buscá sólo dentro de esa zona." },
  { icon: "★", name: "Favoritos y visitadas", href: "/favoritos",
    text: "Guardá lo que te interesa y ocultá lo que ya viste, sin necesidad de crear una cuenta." },
  { icon: "⌂", name: "Directorio de inmobiliarias", href: "/inmobiliarias",
    text: "Mirá todas las inmobiliarias del catálogo y sus publicaciones." },
];

export default async function Home({ searchParams }: { searchParams: Promise<SearchParams> }) {
  // Compatibilidad: "/" servía el explorador, así que cualquier deep-link con
  // parámetros de búsqueda sigue funcionando y se redirige a su ruta canónica.
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (Array.isArray(value)) value.forEach((v) => query.append(key, v));
    else if (typeof value === "string" && value) query.set(key, value);
  }
  if ([...query.keys()].length > 0) redirect(`/propiedades?${query.toString()}`);

  const [inventory, cities, neighbourhoods, agencies] = await Promise.all([
    getHomeInventory(), getHomeCities(), getHomeNeighbourhoods(), getHomeAgencies(),
  ]);
  const carousels = await getHomeCarousels(cities);

  return (
    <SiteShell>
      <HomeHero operations={OPERATIONS} />

      <FeatureGrid
        title="Tu búsqueda, con más contexto"
        subtitle="Las funciones que ERETZ suma sobre un listado común."
        items={TOOLS}
      />

      <PlaceGrid blocks={cities.slice(0, 8)} title="Explorá por ciudad" id="ciudades" />
      <PlaceChips blocks={cities} label="Ciudades" />

      {carousels.map((c) => <PropertyCarousel key={c.title} data={c} />)}

      <AgencyStrip agencies={agencies} />

      <FeatureGrid
        title="Herramientas"
        subtitle="Todo funciona sin cuenta y sin guardar nada en un servidor."
        items={MAP_TOOLS}
      />

      <PlaceGrid blocks={neighbourhoods.slice(0, 8)} title="Explorá por barrio" id="barrios" />
      <PlaceChips blocks={neighbourhoods} label="Barrios" />

      <AboutSection total={inventory.count} />
    </SiteShell>
  );
}
