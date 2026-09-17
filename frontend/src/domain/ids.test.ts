import { describe, expect, it } from "vitest";
import { comoIdOpcional, esIdValido, listingId, organizationId, propertyEntityId } from "./ids";

describe("identificadores", () => {
  it("acepta las formas que realmente existen hoy", () => {
    // Ids numéricos de la base, slugs, y UUID futuros.
    expect(esIdValido("257073")).toBe(true);
    expect(esIdValido("inmobiliaria-lopez")).toBe(true);
    expect(esIdValido("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
  });

  it("convierte ids numéricos, porque la base los tiene así", () => {
    expect(propertyEntityId(12345)).toBe("12345");
  });

  it("rechaza lo que no puede ser un id legítimo", () => {
    // Vacío, espacios e inyección: nada de esto viene de un dato real.
    for (const malo of ["", " ", "a b", "a/b", "a'b", "1; drop table", "a\nb"]) {
      expect(esIdValido(malo)).toBe(false);
    }
  });

  it("rechaza ids desmesurados", () => {
    // Un id de 5.000 caracteres es un bug o un intento de abuso, nunca un dato.
    expect(esIdValido("x".repeat(128))).toBe(true);
    expect(esIdValido("x".repeat(129))).toBe(false);
  });

  it("no filtra el valor recibido en el mensaje de error", () => {
    // Puede venir de una URL pública y terminar en un log.
    const secreto = "token@abc";
    try {
      listingId(secreto);
      expect.unreachable("debería haber fallado");
    } catch (e) {
      expect((e as Error).message).not.toContain(secreto);
      expect((e as Error).message).toMatch(/publicación/);
    }
  });

  it("nombra qué se esperaba, para que el error sea accionable", () => {
    expect(() => organizationId("")).toThrow(/organización/);
    expect(() => propertyEntityId("")).toThrow(/propiedad/);
  });

  it("la variante opcional distingue ausencia de invalidez sin fallar", () => {
    expect(comoIdOpcional(null)).toBeNull();
    expect(comoIdOpcional(undefined)).toBeNull();
    expect(comoIdOpcional("")).toBeNull();
    expect(comoIdOpcional("a b")).toBeNull();
    expect(comoIdOpcional("ok-1")).toBe("ok-1");
  });

  it("no confunde NaN ni Infinity con un id numérico", () => {
    expect(comoIdOpcional(Number.NaN)).toBeNull();
    expect(comoIdOpcional(Number.POSITIVE_INFINITY)).toBeNull();
    expect(comoIdOpcional(0)).toBe("0");
  });
});
