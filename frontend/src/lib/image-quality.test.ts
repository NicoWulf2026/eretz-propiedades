import { describe, expect, it } from "vitest";
import {
  IMAGE_CLASS_HIGH, IMAGE_CLASS_POSSIBLE, IMAGE_CLASS_VALID,
  classifyPropertyImage, displayableImages,
} from "@/lib/image-quality";

const WP = "https://ejemplo.com.ar/wp-content/uploads/2024/07/";

describe("clasificación de imágenes no representativas", () => {
  // Casos tomados de la auditoría real del inventario.
  it.each([
    ["http://{s}.tile.osm.org/{z}/{x}/{y}.png", null],
    ["https://maps.gstatic.com/mapfiles/api-3/images/spotlight-poi3.png", null],
    ["https://bh.com.ar/ing_real_estate_web_base/static/src/img/realestate.jpg", null],
    ["https://meta.com.ar/assets/og/og-home.jpg", null],
    ["https://conectiva.com/wp-content/uploads/2025/07/mt-sample-background.jpg", null],
    ["http://ortiz.com.ar/contenido/sinfoto.jpg", null],
    [`${WP}losandesdefault.jpg`, null],
    ["https://x.com/plugins/includes/images/transparent.gif", null],
    [`${WP}PROPAR-Avatar-210x210-1.jpg`, null],
    [`${WP}MATRICULA_HECTOR_LEZCANO.png`, null],
    ["https://rbessa.com.ar/wp-content/uploads/2022/09/BESSA-BLANCA-FONDOTRANSP542-e1663633539937.png", "Inmobiliaria Bessa"],
    [`${WP}calicio-blanco.png`, "Griselda Calicio Inmobiliaria Propiedades"],
  ])("clasifica como HIGH: %s", (url, publisher) => {
    expect(classifyPropertyImage(url, publisher).imageClass).toBe(IMAGE_CLASS_HIGH);
  });

  it.each([
    ["https://rbessa.com.ar/wp-content/uploads/2024/12/frente.jpeg", "Inmobiliaria Bessa"],
    [`${WP}casa-frente-jardin.jpg`, null],
    // "blanca" en medio no es variante cromática de logo.
    [`${WP}casa-blanca-frente.jpg`, "Inmobiliaria Sur"],
    // La palabra del rubro no debe disparar el match de publicador.
    ["https://sur.com/uploads/depto-inmobiliaria-vista.jpg", "Inmobiliaria Sur"],
  ])("conserva como válida: %s", (url, publisher) => {
    expect(classifyPropertyImage(url, publisher).imageClass).toBe(IMAGE_CLASS_VALID);
  });

  it("repetir no invalida: el loteo real queda POSSIBLE, no HIGH", () => {
    const url = "https://aquino.com.ar/wp-content/uploads/2026/03/Loteo-Sumio-25-1024x745.webp";
    expect(classifyPropertyImage(url, "Pablo Aquino Inmobiliaria", 30).imageClass)
      .toBe(IMAGE_CLASS_POSSIBLE);
  });

  it("url vacía es HIGH", () => {
    expect(classifyPropertyImage("").imageClass).toBe(IMAGE_CLASS_HIGH);
    expect(classifyPropertyImage("   ").imageClass).toBe(IMAGE_CLASS_HIGH);
  });
});

describe("displayableImages", () => {
  it("descarta sólo las HIGH y conserva el resto", () => {
    const raw = [
      "https://rbessa.com.ar/wp-content/uploads/2022/09/BESSA-BLANCA-FONDOTRANSP542-e1663633539937.png",
      "https://rbessa.com.ar/wp-content/uploads/2024/12/frente.jpeg",
    ];
    expect(displayableImages(raw, "Inmobiliaria Bessa")).toEqual([raw[1]]);
  });

  it("una propiedad cuya única imagen es branding queda sin fotos válidas", () => {
    const raw = ["https://rbessa.com.ar/wp-content/uploads/2022/09/BESSA-BLANCA-FONDOTRANSP542-e1663633539937.png"];
    expect(displayableImages(raw, "Inmobiliaria Bessa")).toEqual([]);
  });

  it("no toca galerías de fotos reales", () => {
    const raw = [`${WP}frente.jpg`, `${WP}living.jpg`, `${WP}cocina.jpg`];
    expect(displayableImages(raw, "Sur Propiedades")).toEqual(raw);
  });

  it("POSSIBLE no se oculta: ocultar por sospecha escondería fotos reales", () => {
    const raw = ["https://aquino.com.ar/wp-content/uploads/2026/03/Loteo-Sumio-25-1024x745.webp"];
    expect(displayableImages(raw, "Pablo Aquino Inmobiliaria")).toEqual(raw);
  });
});
