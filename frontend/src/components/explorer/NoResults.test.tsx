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
    expect(screen.getByText("Limpiar filtros")).toBeInTheDocument();
    expect(screen.getByText(/Quitar/)).toBeInTheDocument();
  });

  it("sin filtros no ofrece acciones y muestra el vacío inicial", () => {
    render(<NoResults filters={parsePropertyFilters({})} basePath="/" />);
    expect(screen.queryByText("Ampliar precio")).toBeNull();
    expect(screen.queryByText("Limpiar filtros")).toBeNull();
    expect(screen.getByText(/Todavía no hay propiedades públicas/)).toBeInTheDocument();
  });

  it("ofrece quitar la zona del mapa cuando hay viewport", () => {
    const filters = parsePropertyFilters({ norte: "10", este: "20", sur: "5", oeste: "10", zoom: "12" });
    render(<NoResults filters={filters} basePath="/" />);
    expect(screen.getByText("Quitar zona del mapa")).toBeInTheDocument();
  });

  it("ofrece mostrar sin precio y quitar dormitorios/ambientes cuando aplican", () => {
    const filters = parsePropertyFilters({ precio: "with", dormitorios: "3", ambientes: "4" });
    render(<NoResults filters={filters} basePath="/" />);
    expect(screen.getByText("Mostrar también sin precio")).toBeInTheDocument();
    expect(screen.getByText("Quitar dormitorios")).toBeInTheDocument();
    expect(screen.getByText("Quitar ambientes")).toBeInTheDocument();
  });

  it("ofrece quitar una ubicación con multi-ubicación", () => {
    const filters = parsePropertyFilters({ ubicaciones: "Palermo,Belgrano" });
    render(<NoResults filters={filters} basePath="/" />);
    expect(screen.getByText("Quitar una ubicación")).toBeInTheDocument();
  });
});
