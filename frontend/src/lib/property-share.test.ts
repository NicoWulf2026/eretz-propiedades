import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { contactMessage, contactMessageWithTopics, propertyShareMessage } from "@/lib/property-share";
import { completeRow } from "@/test/fixtures";

describe("property sharing", () => {
  it("builds a useful message only from real property data", () => {
    const property = mapSupabasePropertyToProperty({
      ...completeRow,
      publisher_name: "Inmobiliaria Centro",
    });
    const message = propertyShareMessage(property, "https://eretz.test/propiedad/123");
    expect(message).toContain("Casa en venta");
    expect(message).toContain("USD 180.000");
    expect(message).toContain("3 dormitorios");
    expect(message).toContain("240 m²");
    expect(message).toContain("Inmobiliaria Centro");
    expect(contactMessage(property, "https://eretz.test/propiedad/123")).toContain(message);
  });

  it("omits unknown optional facts instead of saying no", () => {
    const property = mapSupabasePropertyToProperty({ ...completeRow, dormitorios: null, superficie_total: null });
    const message = propertyShareMessage(property, "https://eretz.test/propiedad/123");
    expect(message).not.toContain("dormitorio");
    expect(message).not.toContain("No");
  });
});

describe("compositor de contacto por intención", () => {
  const property = mapSupabasePropertyToProperty({ ...completeRow, id: 12345 });
  const url = "https://eretz.test/propiedad/12345";

  it("arma el mensaje SÓLO con los temas seleccionados (no inventa)", () => {
    const msg = contactMessageWithTopics(property, url, ["disponibilidad", "expensas", "visita"]);
    expect(msg).toBe("Hola, consulto por la propiedad ID ERETZ 12345. Quisiera consultar disponibilidad, expensas y coordinar una visita. " + url);
    expect(msg).not.toMatch(/mascotas|requisitos|ingreso/);
  });

  it("sin temas seleccionados no agrega la cláusula de consulta", () => {
    const msg = contactMessageWithTopics(property, url, []);
    expect(msg).toBe("Hola, consulto por la propiedad ID ERETZ 12345. " + url);
  });

  it("incluye el texto libre del usuario cuando existe", () => {
    const msg = contactMessageWithTopics(property, url, ["disponibilidad"], "¿Está disponible desde marzo?");
    expect(msg).toContain("disponibilidad");
    expect(msg).toContain("¿Está disponible desde marzo?");
  });
});

