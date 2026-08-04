import Link from "next/link";
import { filtersToSearchParams } from "@/lib/property-query";
import type { PropertyFilters } from "@/types/property";

type PaginationProps = {
  filters: PropertyFilters;
  hasNext: boolean;
  hasPrevious: boolean;
  nextCursor: string | null;
  previousCursor: string | null;
  basePath?: string;
};

export function Pagination({ filters, hasNext, hasPrevious, nextCursor, previousCursor, basePath = "/" }: PaginationProps) {
  if (!hasNext && !hasPrevious) return null;
  const href = (page: number, cursor: string, direction: "next" | "prev") => {
    const params = filtersToSearchParams({ ...filters, page, cursor, direction });
    return `${basePath}?${params.toString()}`;
  };
  return (
    <nav aria-label="Paginación" className="mt-10 flex items-center justify-between gap-4">
      {hasPrevious && previousCursor ? <Link className="secondary-button" href={href(Math.max(1, filters.page - 1), previousCursor, "prev")}>← Anterior</Link> : <span />}
      <p className="text-sm font-semibold text-slate-600">Página {filters.page.toLocaleString("es-AR")}</p>
      {hasNext && nextCursor ? <Link className="secondary-button" href={href(filters.page + 1, nextCursor, "next")}>Siguiente →</Link> : <span />}
    </nav>
  );
}
