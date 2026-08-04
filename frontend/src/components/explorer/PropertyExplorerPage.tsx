import { SiteShell } from "@/components/layout/SiteShell";
import { ExplorerClient } from "@/components/explorer/ExplorerClient";
import { parsePropertyFilters, type SearchParams } from "@/lib/property-query";
import { searchProperties } from "@/lib/property-service";

export async function PropertyExplorerPage({ searchParams, basePath }: { searchParams: Promise<SearchParams>; basePath: string }) {
  const filters = parsePropertyFilters(await searchParams);
  const result = await searchProperties(filters);
  return <SiteShell><ExplorerClient filters={filters} result={result} basePath={basePath} /></SiteShell>;
}

