import { render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NaturalLanguageSearch } from "@/components/search/NaturalLanguageSearch";

// Integración: texto NL → filtros estructurados en la URL, preservando ?nl=.
describe("NaturalLanguageSearch (integración)", () => {
  afterEach(() => vi.restoreAllMocks());

  function submitWith(text: string): URL {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign, search: "", href: "https://x.test/propiedades" },
    });
    const { unmount } = render(<NaturalLanguageSearch basePath="/propiedades" />);
    fireEvent.change(screen.getByLabelText(/Escribí lo que buscás/i), { target: { value: text } });
    fireEvent.submit(screen.getByRole("search"));
    expect(assign).toHaveBeenCalledOnce();
    const url = new URL(assign.mock.calls[0][0] as string, "https://x.test");
    unmount();
    return url;
  }

  it("traduce a filtros estructurados y conserva el texto original en nl=", () => {
    const url = submitWith("depto 2 ambientes en Palermo o Belgrano hasta 200 mil dolares");
    expect(url.pathname).toBe("/propiedades");
    expect(url.searchParams.get("tipo")).toBe("departamento");
    expect(url.searchParams.get("ambientes")).toBe("2");
    expect(url.searchParams.get("ubicaciones")).toBe("Palermo,Belgrano");
    expect(url.searchParams.get("moneda")).toBe("USD");
    expect(url.searchParams.get("precio_max")).toBe("200000");
    expect(url.searchParams.get("nl")).toBe("depto 2 ambientes en Palermo o Belgrano hasta 200 mil dolares");
    // no inventa operación
    expect(url.searchParams.get("operacion")).toBeNull();
  });

  it("'comprar' sí se traduce a venta; sin él no se asume", () => {
    expect(submitWith("casa en Rosario para comprar").searchParams.get("operacion")).toBe("venta");
    expect(submitWith("casa en Rosario").searchParams.get("operacion")).toBeNull();
  });

  it("muestra lo NO interpretado sin convertirlo en filtro", () => {
    const url = submitWith("departamento en Palermo con balcón y pileta");
    // amenities no aparecen como filtro
    expect([...url.searchParams.keys()]).not.toContain("cochera");
    expect(url.searchParams.get("tipo")).toBe("departamento");
  });
});
