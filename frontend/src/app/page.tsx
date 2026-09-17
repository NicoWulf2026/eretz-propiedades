import type { Metadata } from "next";
import { PropertyExplorerPage } from "@/components/explorer/PropertyExplorerPage";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Propiedades en Argentina",
  description: "Buscá propiedades de inmobiliarias de toda la Argentina en un solo lugar: mapa, filtros y contacto directo con quien publicó el aviso.",
  robots: { index: false, follow: false },
};

export default function Home({ searchParams }: { searchParams: Promise<SearchParams> }) {
  // V2 convierte la entrada en el producto real: los mismos filtros, mapa,
  // resultados y contratos de URL del explorador, sin una landing intermedia.
  return <PropertyExplorerPage searchParams={searchParams} basePath="/" />;
}
