import type { Metadata } from "next";
import { PropertyExplorerPage } from "@/components/explorer/PropertyExplorerPage";
import type { SearchParams } from "@/lib/property-query";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Explorar propiedades en Argentina",
  description: "Explorá propiedades de toda Argentina en el mapa, filtrá el inventario permitido y contactá directamente al publicador.",
  robots: { index: false, follow: false },
};

export default function Home({ searchParams }: { searchParams: Promise<SearchParams> }) {
  return <PropertyExplorerPage searchParams={searchParams} basePath="/" />;
}

