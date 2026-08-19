import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PropertyCard } from "@/components/property/PropertyCard";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";

describe("PropertyCard", () => {
  it("comunica una ubicación aproximada sin afirmar exactitud", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} />);
    expect(screen.getByText("Ubicación aproximada")).toBeInTheDocument();
    expect(screen.queryByText(/ubicación exacta/i)).not.toBeInTheDocument();
  });

  it("variant full muestra las acciones Ver/Compartir/Contactar", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} variant="full" />);
    expect(screen.getByRole("link", { name: "Ver propiedad" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compartir" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contactar" })).toBeInTheDocument();
  });

  it("variant compact no muestra las acciones extra", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} variant="compact" />);
    expect(screen.queryByRole("button", { name: "Compartir" })).toBeNull();
  });

  it("renders complete public fields and an accessible detail link", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/propiedad/123?volver=%2F");
    // El precio se compone de dos spans (moneda en versalita + monto tabular):
    // se verifica el texto resultante, que debe seguir siendo identico.
    expect(document.querySelector(".card-price")?.textContent?.replace(/\s+/g, " ").trim()).toBe("USD 180.000");
    expect(screen.getByText(/Centro, Córdoba/)).toBeInTheDocument();
    expect(screen.getByText("María")).toBeInTheDocument();
  });

  it("una propiedad activa no muestra la indicación de disponibilidad", () => {
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} />);
    expect(screen.queryByText("Disponibilidad no confirmada")).toBeNull();
  });

  it("una propiedad no confirmada muestra la indicación neutral", () => {
    const property = mapSupabasePropertyToProperty({ ...completeRow, estado: "no_detectada_en_ultimo_scraping" });
    render(<PropertyCard property={property} />);
    expect(screen.getByText("Disponibilidad no confirmada")).toBeInTheDocument();
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

  it("separa la previsualización por hover de la selección intencional", () => {
    const onPreview = vi.fn();
    const onCommit = vi.fn();
    render(<PropertyCard property={mapSupabasePropertyToProperty(completeRow)} onPreview={onPreview} onCommit={onCommit} />);
    const card = document.querySelector<HTMLElement>("[data-property-id]");
    if (!card) throw new Error("property card missing");
    fireEvent.pointerEnter(card);
    expect(onPreview).toHaveBeenLastCalledWith("123");
    fireEvent.pointerLeave(card);
    expect(onPreview).toHaveBeenLastCalledWith(null);
    fireEvent.click(screen.getByRole("link"));
    expect(onCommit).toHaveBeenCalledWith("123");
  });
});
