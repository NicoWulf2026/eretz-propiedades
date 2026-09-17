import { describe, expect, it } from "vitest";
import {
  VAR_MUESTREO,
  VAR_SHADOW,
  configuracionShadow,
  entraEnMuestra,
  fraccionDeMuestreo,
  hashDeId,
  shadowActivo,
} from "./flag";

const env = (v: Record<string, string | undefined>) => v as NodeJS.ProcessEnv;

describe("apagado por defecto", () => {
  it("sin la variable, apagado", () => {
    expect(shadowActivo(env({}))).toBe(false);
  });

  it("sólo el string exacto 'true' lo enciende", () => {
    // Un interruptor con varias formas de encenderse tiene varias formas de
    // encenderse por error.
    expect(shadowActivo(env({ [VAR_SHADOW]: "true" }))).toBe(true);
    for (const valor of ["1", "TRUE", "True", "yes", "on", "si", " true", "true ", ""]) {
      expect(shadowActivo(env({ [VAR_SHADOW]: valor }))).toBe(false);
    }
  });

  it("un valor sin sentido deja el modo apagado, no encendido", () => {
    // No hay `!== "false"`, que es la forma habitual de encenderse por accidente.
    expect(shadowActivo(env({ [VAR_SHADOW]: "false" }))).toBe(false);
    expect(shadowActivo(env({ [VAR_SHADOW]: "cualquier cosa" }))).toBe(false);
  });

  it("la variable de muestreo por sí sola no enciende nada", () => {
    const c = configuracionShadow(env({ [VAR_MUESTREO]: "1" }));
    expect(c.activo).toBe(false);
    expect(c.fraccion).toBe(0);
  });
});

describe("muestreo", () => {
  it("por defecto evalúa todo cuando está encendido", () => {
    // Medir sobre el 1% daría distribuciones con ruido que nadie sabe leer.
    expect(configuracionShadow(env({ [VAR_SHADOW]: "true" }))).toEqual({ activo: true, fraccion: 1 });
  });

  it("acepta una fracción válida", () => {
    expect(fraccionDeMuestreo(env({ [VAR_MUESTREO]: "0.1" }))).toBe(0.1);
    expect(fraccionDeMuestreo(env({ [VAR_MUESTREO]: "0" }))).toBe(0);
    expect(fraccionDeMuestreo(env({ [VAR_MUESTREO]: "1" }))).toBe(1);
  });

  it("un valor inválido devuelve 0, no 1", () => {
    // Es el único default seguro para un número que no se entendió.
    for (const malo of ["abc", "-0.5", "2", "NaN", "Infinity"]) {
      expect(fraccionDeMuestreo(env({ [VAR_MUESTREO]: malo }))).toBe(0);
    }
  });
});

describe("la muestra es determinista, no aleatoria", () => {
  it("el mismo id da siempre el mismo hash", () => {
    // Con Math.random(), la misma propiedad entraría en una request y no en la
    // siguiente, y comparar dos mediciones dejaría de ser posible.
    expect(hashDeId("12345")).toBe(hashDeId("12345"));
    expect(hashDeId("12345")).not.toBe(hashDeId("12346"));
  });

  it("la pertenencia a la muestra es estable entre corridas", () => {
    const ids = Array.from({ length: 200 }, (_, i) => String(i));
    const primera = ids.filter((id) => entraEnMuestra(id, 0.3));
    const segunda = ids.filter((id) => entraEnMuestra(id, 0.3));
    expect(primera).toEqual(segunda);
  });

  it("fracción 1 incluye todo y 0 no incluye nada", () => {
    const ids = Array.from({ length: 50 }, (_, i) => String(i));
    expect(ids.every((id) => entraEnMuestra(id, 1))).toBe(true);
    expect(ids.some((id) => entraEnMuestra(id, 0))).toBe(false);
  });

  it("una fracción intermedia toma aproximadamente esa proporción", () => {
    const ids = Array.from({ length: 2000 }, (_, i) => `prop-${i}`);
    const incluidos = ids.filter((id) => entraEnMuestra(id, 0.25)).length;
    // Margen amplio: se comprueba que el hash reparte, no una distribución exacta.
    expect(incluidos).toBeGreaterThan(2000 * 0.15);
    expect(incluidos).toBeLessThan(2000 * 0.35);
  });

  it("una muestra más chica está contenida en la más grande", () => {
    // Propiedad del muestreo por hash: subir la fracción agrega, no reemplaza.
    const ids = Array.from({ length: 500 }, (_, i) => `p${i}`);
    const chica = new Set(ids.filter((id) => entraEnMuestra(id, 0.1)));
    const grande = new Set(ids.filter((id) => entraEnMuestra(id, 0.5)));
    for (const id of chica) expect(grande.has(id)).toBe(true);
  });

  it("el hash no desborda ni da negativos", () => {
    for (const id of ["", "a", "x".repeat(500), "257073", "🏠"]) {
      const h = hashDeId(id);
      expect(h).toBeGreaterThanOrEqual(0);
      expect(h).toBeLessThan(0x100000000);
      expect(Number.isInteger(h)).toBe(true);
    }
  });
});
