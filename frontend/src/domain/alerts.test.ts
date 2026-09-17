import { describe, expect, it } from "vitest";
import type { PropertyFilters } from "@/types/property";
import { savedSearchId, userId } from "./ids";
import {
  ALERT_EVENT_TYPES,
  FILTROS_NO_EVALUABLES,
  type AlertDeliveryPreference,
  type AlertRule,
  type PropiedadParaEmparejar,
  coincideConBusqueda,
  enHorarioSilencioso,
  esEvaluableLocalmente,
  eventosActivos,
  filtrosNoEvaluables,
} from "./alerts";

function prop(o: Partial<PropiedadParaEmparejar> = {}): PropiedadParaEmparejar {
  return {
    operation: "venta",
    propertyType: "departamento",
    province: "Santa Fe",
    city: "Rosario",
    neighborhood: "Centro",
    price: 100_000,
    currency: "USD",
    expenses: null,
    rooms: 3,
    bedrooms: 2,
    bathrooms: 1,
    garages: 0,
    totalArea: 70,
    coveredArea: 65,
    landArea: null,
    age: 10,
    hasImages: true,
    hasCoordinates: true,
    hasVideo: false,
    hasFloorPlan: false,
    mortgageEligible: null,
    ...o,
  };
}

const f = (o: Partial<PropertyFilters>) => o;
const res = (filtros: Partial<PropertyFilters>, p = prop()) => coincideConBusqueda(filtros, p).resultado;

describe("no se finge poder evaluar todo", () => {
  it("la búsqueda de texto necesita al servidor", () => {
    // La base normaliza acentos y parte términos; una aproximación en JS
    // acierta el 90% y ese 10% es imposible de detectar desde afuera.
    const r = coincideConBusqueda(f({ q: "luminoso" }), prop());
    expect(r.resultado).toBe("INDETERMINADO");
    if (r.resultado === "INDETERMINADO") expect(r.filtros).toContain("q");
  });

  it("INDETERMINADO nunca es NO_COINCIDE", () => {
    // Decir "no coincide" cuando no se sabe produce alertas que nunca llegan.
    for (const clave of Object.keys(FILTROS_NO_EVALUABLES)) {
      const valor = clave === "locations" ? ["x"] : clave === "recentDays" ? 7 : "x";
      const r = coincideConBusqueda({ [clave]: valor } as Partial<PropertyFilters>, prop());
      expect(r.resultado).toBe("INDETERMINADO");
    }
  });

  it("cada filtro no evaluable dice por qué", () => {
    for (const motivo of Object.values(FILTROS_NO_EVALUABLES)) {
      expect(motivo.length).toBeGreaterThan(0);
    }
  });

  it("un filtro vacío no cuenta como en uso", () => {
    expect(filtrosNoEvaluables(f({ q: "" }))).toEqual([]);
    expect(filtrosNoEvaluables(f({ locations: [] }))).toEqual([]);
    expect(esEvaluableLocalmente(f({ q: "" }))).toBe(true);
  });

  it("los campos de presentación no afectan el emparejamiento", () => {
    expect(res(f({ sort: "price_asc", page: 3, mode: "map_only" }))).toBe("COINCIDE");
  });
});

describe("emparejamiento básico", () => {
  it("una búsqueda vacía coincide con todo", () => {
    expect(res(f({}))).toBe("COINCIDE");
  });

  it("compara operación y tipo con los valores canónicos del tipo", () => {
    // `PropertyFilters` tipa operación y tipo como uniones en minúscula, así
    // que una variante en mayúsculas no puede llegar acá legítimamente.
    expect(res(f({ operation: "venta", propertyType: "departamento" }))).toBe("COINCIDE");
    expect(res(f({ operation: "alquiler" }))).toBe("NO_COINCIDE");
  });

  it("compara la ubicación ignorando acentos y caja", () => {
    // Ciudad y barrio sí son texto libre y llegan como los escribió la fuente.
    expect(res(f({ city: "rosario", neighborhood: "CENTRO" }))).toBe("COINCIDE");
    expect(coincideConBusqueda(f({ city: "Cordoba" }), prop({ city: "Córdoba" })).resultado).toBe(
      "COINCIDE",
    );
    expect(res(f({ city: "Córdoba" }))).toBe("NO_COINCIDE");
  });

  it("explica por qué no coincide", () => {
    const r = coincideConBusqueda(f({ operation: "alquiler" }), prop());
    if (r.resultado === "NO_COINCIDE") expect(r.motivo).toMatch(/operación/);
    else expect.unreachable("debería no coincidir");
  });
});

describe("precio", () => {
  it("respeta mínimo y máximo", () => {
    expect(res(f({ minPrice: 50_000, maxPrice: 150_000 }))).toBe("COINCIDE");
    expect(res(f({ minPrice: 150_000 }))).toBe("NO_COINCIDE");
    expect(res(f({ maxPrice: 50_000 }))).toBe("NO_COINCIDE");
  });

  it("no compara montos de monedas distintas", () => {
    // Sin el chequeo de moneda, 100.000 ARS pasaría un filtro de 100.000 USD.
    const enPesos = prop({ currency: "ARS", price: 100_000 });
    expect(coincideConBusqueda(f({ currency: "USD", maxPrice: 150_000 }), enPesos).resultado).toBe(
      "NO_COINCIDE",
    );
  });

  it("una propiedad sin precio no entra en un filtro de precio", () => {
    expect(coincideConBusqueda(f({ minPrice: 1 }), prop({ price: null })).resultado).toBe("NO_COINCIDE");
  });

  it("distingue buscar con precio de buscar a consultar", () => {
    expect(coincideConBusqueda(f({ priceMode: "with" }), prop({ price: null })).resultado).toBe(
      "NO_COINCIDE",
    );
    expect(coincideConBusqueda(f({ priceMode: "consult" }), prop({ price: null })).resultado).toBe(
      "COINCIDE",
    );
    expect(res(f({ priceMode: "consult" }))).toBe("NO_COINCIDE");
  });
});

