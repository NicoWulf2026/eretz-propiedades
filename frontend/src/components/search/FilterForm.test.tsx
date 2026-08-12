import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FilterForm } from "@/components/search/FilterForm";
import { parsePropertyFilters } from "@/lib/property-query";

// Fase A: los filtros visibles deben estar respaldados por datos reales del
// catálogo público (193.615). Los campos ~100% NULL se ocultan para no producir
// resultados engañosos (cero). NULL nunca equivale a "No".
describe("FilterForm — filtros alineados con datos públicos reales", () => {
  const filters = parsePropertyFilters({});

  it("ofrece operación Consultar y tipo Otro (valores reales del catálogo)", () => {
    render(<FilterForm filters={filters} />);
    expect(screen.getByRole("option", { name: "Consultar" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Otro" })).toBeInTheDocument();
  });

  it("conserva los filtros con respaldo de datos", () => {
    const { container } = render(<FilterForm filters={filters} />);
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.getByText("Superficie total mín.")).toBeInTheDocument();
    expect(screen.getByText("Con imágenes")).toBeInTheDocument();
    expect(screen.getByText("Con ubicación en mapa")).toBeInTheDocument();
    expect(screen.getByText("Baños mín.")).toBeInTheDocument();
  });

  it("oculta los filtros sin respaldo de datos (columnas ~100% nulas)", () => {
    const { container } = render(<FilterForm filters={filters} />);
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.queryByText(/Cocheras/)).toBeNull();
    expect(screen.queryByText(/Superficie cubierta/)).toBeNull();
    expect(screen.queryByText("Terreno mín.")).toBeNull();
    expect(screen.queryByText(/Expensas/)).toBeNull();
    expect(screen.queryByText(/Antigüedad/)).toBeNull();
    expect(screen.queryByText(/Con video/)).toBeNull();
    expect(screen.queryByText(/Con plano/)).toBeNull();
    expect(screen.queryByText(/Apto crédito/)).toBeNull();
  });
});
