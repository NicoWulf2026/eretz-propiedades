import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { SearchAutocomplete } from "@/components/search/SearchAutocomplete";

describe("SearchAutocomplete — puerta universal V2", () => {
  beforeEach(() => localStorage.clear());

  it("muestra y permite borrar búsquedas recientes individualmente", async () => {
    localStorage.setItem("eretz:recent-searches:v1", JSON.stringify(["Palermo", "Rosario"]));
    render(<SearchAutocomplete defaultValue="" />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    expect(await screen.findByText("Palermo")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("button", { name: "Borrar búsqueda reciente Palermo" }));
    expect(screen.queryByText("Palermo")).toBeNull();
    expect(screen.getByText("Rosario")).toBeInTheDocument();
  });

  it("explica qué interpretó y permite excluir un filtro antes de buscar", () => {
    const { container } = render(<SearchAutocomplete defaultValue="" />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "departamento 2 dormitorios en Palermo" } });
    expect(screen.getByText("Interpretamos")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "No aplicar 2+ dormitorios" }));
    expect(container.querySelector('input[name="__nl_skip"][value="dormitorios"]')).toBeInTheDocument();
  });

  it("separa términos no respaldados sin presentarlos como filtros", () => {
    render(<SearchAutocomplete defaultValue="" />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "departamento en Palermo con balcón" } });
    expect(screen.getByText("No pudimos interpretar")).toBeInTheDocument();
    expect(screen.getByText("balcon")).toBeInTheDocument();
  });
});
