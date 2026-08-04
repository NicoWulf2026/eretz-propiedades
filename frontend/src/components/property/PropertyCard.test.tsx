import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PropertyCard } from "@/components/property/PropertyCard";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";

describe("PropertyCard", () => {
  it("renders complete public fields and an accessible detail link", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/propiedad/123?volver=%2F");
    expect(screen.getByText("USD 180.000")).toBeInTheDocument();
    expect(screen.getByText(/Centro, Córdoba/)).toBeInTheDocument();
    expect(screen.getByText("María")).toBeInTheDocument();
  });

  it("renders dignified missing-data fallbacks", () => {
    const property = mapSupabasePropertyToProperty({
      ...completeRow,
      precio: null,
      moneda: null,
      ciudad: null,
      provincia: null,
      barrio: null,
      imagenes: null,
    });
    render(<PropertyCard property={property} />);
    expect(screen.getByText("Precio a consultar")).toBeInTheDocument();
    expect(screen.getByText("Ubicación no especificada")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Imagen no disponible" })).toBeInTheDocument();
  });
});
