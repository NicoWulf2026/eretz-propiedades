import { SiteShell } from "@/components/layout/SiteShell";
import { ExplorerClient } from "@/components/explorer/ExplorerClient";
import { parsePropertyFilters, type SearchParams } from "@/lib/property-query";

export async function PropertyExplorerPage({ searchParams, basePath }: { searchParams: Promise<SearchParams>; basePath: string }) {
  const filters = parsePropertyFilters(await searchParams);
  return <SiteShell><ExplorerClient filters={filters} basePath={basePath} /></SiteShell>;
}
