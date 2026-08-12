import { describe, expect, it } from "vitest";
import { entitySlug, idFromSlug, slugify } from "@/lib/slug";

describe("slug", () => {
  it("normaliza acentos, espacios y símbolos", () => {
    expect(slugify("Inmobiliaria Ñandú & Cía.")).toBe("inmobiliaria-nandu-cia");
  });
  it("nunca queda vacío", () => {
    expect(slugify("")).toBe("perfil");
    expect(slugify("!!!")).toBe("perfil");
  });
  it("adjunta el id y lo recupera", () => {
    const slug = entitySlug(1234, "Acme Propiedades");
    expect(slug).toBe("acme-propiedades-1234");
    expect(idFromSlug(slug)).toBe("1234");
  });
  it("recupera el id aunque el nombre tenga números", () => {
    expect(idFromSlug(entitySlug(77, "Grupo 21"))).toBe("77");
  });
  it("devuelve vacío si el slug no trae id", () => {
    expect(idFromSlug("sin-id")).toBe("");
  });
});
