import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchAutocomplete } from "@/components/search/SearchAutocomplete";

describe("SearchAutocomplete — puerta universal V2", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

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

  it("selecciona con mouse una sugerencia API v2 y conserva su nivel", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      status: "SUCCESS",
      suggestions: [{
        id: "area:MUNICIPIO:la-calera",
        label: "La Calera",
        category: "municipio",
        query: "La Calera",
        count: 90,
        geography: {
          kind: "area", entityId: null, level: "MUNICIPIO", canonical: null,
          province: null, department: null, municipality: null, locality: null,
        },
      }],
    }), { status: 200 })));
    const { container } = render(<SearchAutocomplete defaultValue="" />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "La Cal" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: /La Calera/ }));
    expect(container.querySelector('input[name="__suggestion_level"][value="MUNICIPIO"]')).toBeInTheDocument();
    expect(container.querySelector('input[name="__suggestion_kind"][value="area"]')).toBeInTheDocument();
  });

  it("diferencia respuesta vacía de error API", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "SUCCESS_EMPTY", suggestions: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "FAILURE", suggestions: [], error: { kind: "NETWORK_ERROR" } }), { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<SearchAutocomplete defaultValue="" />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zz-empty" } });
    expect(await screen.findByText("No encontramos sugerencias. Podés buscar igual.")).toBeInTheDocument();
    unmount();

    render(<SearchAutocomplete defaultValue="" />);
    const second = screen.getByRole("combobox");
    fireEvent.focus(second);
    fireEvent.change(second, { target: { value: "zz-error" } });
    expect(await screen.findByText("No pudimos cargar sugerencias. Podés buscar igual.")).toBeInTheDocument();
  });

  it("no presenta PARTIAL_DATA sin ítems válidos como resultado vacío", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      status: "PARTIAL_DATA",
      suggestions: [],
      issues: [{ path: "$.data[0]", message: "invalid item" }],
    }), { status: 200 })));
    render(<SearchAutocomplete defaultValue="" />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "partial-empty" } });
    expect(await screen.findByText("No pudimos cargar sugerencias. Podés buscar igual.")).toBeInTheDocument();
    expect(screen.queryByText("No encontramos sugerencias. Podés buscar igual.")).toBeNull();
  });
});
