import { describe, expect, it } from "vitest";
import {
  PESOS_SIMILITUD,
  PUNTAJE_MINIMO,
  TOLERANCIA_PRECIO,
  type CandidatoRelacionado,
  explicarSimilitud,
  puntuarSimilitud,
  recomendar,
} from "./recommendations";

function cand(id: string, o: Partial<CandidatoRelacionado> = {}): CandidatoRelacionado {
  return {
    id,
    operation: "venta",
    propertyType: "departamento",
    province: "Santa Fe",
    city: "Rosario",
    neighborhood: "Centro",
    price: 100_000,
    currency: "USD",
    bedrooms: 2,
    rooms: 3,
    totalArea: 70,
    ...o,
  };
}

const BASE = cand("base");
const codigos = (c: CandidatoRelacionado) => puntuarSimilitud(BASE, c).reasons.map((r) => r.code);

describe("ubicación pesa más que todo lo demás", () => {
  it("el mismo barrio puntúa más que la misma ciudad, y ésta más que la provincia", () => {
    const barrio = puntuarSimilitud(BASE, cand("a")).score;
    const ciudad = puntuarSimilitud(BASE, cand("b", { neighborhood: "Fisherton" })).score;
    const provincia = puntuarSimilitud(BASE, cand("c", { neighborhood: "X", city: "Santa Fe" })).score;
    expect(barrio).toBeGreaterThan(ciudad);
    expect(ciudad).toBeGreaterThan(provincia);
  });

  it("otra provincia no aporta ubicación", () => {
    const otra = cand("d", { neighborhood: "X", city: "Córdoba", province: "Córdoba" });
    expect(codigos(otra)).not.toContain("UBICACION");
  });

  it("dos ausencias no son una coincidencia", () => {
    // Sin esto, todas las propiedades sin barrio se considerarían del mismo.
    const sinBarrio = { ...BASE, neighborhood: null };
    const otro = cand("e", { neighborhood: null });
    const r = puntuarSimilitud(sinBarrio, otro);
    expect(r.reasons.find((x) => x.code === "UBICACION")?.label).toBe("la misma ciudad");
  });

  it("ignora acentos y mayúsculas al comparar", () => {
    const otro = cand("f", { neighborhood: "centro", city: "ROSARIO" });
    expect(codigos(otro)).toContain("UBICACION");
  });

  it("es la señal de mayor peso", () => {
    const pesos = Object.values(PESOS_SIMILITUD);
    expect(PESOS_SIMILITUD.ubicacion).toBe(Math.max(...pesos));
  });
});

describe("precio", () => {
  it("puntúa más cuanto más parecido", () => {
    const igual = puntuarSimilitud(BASE, cand("a")).score;
    const cerca = puntuarSimilitud(BASE, cand("b", { price: 110_000 })).score;
    const lejos = puntuarSimilitud(BASE, cand("c", { price: 300_000 })).score;
    expect(igual).toBeGreaterThan(cerca);
    expect(cerca).toBeGreaterThan(lejos);
  });

  it("deja de aportar más allá de la tolerancia", () => {
    const fuera = cand("d", { price: 100_000 * (1 + TOLERANCIA_PRECIO) });
    expect(codigos(fuera)).not.toContain("PRECIO");
  });

  it("no compara precios de monedas distintas", () => {
    expect(codigos(cand("e", { currency: "ARS" }))).not.toContain("PRECIO");
  });

  it("no compara si falta el precio de alguno de los dos", () => {
    expect(codigos(cand("f", { price: null }))).not.toContain("PRECIO");
    expect(puntuarSimilitud({ ...BASE, price: null }, cand("g")).reasons.map((r) => r.code)).not.toContain(
      "PRECIO",
    );
  });
});

describe("dormitorios y superficie", () => {
  it("la coincidencia exacta de dormitorios puntúa más que una diferencia de uno", () => {
    const exacto = puntuarSimilitud(BASE, cand("a")).score;
    const uno = puntuarSimilitud(BASE, cand("b", { bedrooms: 3 })).score;
    expect(exacto).toBeGreaterThan(uno);
  });

  it("una diferencia de dos o más no aporta", () => {
    expect(codigos(cand("c", { bedrooms: 5 }))).not.toContain("DORMITORIOS");
  });

  it("la superficie parecida aporta", () => {
    expect(codigos(cand("d", { totalArea: 75 }))).toContain("SUPERFICIE");
    expect(codigos(cand("e", { totalArea: 300 }))).not.toContain("SUPERFICIE");
  });
});

