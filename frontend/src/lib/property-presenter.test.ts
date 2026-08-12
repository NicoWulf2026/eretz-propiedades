import { describe, expect, it } from "vitest";
import { availabilityLabel, isAvailabilityConfirmed } from "@/lib/property-presenter";

describe("disponibilidad no confirmada", () => {
  it("sólo 'activa' es disponibilidad confirmada", () => {
    expect(isAvailabilityConfirmed("activa")).toBe(true);
    expect(isAvailabilityConfirmed("no_detectada_en_ultimo_scraping")).toBe(false);
    expect(isAvailabilityConfirmed("desconocida")).toBe(false);
  });

  it("muestra la etiqueta neutral sólo cuando corresponde", () => {
    expect(availabilityLabel("activa")).toBeNull();
    expect(availabilityLabel("no_detectada_en_ultimo_scraping")).toBe("Disponibilidad no confirmada");
    expect(availabilityLabel("desconocida")).toBe("Disponibilidad no confirmada");
  });
});
