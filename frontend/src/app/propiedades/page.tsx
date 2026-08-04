import type { Metadata } from "next";
import { PropertyExplorerPage } from "@/components/explorer/PropertyExplorerPage";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Buscar propiedades en Argentina",
  description: "Buscá propiedades con mapa, filtros server-side, paginación por cursor y contacto directo.",
  robots: { index: false, follow: false },
};

export default function PropertiesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return <PropertyExplorerPage searchParams={searchParams} basePath="/propiedades" />;
}

