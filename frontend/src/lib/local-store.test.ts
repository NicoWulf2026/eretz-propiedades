import { beforeEach, describe, expect, it } from "vitest";
import {
  STORE_LIMITS,
  addRecentSearch,
  addRecentView,
  clearHidden,
  clearRecentSearches,
  getCompare,
  getFavorites,
  getHidden,
  getRecentSearches,
  getRecentViews,
  hideProperty,
  inCompare,
  isFavorite,
  isHidden,
  removeRecentSearch,
  toggleCompare,
  toggleFavorite,
  unhideProperty,
} from "@/lib/local-store";

beforeEach(() => localStorage.clear());

describe("favoritos", () => {
  it("alterna y persiste", () => {
    expect(isFavorite("1")).toBe(false);
    expect(toggleFavorite("1")).toBe(true);
    expect(isFavorite("1")).toBe(true);
    expect(getFavorites()).toEqual(["1"]);
    expect(toggleFavorite("1")).toBe(false);
    expect(getFavorites()).toEqual([]);
  });
});

describe("ocultas", () => {
  it("oculta, restaura una y todas", () => {
    hideProperty("a");
    hideProperty("b");
    expect(isHidden("a")).toBe(true);
    expect(getHidden()).toEqual(["b", "a"]);
    unhideProperty("a");
    expect(isHidden("a")).toBe(false);
    clearHidden();
    expect(getHidden()).toEqual([]);
  });
  it("no duplica al ocultar dos veces", () => {
    hideProperty("x");
    hideProperty("x");
    expect(getHidden()).toEqual(["x"]);
  });
});

describe("comparar (2..4)", () => {
  it("respeta el tope de 4 y marca lleno", () => {
    expect(STORE_LIMITS.compare).toBe(4);
    expect(toggleCompare("1")).toMatchObject({ active: true, full: false });
    toggleCompare("2");
    toggleCompare("3");
    expect(toggleCompare("4")).toMatchObject({ active: true, full: false });
    const full = toggleCompare("5");
    expect(full).toMatchObject({ active: false, full: true });
    expect(inCompare("5")).toBe(false);
    expect(getCompare()).toHaveLength(4);
  });
  it("quitar libera espacio", () => {
    ["1", "2", "3", "4"].forEach(toggleCompare);
    expect(toggleCompare("2")).toMatchObject({ active: false, full: false });
    expect(getCompare()).not.toContain("2");
    expect(toggleCompare("5")).toMatchObject({ active: true });
  });
});

describe("vistas recientes", () => {
  it("agrega, deduplica moviendo al frente y guarda snapshot", () => {
    addRecentView({ id: "1", title: "Casa", price: "USD 100.000" });
    addRecentView({ id: "2", title: "Depto", price: null });
    addRecentView({ id: "1", title: "Casa", price: "USD 100.000" });
    const recent = getRecentViews();
    expect(recent.map((r) => r.id)).toEqual(["1", "2"]);
    expect(recent[0]).toMatchObject({ id: "1", title: "Casa", price: "USD 100.000" });
    expect(typeof recent[0].at).toBe("number");
  });
  it("acota al límite", () => {
    for (let i = 0; i < STORE_LIMITS.recent + 10; i++) addRecentView({ id: String(i), title: "x", price: null });
    expect(getRecentViews().length).toBe(STORE_LIMITS.recent);
  });
});

describe("búsquedas recientes", () => {
  it("agrega, deduplica por url, elimina y limpia", () => {
    addRecentSearch({ url: "/?operacion=venta", label: "Venta" });
    addRecentSearch({ url: "/?operacion=alquiler", label: "Alquiler" });
    addRecentSearch({ url: "/?operacion=venta", label: "Venta (repetida)" });
    expect(getRecentSearches().map((s) => s.url)).toEqual(["/?operacion=venta", "/?operacion=alquiler"]);
    removeRecentSearch("/?operacion=venta");
    expect(getRecentSearches().map((s) => s.url)).toEqual(["/?operacion=alquiler"]);
    clearRecentSearches();
    expect(getRecentSearches()).toEqual([]);
  });
  it("ignora url vacía", () => {
    addRecentSearch({ url: "   ", label: "x" });
    expect(getRecentSearches()).toEqual([]);
  });
});
