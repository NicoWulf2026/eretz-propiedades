import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActiveChips, activeChips } from "@/components/explorer/ActiveChips";
import { parsePropertyFilters } from "@/lib/property-query";

describe("ActiveChips", () => {
  it("deriva un chip por filtro aplicado", () => {
    const filters = parsePropertyFilters({ operacion: "venta", ciudad: "Córdoba", precio_min: "100000" });
    const chips = activeChips(filters);
    const keys = chips.map((c) => c.key).sort();
    expect(keys).toEqual(["city", "op", "pmin"]);
  });

  it("al quitar un chip conserva el resto y reinicia el cursor", () => {
    const base = parsePropertyFilters({ operacion: "venta", ciudad: "Córdoba" });
    const filters = { ...base, page: 3, cursor: "abc", direction: "prev" as const };
    const opChip = activeChips(filters).find((c) => c.key === "op")!;
    // se quita 'operation', se conserva 'city', y el cursor vuelve a página 1
    expect(opChip.next.operation).toBe("");
    expect(opChip.next.city).toBe("Córdoba");
    expect(opChip.next.page).toBe(1);
    expect(opChip.next.cursor).toBe("");
    expect(opChip.next.direction).toBe("next");
  });

  it("muestra 'Limpiar todos' con más de un filtro y el chip de viewport", () => {
    const filters = parsePropertyFilters({ operacion: "venta", ciudad: "Córdoba", norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12" });
    const onRemoveViewport = vi.fn();
    render(<ActiveChips filters={filters} basePath="/" onRemoveViewport={onRemoveViewport} />);
    expect(screen.getByText("Limpiar todos")).toBeInTheDocument();
    expect(screen.getByText("Zona del mapa aplicada")).toBeInTheDocument();
  });

  it("no renderiza nada sin filtros ni viewport", () => {
    const { container } = render(<ActiveChips filters={parsePropertyFilters({})} basePath="/" />);
    expect(container.firstChild).toBeNull();
  });
});
