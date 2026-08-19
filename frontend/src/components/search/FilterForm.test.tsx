import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildFilterSearchParams, FilterForm } from "@/components/search/FilterForm";
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

  it("oculta los filtros que siguen sin respaldo suficiente", () => {
    const { container } = render(<FilterForm filters={filters} />);
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.queryByText(/Superficie cubierta/)).toBeNull();
    expect(screen.queryByText("Terreno mín.")).toBeNull();
    expect(screen.queryByText(/Expensas/)).toBeNull();
    expect(screen.queryByText(/Antigüedad/)).toBeNull();
    expect(screen.queryByText(/Con video/)).toBeNull();
    expect(screen.queryByText(/Con plano/)).toBeNull();
  });

  it("expone cochera y apto crédito porque el catálogo actual ya tiene datos, con tri-state explícito", () => {
    const { container } = render(<FilterForm filters={filters} />);
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.getByText("Cocheras mín.")).toBeInTheDocument();
    const credit = screen.getByLabelText("Apto crédito");
    expect(credit).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sin filtrar" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sin información" })).toBeInTheDocument();
  });

  it("unifica una frase natural en filtros verificables y conserva nl=", () => {
    const form = new FormData();
    form.set("q", "departamento 2 dormitorios en Palermo hasta 200 mil dólares");
    const params = buildFilterSearchParams(form);
    expect(params.get("q")).toBeNull();
    expect(params.get("tipo")).toBe("departamento");
    expect(params.get("dormitorios")).toBe("2");
    expect(params.get("ubicaciones")).toBe("Palermo");
    expect(params.get("moneda")).toBe("USD");
    expect(params.get("precio_max")).toBe("200000");
    expect(params.get("nl")).toContain("departamento");
  });

  it("permite descartar una interpretación y prioriza la selección manual", () => {
    const form = new FormData();
    form.set("q", "departamento 2 dormitorios en Palermo");
    form.set("tipo", "casa");
    form.append("__nl_skip", "dormitorios");
    const params = buildFilterSearchParams(form);
    expect(params.get("tipo")).toBe("casa");
    expect(params.get("dormitorios")).toBeNull();
    expect(params.get("ubicaciones")).toBe("Palermo");
  });

  it("convierte una sugerencia geográfica elegida en un parámetro estructurado", () => {
    const form = new FormData();
    form.set("q", "Palermo");
    form.set("__suggestion_category", "barrio");
    form.set("__suggestion_value", "Palermo");
    const params = buildFilterSearchParams(form);
    expect(params.get("q")).toBeNull();
    expect(params.get("barrio")).toBe("Palermo");
  });

  it("una búsqueda rápida conserva filtros avanzados y viewport ya aplicados", () => {
    const filtersWithState = parsePropertyFilters({
      ciudad: "Rosario", moneda: "USD", precio_max: "180000",
      norte: "-32.8", este: "-60.5", sur: "-33.1", oeste: "-60.9", zoom: "12",
    });
    const { container } = render(<FilterForm filters={filtersWithState} action="/propiedades" />);
    const form = container.querySelector("form") as HTMLFormElement;
    const params = buildFilterSearchParams(new FormData(form));
    expect(params.get("ciudad")).toBe("Rosario");
    expect(params.get("moneda")).toBe("USD");
    expect(params.get("precio_max")).toBe("180000");
    expect(params.get("zoom")).toBe("12");
  });
});
