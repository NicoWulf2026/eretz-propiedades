import { describe, expect, it } from "vitest";
import { filterGroupCounts, totalGroupCount } from "@/lib/filter-groups";
import { parsePropertyFilters } from "@/lib/property-query";

const base = () => parsePropertyFilters({});

describe("filterGroupCounts", () => {
  it("sin filtros no cuenta nada", () => {
    expect(filterGroupCounts(base())).toEqual({ ubicacion: 0, precio: 0, caracteristicas: 0, publicacion: 0 });
    expect(totalGroupCount(base())).toBe(0);
  });

  it("cuenta ubicación por campo con valor", () => {
    const f = parsePropertyFilters({ provincia: "Buenos Aires", barrio: "Palermo" });
    expect(filterGroupCounts(f).ubicacion).toBe(2);
  });

  it("multi-ubicación cuenta una vez, no una por zona", () => {
    const f = parsePropertyFilters({ ubicaciones: "Palermo,Belgrano,Núñez" });
    expect(filterGroupCounts(f).ubicacion).toBe(1);
  });

  it("cuenta precio: moneda, mínimo, máximo y modo", () => {
    const f = parsePropertyFilters({ moneda: "USD", precio_min: "100000", precio_max: "200000", precio: "with" });
    expect(filterGroupCounts(f).precio).toBe(4);
  });

  it("cuenta características incluidos los checkboxes", () => {
    const f = parsePropertyFilters({ dormitorios: "2", superficie: "50", imagenes: "1" });
    expect(filterGroupCounts(f).caracteristicas).toBe(3);
  });

  it("cuenta cochera y el estado tri-state de crédito por separado", () => {
    const f = parsePropertyFilters({ cocheras: "1", credito: "no" });
    expect(filterGroupCounts(f).caracteristicas).toBe(2);
  });

  it("el orden por defecto no suma; otro orden sí", () => {
    expect(filterGroupCounts(parsePropertyFilters({ orden: "recent" })).publicacion).toBe(0);
    expect(filterGroupCounts(parsePropertyFilters({ orden: "area_desc" })).publicacion).toBe(1);
  });

  it("un valor vacío no cuenta como filtro activo", () => {
    const f = parsePropertyFilters({ provincia: "", ciudad: "   ", precio_min: "" });
    expect(totalGroupCount(f)).toBe(0);
  });

  it("se restaura desde URL con filtros en varios grupos", () => {
    const f = parsePropertyFilters({ barrio: "Palermo", moneda: "USD", precio_max: "200000", dormitorios: "2" });
    const c = filterGroupCounts(f);
    expect(c).toEqual({ ubicacion: 1, precio: 2, caracteristicas: 1, publicacion: 0 });
    expect(totalGroupCount(f)).toBe(4);
  });

  it("limpiar deja todos los contadores en cero", () => {
    expect(totalGroupCount(parsePropertyFilters({}))).toBe(0);
  });
});
