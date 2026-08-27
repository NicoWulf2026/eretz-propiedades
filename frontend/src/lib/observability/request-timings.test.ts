import { describe, expect, it } from "vitest";
import {
  MAXIMO_ETIQUETAS,
  camposDeTiempos,
  crearAcumulador,
  ejecutarEn,
  hayTiempos,
  medirEnRequest,
  registrarTiempo,
} from "./request-timings";

describe("alcance por request", () => {
  it("dos requests concurrentes no se mezclan las mediciones", () => {
    // Es la razón de usar AsyncLocalStorage en vez de una variable de módulo:
    // con un acumulador compartido, cada request reportaría el trabajo de las
    // otras.
    const a = crearAcumulador();
    const b = crearAcumulador();

    ejecutarEn(a, () => registrarTiempo("db", 100));
    ejecutarEn(b, () => registrarTiempo("db", 7));

    expect(camposDeTiempos(a)).toEqual({ db_ms: 100, db_n: 1 });
    expect(camposDeTiempos(b)).toEqual({ db_ms: 7, db_n: 1 });
  });

  it("se mantiene a través de await, que es donde una variable global fallaría", async () => {
    const a = crearAcumulador();
    const b = crearAcumulador();

    const trabajo = (acumulador: ReturnType<typeof crearAcumulador>, ms: number) =>
      ejecutarEn(acumulador, async () => {
        await new Promise((r) => setTimeout(r, 1));
        registrarTiempo("db", ms);
      });

    await Promise.all([trabajo(a, 50), trabajo(b, 3)]);

    expect(camposDeTiempos(a).db_ms).toBe(50);
    expect(camposDeTiempos(b).db_ms).toBe(3);
  });
});

describe("fuera de una request no hace nada", () => {
  it("registrar sin contexto no lanza ni acumula", () => {
    expect(() => registrarTiempo("db", 100)).not.toThrow();
  });

  it("medir sin contexto devuelve el valor igual", async () => {
    // Es el caso de los tests unitarios y de cualquier script que use la capa
    // de datos por fuera de una ruta.
    await expect(medirEnRequest("db", async () => 42)).resolves.toBe(42);
  });

  it("propaga el error de la operación medida", async () => {
    await expect(medirEnRequest("db", async () => { throw new Error("cayó"); })).rejects.toThrow("cayó");
  });
});

describe("acumulación", () => {
  it("suma varias consultas y cuenta cuántas fueron", () => {
    // `db_ms=1900 db_n=3` distingue una consulta lenta de tres que se acumulan.
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      registrarTiempo("db", 1000);
      registrarTiempo("db", 900);
      registrarTiempo("db", 5);
    });
    expect(camposDeTiempos(a)).toEqual({ db_ms: 1905, db_n: 3 });
  });

  it("separa etiquetas distintas y las ordena", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      registrarTiempo("gate", 5);
      registrarTiempo("db", 10);
    });
    expect(Object.keys(camposDeTiempos(a))).toEqual(["db_ms", "db_n", "gate_ms", "gate_n"]);
  });

  it("mide también cuando la operación falla", async () => {
    // Una consulta que tarda cinco segundos y después revienta es justamente
    // la que hay que ver.
    const a = crearAcumulador();
    await ejecutarEn(a, async () => {
      await medirEnRequest("db", async () => { throw new Error("x"); }).catch(() => undefined);
    });
    expect(camposDeTiempos(a).db_n).toBe(1);
  });
});

describe("defensas", () => {
  it("descarta etiquetas mal formadas", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      for (const mala of ["", "DB", "con espacio", "con-guion", "1db", "x".repeat(40)]) {
        registrarTiempo(mala, 10);
      }
    });
    expect(camposDeTiempos(a)).toEqual({});
  });

  it("descarta duraciones imposibles", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      registrarTiempo("db", Number.NaN);
      registrarTiempo("db", -1);
      registrarTiempo("db", Number.POSITIVE_INFINITY);
    });
    expect(camposDeTiempos(a)).toEqual({});
  });

  it("acota la cantidad de etiquetas distintas", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      for (let i = 0; i < MAXIMO_ETIQUETAS + 5; i++) registrarTiempo(`etiqueta_${i}`, 1);
    });
    expect(Object.keys(camposDeTiempos(a))).toHaveLength(MAXIMO_ETIQUETAS * 2);
  });

  it("sigue acumulando en una etiqueta existente tras llegar al tope", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => {
      for (let i = 0; i < MAXIMO_ETIQUETAS; i++) registrarTiempo(`etiqueta_${i}`, 1);
      registrarTiempo("etiqueta_0", 9);
    });
    expect(camposDeTiempos(a).etiqueta_0_ms).toBe(10);
  });
});

describe("campos para el log", () => {
  it("todo lo que emite es escalar", () => {
    // `logEvent` descarta en silencio lo que no lo es.
    const a = crearAcumulador();
    ejecutarEn(a, () => registrarTiempo("db", 12.6));
    for (const valor of Object.values(camposDeTiempos(a))) {
      expect(typeof valor).toBe("number");
    }
  });

  it("redondea a milisegundos enteros", () => {
    const a = crearAcumulador();
    ejecutarEn(a, () => registrarTiempo("db", 12.6));
    expect(camposDeTiempos(a).db_ms).toBe(13);
  });

  it("un acumulador vacío no ensucia la línea", () => {
    const a = crearAcumulador();
    expect(hayTiempos(a)).toBe(false);
    expect(camposDeTiempos(a)).toEqual({});
  });
});
