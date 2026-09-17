import { describe, expect, it } from "vitest";
import {
  type ElementoFechado,
  type EstadoSync,
  fusionarConjunto,
  fusionarFechados,
  planVacio,
  puedeLimpiarLocal,
} from "./sync";

describe("fusión de conjuntos sin fechas", () => {
  it("conserva lo que está de los dos lados", () => {
    const p = fusionarConjunto({ ids: ["a", "b"] }, { ids: ["a", "b"] });
    expect(p.resultado).toEqual(["a", "b"]);
    expect(planVacio(p)).toBe(true);
  });

  it("sube lo que sólo está local", () => {
    const p = fusionarConjunto({ ids: ["a", "b"] }, { ids: ["a"] });
    expect(p.subir).toEqual(["b"]);
    expect(p.bajar).toEqual([]);
    expect(p.resultado).toEqual(["a", "b"]);
  });

  it("baja lo que sólo está en la nube", () => {
    const p = fusionarConjunto({ ids: ["a"] }, { ids: ["a", "c"] });
    expect(p.bajar).toEqual(["c"]);
    expect(p.resultado).toEqual(["a", "c"]);
  });

  it("no pierde nada de ninguno de los dos lados", () => {
    // La propiedad que más importa de toda la fusión.
    const p = fusionarConjunto({ ids: ["a", "b"] }, { ids: ["c", "d"] });
    expect(p.resultado).toEqual(["a", "b", "c", "d"]);
  });

  it("registra como resurrección lo que baja sin poder descartar un borrado", () => {
    // Sin lápidas es indecidible si "no está local" es "nunca lo tuve" o "lo
    // borré". Se conserva, pero queda anotado para que el costo sea medible.
    const p = fusionarConjunto({ ids: ["a"] }, { ids: ["a", "c"] });
    expect(p.resurrecciones).toEqual(["c"]);
  });

  it("no marca resurrección cuando el dispositivo sí lleva lápidas", () => {
    const p = fusionarConjunto({ ids: ["a"], tombstones: [] }, { ids: ["a", "c"] });
    expect(p.bajar).toEqual(["c"]);
    expect(p.resurrecciones).toEqual([]);
  });

  it("es idempotente: fusionar el resultado no cambia nada", () => {
    const primera = fusionarConjunto({ ids: ["a", "b"] }, { ids: ["b", "c"] });
    const segunda = fusionarConjunto({ ids: primera.resultado }, { ids: primera.resultado });
    expect(segunda.resultado).toEqual(primera.resultado);
    expect(planVacio(segunda)).toBe(true);
  });

  it("es determinista y ordena estable", () => {
    const a = fusionarConjunto({ ids: ["c", "a"] }, { ids: ["b"] });
    const b = fusionarConjunto({ ids: ["a", "c"] }, { ids: ["b"] });
    expect(a).toEqual(b);
    expect(a.resultado).toEqual(["a", "b", "c"]);
  });

  it("tolera duplicados en la entrada", () => {
    const p = fusionarConjunto({ ids: ["a", "a", "b"] }, { ids: ["b", "b"] });
    expect(p.resultado).toEqual(["a", "b"]);
  });

  it("dos lados vacíos dan un plan vacío", () => {
    expect(planVacio(fusionarConjunto({ ids: [] }, { ids: [] }))).toBe(true);
  });
});

describe("borrados con lápida", () => {
  it("propaga a la nube un borrado hecho localmente", () => {
    const p = fusionarConjunto(
      { ids: [], tombstones: [{ id: "a", deletedAt: 100 }] },
      { ids: ["a"] },
    );
    expect(p.borrados).toEqual(["a"]);
    expect(p.resultado).toEqual([]);
    expect(p.bajar).toEqual([]);
  });

  it("propaga al dispositivo un borrado hecho en la nube", () => {
    const p = fusionarConjunto(
      { ids: ["a"], tombstones: [] },
      { ids: [], tombstones: [{ id: "a", deletedAt: 100 }] },
    );
    expect(p.borrados).toEqual(["a"]);
    expect(p.resultado).toEqual([]);
  });

  it("una lápida no borra algo que sigue presente de los dos lados", () => {
    // Volvió a marcarse después: la presencia en ambos lados manda.
    const p = fusionarConjunto(
      { ids: ["a"], tombstones: [{ id: "a", deletedAt: 100 }] },
      { ids: ["a"] },
    );
    expect(p.resultado).toEqual(["a"]);
    expect(p.borrados).toEqual([]);
  });

  it("usa la lápida más reciente cuando hay varias", () => {
    const p = fusionarConjunto(
      { ids: [], tombstones: [{ id: "a", deletedAt: 100 }, { id: "a", deletedAt: 300 }] },
      { ids: ["a"] },
    );
    expect(p.borrados).toEqual(["a"]);
  });

  it("las lápidas de otros ids no afectan", () => {
    const p = fusionarConjunto(
      { ids: ["a"], tombstones: [{ id: "z", deletedAt: 100 }] },
      { ids: ["a", "b"] },
    );
    expect(p.resultado).toEqual(["a", "b"]);
    expect(p.borrados).toEqual([]);
  });
});