describe("mínimos y máximos", () => {
  it("aplica los mínimos", () => {
    expect(res(f({ minBedrooms: 2, minRooms: 3 }))).toBe("COINCIDE");
    expect(res(f({ minBedrooms: 3 }))).toBe("NO_COINCIDE");
  });

  it("un dato ausente no satisface un mínimo", () => {
    expect(coincideConBusqueda(f({ minGarages: 1 }), prop({ garages: null })).resultado).toBe(
      "NO_COINCIDE",
    );
  });

  it("aplica los máximos", () => {
    expect(res(f({ maxArea: 100, maxAge: 20 }))).toBe("COINCIDE");
    expect(res(f({ maxAge: 5 }))).toBe("NO_COINCIDE");
  });

  it("un máximo de expensas descarta lo que no tiene el dato", () => {
    expect(res(f({ maxExpenses: 50_000 }))).toBe("NO_COINCIDE");
  });
});

describe("banderas", () => {
  it("filtra por fotos, ubicación, video y plano", () => {
    expect(res(f({ hasImages: true, hasLocation: true }))).toBe("COINCIDE");
    expect(res(f({ hasVideo: true }))).toBe("NO_COINCIDE");
    expect(res(f({ hasFloorPlan: true }))).toBe("NO_COINCIDE");
  });

  it("una bandera en false no filtra", () => {
    expect(coincideConBusqueda(f({ hasVideo: false }), prop({ hasVideo: false })).resultado).toBe(
      "COINCIDE",
    );
  });
});

describe("apto crédito: null no es false", () => {
  it("busca los que sí lo son", () => {
    expect(coincideConBusqueda(f({ mortgageState: "si" }), prop({ mortgageEligible: true })).resultado).toBe(
      "COINCIDE",
    );
    // Sin dato NO es apto: no se puede afirmar que lo sea.
    expect(res(f({ mortgageState: "si" }))).toBe("NO_COINCIDE");
  });

  it("busca los que explícitamente no lo son, sin incluir los desconocidos", () => {
    expect(
      coincideConBusqueda(f({ mortgageState: "no" }), prop({ mortgageEligible: false })).resultado,
    ).toBe("COINCIDE");
    expect(res(f({ mortgageState: "no" }))).toBe("NO_COINCIDE");
  });

  it("busca justamente los que no tienen el dato", () => {
    expect(res(f({ mortgageState: "sininfo" }))).toBe("COINCIDE");
    expect(
      coincideConBusqueda(f({ mortgageState: "sininfo" }), prop({ mortgageEligible: true })).resultado,
    ).toBe("NO_COINCIDE");
  });

  it("vacío no filtra", () => {
    expect(res(f({ mortgageState: "" }))).toBe("COINCIDE");
  });
});

describe("reglas de alerta", () => {
  const regla = (o: Partial<AlertRule> = {}): AlertRule => ({
    savedSearchId: savedSearchId("s-1"),
    types: ["NEW_LISTING", "PRICE_CHANGED"],
    frequency: "DAILY",
    enabled: true,
    ...o,
  });

  it("una regla apagada no dispara nada", () => {
    expect(eventosActivos(regla({ enabled: false }))).toEqual([]);
    // Pero se conserva: borrarla perdería la búsqueda.
    expect(regla({ enabled: false }).types).toHaveLength(2);
  });

  it("una encendida dispara sus tipos", () => {
    expect(eventosActivos(regla())).toEqual(["NEW_LISTING", "PRICE_CHANGED"]);
  });

  it("cubre los cuatro tipos de evento pedidos", () => {
    expect(ALERT_EVENT_TYPES).toEqual([
      "NEW_LISTING",
      "PRICE_CHANGED",
      "STATUS_CHANGED",
      "SIMILAR_LISTING",
    ]);
  });
});

describe("horario silencioso", () => {
  const pref = (quietHours: AlertDeliveryPreference["quietHours"]): AlertDeliveryPreference => ({
    userId: userId("u-1"),
    channels: ["EMAIL"],
    quietHours,
  });

  it("sin restricción, nunca silencia", () => {
    expect(enHorarioSilencioso(pref(null), 3)).toBe(false);
  });

  it("respeta un rango dentro del mismo día", () => {
    const p = pref({ from: 13, to: 15 });
    expect(enHorarioSilencioso(p, 14)).toBe(true);
    expect(enHorarioSilencioso(p, 12)).toBe(false);
    expect(enHorarioSilencioso(p, 15)).toBe(false);
  });

  it("respeta un rango que cruza la medianoche", () => {
    // De 22 a 8: no alcanza con comparar mayor y menor.
    const p = pref({ from: 22, to: 8 });
    expect(enHorarioSilencioso(p, 23)).toBe(true);
    expect(enHorarioSilencioso(p, 3)).toBe(true);
    expect(enHorarioSilencioso(p, 12)).toBe(false);
    expect(enHorarioSilencioso(p, 8)).toBe(false);
  });

  it("un rango degenerado no silencia todo el día", () => {
    expect(enHorarioSilencioso(pref({ from: 10, to: 10 }), 10)).toBe(false);
  });
});

describe("determinismo", () => {
  it("la misma búsqueda y propiedad dan el mismo resultado", () => {
    const filtros = f({ minPrice: 50_000, city: "Rosario" });
    expect(coincideConBusqueda(filtros, prop())).toEqual(coincideConBusqueda(filtros, prop()));
  });
});
