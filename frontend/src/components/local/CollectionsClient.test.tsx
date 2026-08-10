import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CollectionsClient } from "@/components/local/CollectionsClient";
import { getCollections } from "@/lib/local-store";

// Evita fetch real del hook de propiedades por ids.
vi.mock("@/components/local/use-properties-by-ids", () => ({
  usePropertiesByIds: () => ({ properties: [], loading: false, error: false }),
}));

beforeEach(() => localStorage.clear());

describe("CollectionsClient (interacción)", () => {
  it("crea, renombra y elimina una colección desde la UI", () => {
    render(<CollectionsClient />);
    // crear
    fireEvent.change(screen.getByLabelText(/nueva colección/i), { target: { value: "Para visitar" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(getCollections().map((c) => c.name)).toContain("Para visitar");
    expect(screen.getByRole("button", { name: /Para visitar/ })).toBeInTheDocument();

    // renombrar
    fireEvent.click(screen.getByRole("button", { name: "Renombrar" }));
    const input = screen.getByDisplayValue("Para visitar");
    fireEvent.change(input, { target: { value: "Finalistas" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(getCollections()[0].name).toBe("Finalistas");

    // eliminar
    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    expect(getCollections()).toEqual([]);
  });

  it("no crea colección con nombre vacío", () => {
    render(<CollectionsClient />);
    fireEvent.click(screen.getByRole("button", { name: "Crear" }));
    expect(getCollections()).toEqual([]);
  });
});