describe("fusión de elementos con fecha", () => {
  const el = (id: string, at: number): ElementoFechado => ({ id, at });

  it("gana el más reciente", () => {
    const p = fusionarFechados([el("a", 200)], [el("a", 100)]);
    expect(p.resultado).toEqual([el("a", 200)]);
    expect(p.conflictos).toEqual([{ id: "a", ganador: "LOCAL", local: 200, nube: 100 }]);
  });

  it("gana la nube cuando es más reciente", () => {
    const p = fusionarFechados([el("a", 100)], [el("a", 500)]);
    expect(p.resultado).toEqual([el("a", 500)]);
    expect(p.conflictos[0].ganador).toBe("NUBE");
    expect(p.bajar).toEqual([el("a", 500)]);
  });

  it("un empate exacto no es conflicto y converge a la nube", () => {
    // Que dos navegadores lleguen al mismo valor importa más que quién gana.
    const p = fusionarFechados([el("a", 100)], [el("a", 100)]);
    expect(p.conflictos).toEqual([]);
    expect(p.subir).toEqual([]);
    expect(p.bajar).toEqual([]);
  });

  it("conserva lo que está de un solo lado", () => {
    const p = fusionarFechados([el("a", 100)], [el("b", 200)]);
    expect(p.resultado.map((x) => x.id)).toEqual(["b", "a"]);
    expect(p.subir).toEqual([el("a", 100)]);
    expect(p.bajar).toEqual([el("b", 200)]);
  });

  it("ordena del más reciente al más viejo", () => {
    const p = fusionarFechados([el("a", 100), el("c", 300)], [el("b", 200)]);
    expect(p.resultado.map((x) => x.id)).toEqual(["c", "b", "a"]);
  });

  it("desempata por id para ser determinista", () => {
    const p = fusionarFechados([el("b", 100), el("a", 100)], []);
    expect(p.resultado.map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("es idempotente", () => {
    const primera = fusionarFechados([el("a", 200)], [el("a", 100), el("b", 50)]);
    const segunda = fusionarFechados(primera.resultado, primera.resultado);
    expect(segunda.resultado).toEqual(primera.resultado);
    expect(segunda.conflictos).toEqual([]);
  });

  it("preserva los campos extra del elemento ganador", () => {
    type Coleccion = ElementoFechado & { name: string; ids: string[] };
    const local: Coleccion = { id: "c1", at: 300, name: "Para visitar", ids: ["p1"] };
    const nube: Coleccion = { id: "c1", at: 100, name: "Vieja", ids: ["p9"] };
    const p = fusionarFechados([local], [nube]);
    expect(p.resultado[0].name).toBe("Para visitar");
    expect(p.resultado[0].ids).toEqual(["p1"]);
  });
});

describe("la regla del borrado", () => {
  it("sólo se limpia lo local tras confirmar", () => {
    // Es la regla explícita del encargo: nunca borrar local antes de que la
    // nube haya confirmado.
    expect(puedeLimpiarLocal("CONFIRMADO")).toBe(true);
    for (const e of ["PLANIFICADO", "SUBIENDO", "FALLIDO"] as EstadoSync[]) {
      expect(puedeLimpiarLocal(e)).toBe(false);
    }
  });

  it("un fallo a mitad de camino no habilita limpiar", () => {
    // La ventana entre "subí" y "guardé" es donde se pierden datos.
    expect(puedeLimpiarLocal("SUBIENDO")).toBe(false);
    expect(puedeLimpiarLocal("FALLIDO")).toBe(false);
  });
});
