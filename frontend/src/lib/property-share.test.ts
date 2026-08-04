import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { contactMessage, propertyShareMessage } from "@/lib/property-share";
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

