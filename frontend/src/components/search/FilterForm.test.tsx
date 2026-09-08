import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildFilterSearchParams, FilterForm } from "@/components/search/FilterForm";
import { parsePropertyFilters } from "@/lib/property-query";
import { adaptApiV2Filters } from "@/lib/api-v2/adapters";
import { apiV2FiltersFixture } from "@/test/api-v2-fixtures";

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

  it("muestra cantidades reales de API v2 sin cambiar los valores enviados", () => {
    const metadata = { status: "SUCCESS" as const, metadata: adaptApiV2Filters(apiV2FiltersFixture) };
    const { container } = render(<FilterForm filters={filters} filterMetadata={metadata} />);
    expect(screen.getByRole("option", { name: "Comprar (42.536)" })).toHaveValue("venta");
    expect(screen.getByRole("option", { name: "Temporario (303)" })).toHaveValue("temporario");
    expect(screen.getByRole("option", { name: "Departamento (20.700)" })).toHaveValue("departamento");
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.getByRole("option", { name: "USD (46.361)" })).toHaveValue("USD");
  });

  it("distingue metadata no disponible sin ocultar controles legacy", () => {
    const unavailable = { status: "FAILURE" as const, metadata: null, error: { kind: "NETWORK_ERROR" as const } };
    const { container } = render(<FilterForm filters={filters} filterMetadata={unavailable} />);
    expect(screen.getByRole("option", { name: "Comprar" })).toHaveValue("venta");
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos actualizar las cantidades del catálogo");
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

  it("preserva el nivel de un municipio sin convertirlo en ciudad", () => {
    const form = new FormData();
    form.set("ciudad", "Rosario");
    form.set("barrio", "Centro");
    form.set("q", "La Calera");
    form.set("__suggestion_category", "municipio");
    form.set("__suggestion_value", "La Calera");
    form.set("__suggestion_kind", "area");
    form.set("__suggestion_level", "MUNICIPIO");
    const params = buildFilterSearchParams(form);
    expect(params.get("q")).toBeNull();
    expect(params.get("ciudad")).toBeNull();
    expect(params.get("ubicaciones")).toBe("La Calera");
    expect(params.get("area_nivel")).toBe("MUNICIPIO");
    expect(params.get("area_nombre")).toBe("La Calera");
    expect(params.get("barrio")).toBeNull();
  });

  it("preserva que un barrio de API v2 no es canónico", () => {
    const form = new FormData();
    form.set("provincia", "Córdoba");
    form.set("area_nivel", "PROVINCIA");
    form.set("q", "Palermo");
    form.set("__suggestion_category", "barrio");
    form.set("__suggestion_value", "Palermo");
    form.set("__suggestion_kind", "neighborhood");
    form.set("__suggestion_canonical", "0");
    const params = buildFilterSearchParams(form);
    expect(params.get("barrio")).toBe("Palermo");
    expect(params.get("barrio_canonico")).toBe("0");
    expect(params.get("provincia")).toBeNull();
    expect(params.get("area_nivel")).toBeNull();
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
