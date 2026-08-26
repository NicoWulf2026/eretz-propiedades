import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { propertyDetailGroups, propertyDetailTitle, propertyReturnContext, publicationMatchConfidence } from "@/lib/property-detail";
import { completeRow } from "@/test/fixtures";

describe("presentación de Ficha V2", () => {
  it("usa tipo y ubicación útil en lugar del título scrapeado", () => {
    const property = mapSupabasePropertyToProperty({ ...completeRow, titulo: "IMPERDIBLE!!! oportunidad única", tipo_propiedad: "departamento", barrio: "Palermo", ciudad: "CABA", provincia: "CABA" });
    expect(propertyDetailTitle(property)).toBe("Departamento en Palermo, CABA");
  });

  it("preserva null y omite datos desconocidos", () => {
    const property = mapSupabasePropertyToProperty({ ...completeRow, apto_credito: null, banos: null, superficie_terreno: null });
    const facts = propertyDetailGroups(property).flatMap((group) => group.items);
    expect(property.mortgageEligible).toBeNull();
    expect(facts.some((item) => item.label === "Apto crédito")).toBe(false);
    expect(facts.some((item) => item.label === "Baños")).toBe(false);
    expect(facts.some((item) => item.label === "Terreno")).toBe(false);
  });

  it("resume el contexto real de retorno", () => {
    expect(propertyReturnContext("/propiedades?barrio=Palermo&dormitorios=2&moneda=USD&precio_max=200000&modo=results_only"))
      .toBe("en Palermo · 2+ dormitorios · hasta USD 200.000");
  });

  it("clasifica publicaciones equivalentes sin afirmar identidad por dirección solamente", () => {
    const property = mapSupabasePropertyToProperty({ ...completeRow, id: 1, direccion: "Independencia 700", precio: 100000, superficie_total: 60 });
    const similar = mapSupabasePropertyToProperty({ ...completeRow, id: 2, direccion: "Independencia 700 2A", precio: 101000, superficie_total: 60 });
    const weak = mapSupabasePropertyToProperty({ ...completeRow, id: 3, direccion: "Independencia 700", precio: 300000, superficie_total: 200, titulo: "Casa con pileta" });
    expect(publicationMatchConfidence(property, similar)).toBe("HIGH_CONFIDENCE");
    expect(publicationMatchConfidence(property, weak)).not.toBe("HIGH_CONFIDENCE");
  });
});