describe("explicabilidad", () => {
  it("toda coincidencia deja una razón legible", () => {
    const r = puntuarSimilitud(BASE, cand("a"));
    expect(r.reasons.length).toBeGreaterThan(0);
    for (const razon of r.reasons) {
      expect(razon.label.length).toBeGreaterThan(0);
      expect(razon.code.length).toBeGreaterThan(0);
      expect(razon.weight).toBeGreaterThan(0);
    }
  });

  it("ordena las razones por cuánto aportaron", () => {
    const r = puntuarSimilitud(BASE, cand("a"));
    const pesos = r.reasons.map((x) => x.weight);
    expect([...pesos].sort((a, b) => b - a)).toEqual(pesos);
  });

  it("arma el texto de 'Similar porque…'", () => {
    const r = puntuarSimilitud(BASE, cand("a"));
    expect(explicarSimilitud(r)).toContain("el mismo barrio");
    expect(explicarSimilitud(r).split("·")).toHaveLength(2);
  });

  it("sin coincidencias no inventa una explicación", () => {
    const nada = cand("z", {
      neighborhood: "X", city: "Y", province: "Z",
      price: null, bedrooms: null, totalArea: null, propertyType: "campo",
    });
    const r = puntuarSimilitud(BASE, nada);
    expect(r.score).toBe(0);
    expect(explicarSimilitud(r)).toBe("");
  });
});

describe("neutralidad del ranking", () => {
  it("el tipo de entrada no tiene ningún campo comercial", () => {
    // La forma de que nadie agregue un boost pago por accidente es que no haya
    // dónde ponerlo.
    const claves = Object.keys(cand("a"));
    for (const prohibida of ["paidBoost", "sponsoredWeight", "commercialPriority", "featured", "promoted"]) {
      expect(claves).not.toContain(prohibida);
    }
  });

  it("dos propiedades idénticas puntúan igual", () => {
    const a = puntuarSimilitud(BASE, cand("a"));
    const b = puntuarSimilitud(BASE, cand("b"));
    expect(a.score).toBe(b.score);
  });

  it("no hay personalización por comportamiento: la firma no recibe usuario", () => {
    // Hacerlo con el historial local convertiría descubrimiento en seguimiento.
    expect(puntuarSimilitud.length).toBe(2);
  });
});

describe("selección", () => {
  it("nunca incluye la propia propiedad", () => {
    const r = recomendar(BASE, [cand("base"), cand("a")]);
    expect(r.map((x) => x.id)).toEqual(["a"]);
  });

  it("ordena de más a menos parecido", () => {
    const r = recomendar(BASE, [
      cand("lejos", { neighborhood: "X", city: "Santa Fe", price: 250_000 }),
      cand("cerca"),
      cand("medio", { neighborhood: "Fisherton" }),
    ]);
    expect(r.map((x) => x.id)).toEqual(["cerca", "medio", "lejos"]);
  });

  it("respeta el límite", () => {
    const muchos = Array.from({ length: 20 }, (_, i) => cand(`c${i}`));
    expect(recomendar(BASE, muchos)).toHaveLength(4);
    expect(recomendar(BASE, muchos, { limite: 2 })).toHaveLength(2);
  });

  it("con el umbral puesto prefiere devolver menos", () => {
    // Mostrar cuatro cosas sin relación es peor que mostrar una que sí la tiene.
    const irrelevantes = Array.from({ length: 5 }, (_, i) =>
      cand(`x${i}`, {
        neighborhood: "X", city: "Y", province: "Z",
        price: null, bedrooms: null, totalArea: null, propertyType: "campo",
      }),
    );
    expect(recomendar(BASE, irrelevantes)).toEqual([]);
    expect(PUNTAJE_MINIMO).toBeGreaterThan(0);
  });

  it("con minimo 0 conserva la cantidad, que es lo que usa la ficha", () => {
    const irrelevantes = Array.from({ length: 5 }, (_, i) =>
      cand(`x${i}`, {
        neighborhood: "X", city: "Y", province: "Z",
        price: null, bedrooms: null, totalArea: null, propertyType: "campo",
      }),
    );
    expect(recomendar(BASE, irrelevantes, { minimo: 0 })).toHaveLength(4);
  });

  it("el orden es estable entre cargas", () => {
    // Una lista que cambia de orden sola confunde a quien vuelve.
    const empatados = [cand("b"), cand("a"), cand("c")];
    expect(recomendar(BASE, empatados).map((x) => x.id)).toEqual(["a", "b", "c"]);
    expect(recomendar(BASE, [...empatados].reverse()).map((x) => x.id)).toEqual(["a", "b", "c"]);
  });

  it("es determinista", () => {
    const c = [cand("a"), cand("b", { price: 120_000 })];
    expect(recomendar(BASE, c)).toEqual(recomendar(BASE, c));
  });
});
