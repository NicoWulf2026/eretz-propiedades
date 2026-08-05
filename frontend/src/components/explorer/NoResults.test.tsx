import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NoResults } from "@/components/explorer/NoResults";
import { parsePropertyFilters } from "@/lib/property-query";

// Fase H: las acciones de "sin resultados" sólo aparecen cuando aplican.
describe("NoResults", () => {
  it("muestra acciones contextuales según los filtros aplicados", () => {
    const filters = parsePropertyFilters({ ciudad: "Córdoba", precio_min: "100000" });
    render(<NoResults filters={filters} basePath="/" />);
    expect(screen.getByText("Ampliar precio")).toBeInTheDocument();
    expect(screen.getByText("Ampliar ubicación")).toBeInTheDocument();
    expect(screen.getByText("Limpiar todos")).toBeInTheDocument();
    expect(screen.getByText(/Quitar/)).toBeInTheDocument();
  });

  it("sin filtros no ofrece acciones y muestra el vacío inicial", () => {
    render(<NoResults filters={parsePropertyFilters({})} basePath="/" />);
    expect(screen.queryByText("Ampliar precio")).toBeNull();
    expect(screen.queryByText("Limpiar todos")).toBeNull();
    expect(screen.getByText(/Todavía no hay propiedades públicas/)).toBeInTheDocument();
  });

  it("ofrece quitar la zona del mapa cuando hay viewport", () => {
    const filters = parsePropertyFilters({ norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12" });
    render(<NoResults filters={filters} basePath="/" />);
    expect(screen.getByText("Quitar filtro del mapa")).toBeInTheDocument();
  });
});
