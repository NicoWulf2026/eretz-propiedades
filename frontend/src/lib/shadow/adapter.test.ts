import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";
import type { SupabaseProperty } from "@/types/property";
import {
  aEntradaDeModeracion,
  aEntradaDeScore,
  aPublicacionAnalizable,
  hostDeUrl,
  operacionDeclarada,
  origenDeFila,
  tieneContacto,
  tituloReal,
} from "./adapter";
import { analizarCalidad } from "@/domain/data-quality";

const fila = (o: Partial<SupabaseProperty> = {}): SupabaseProperty => ({ ...completeRow, ...o });
const propiedadDe = (o: Partial<SupabaseProperty> = {}) => mapSupabasePropertyToProperty(fila(o));

describe("deshace los reemplazos de presentación", () => {
  it("una publicación sin título se adapta como sin título", () => {
    // El mapper escribe "Propiedad sin título". Leer `property.title` haría que
    // NINGUNA publicación apareciera nunca sin título.
    const p = propiedadDe({ titulo: null });
    expect(p.title).toBe("Propiedad sin título");
    expect(tituloReal(p)).toBeNull();
    expect(aPublicacionAnalizable(p, fila({ titulo: null })).title).toBeNull();
  });

  it("un título real se conserva", () => {
    const p = propiedadDe();
    expect(tituloReal(p)).toBe("Casa luminosa con jardín");
  });

  it("distingue 'sin operación' de 'operación a consultar'", () => {
    // `normalizeOperation` manda las dos a "consultar" y en `Property` se ven
    // idénticas.
    expect(propiedadDe({ operacion: null }).operation).toBe("consultar");
    expect(propiedadDe({ operacion: "consultar" }).operation).toBe("consultar");

    expect(operacionDeclarada(fila({ operacion: null }))).toBeNull();
    expect(operacionDeclarada(fila({ operacion: "consultar" }))).toBe("consultar");
    expect(operacionDeclarada(fila({ operacion: "   " }))).toBeNull();
  });

  it("usa el tipo crudo, porque el normalizado nunca está ausente", () => {
    // `normalizePropertyType` manda lo desconocido a "otro".
    const p = propiedadDe({ tipo_propiedad: null });
    expect(p.propertyType).toBe("otro");
    expect(aPublicacionAnalizable(p, fila({ tipo_propiedad: null })).propertyType).toBeNull();
  });
});

describe("origen", () => {
  it("reconoce el scraping por la columna de fuente", () => {
    expect(origenDeFila(fila({ fuente_extraccion: "public", cms_origen: null }))).toBe("SCRAPED");
    expect(origenDeFila(fila({ fuente_extraccion: null, cms_origen: "wordpress" }))).toBe("SCRAPED");
  });

  it("sin ninguna de las dos columnas, el origen es desconocido y no se inventa", () => {
    expect(origenDeFila(fila({ fuente_extraccion: null, cms_origen: null }))).toBe("UNKNOWN");
    expect(origenDeFila(fila({ fuente_extraccion: "  ", cms_origen: "" }))).toBe("UNKNOWN");
  });

  it("un origen desconocido no cae en la rama que bloquea", () => {
    // Al no ser MANUAL ni API, la moderación revisa en vez de rechazar.
    const f = fila({ fuente_extraccion: null, cms_origen: null });
    const p = mapSupabasePropertyToProperty(f);
    const entrada = aEntradaDeModeracion(p, f, analizarCalidad(aPublicacionAnalizable(p, f)));
    expect(entrada.origin).toBe("UNKNOWN");
  });
});

describe("host de la fuente", () => {
  it("extrae el host y le saca www", () => {
    expect(hostDeUrl("https://www.Inmobiliaria.COM.ar/p/1")).toBe("inmobiliaria.com.ar");
  });

  it("tolera ausencia y basura sin lanzar", () => {
    expect(hostDeUrl(null)).toBeNull();
    expect(hostDeUrl("no es una url")).toBeNull();
    expect(hostDeUrl("")).toBeNull();
  });
});

describe("contacto", () => {
  it("reconoce teléfono, email o web del publicador", () => {
    expect(tieneContacto(propiedadDe({ publisher_phone: "3410000000" }))).toBe(true);
    expect(tieneContacto(propiedadDe({ publisher_email: "a@b.com", publisher_phone: null }))).toBe(true);
  });

  it("reconoce el teléfono del agente cuando no hay publicador", () => {
    const p = propiedadDe({
      publisher_name: null, publisher_phone: null, publisher_email: null, publisher_website: null,
      agente_nombre: "Juan", agente_telefono: "3410000000",
    });
    expect(tieneContacto(p)).toBe(true);
  });

  it("sin ninguna vía, no hay contacto", () => {
    const p = propiedadDe({
      publisher_name: null, publisher_phone: null, publisher_email: null, publisher_website: null,
      agente_nombre: null, agente_telefono: null,
    });
    expect(tieneContacto(p)).toBe(false);
  });
});

describe("nulls y ausencias", () => {
  it("una fila casi vacía se adapta sin lanzar", () => {
    const vacia = fila({
      titulo: null, descripcion: null, precio: null, moneda: null, precio_usd: null,
      tipo_propiedad: null, operacion: null, ambientes: null, dormitorios: null, banos: null,
      superficie_total: null, superficie_cubierta: null, superficie_terreno: null,
      direccion: null, barrio: null, ciudad: null, provincia: null,
      latitud: null, longitud: null, imagenes: null, antiguedad: null, expensas: null,
      cocheras: null, agente_nombre: null, agente_telefono: null,
      publisher_name: null, publisher_phone: null, publisher_email: null,
      publisher_website: null, publisher_verified: null,
      fuente_extraccion: null, cms_origen: null,
    });
    const p = mapSupabasePropertyToProperty(vacia);
    expect(() => aPublicacionAnalizable(p, vacia)).not.toThrow();

    const analizable = aPublicacionAnalizable(p, vacia);
    expect(analizable.title).toBeNull();
    expect(analizable.operation).toBeNull();
    expect(analizable.propertyType).toBeNull();
    expect(analizable.price).toBeNull();
    expect(analizable.images).toEqual([]);
  });

  it("no inventa defaults semánticos para lo ausente", () => {
    const sinPrecio = fila({ precio: null, precio_usd: null, moneda: null });
    const p = mapSupabasePropertyToProperty(sinPrecio);
    const a = aPublicacionAnalizable(p, sinPrecio);
    expect(a.price).toBeNull();
    expect(a.price).not.toBe(0);
    expect(a.currency).toBeNull();
  });

  it("preserva los tres valores de verificación del publicador", () => {
    // null no es false. Hace falta `publisher_name`: sin él el mapper arma el
    // publicador desde `agente_nombre`, y esa rama fija `verified: null`
    // siempre, ignorando la columna.
    const de = (v: boolean | null) => {
      const f = fila({ publisher_name: "Inmobiliaria López", publisher_verified: v });
      const p = mapSupabasePropertyToProperty(f);
      return aEntradaDeScore(p, f, analizarCalidad(aPublicacionAnalizable(p, f))).publisherVerified;
    };
    expect(de(true)).toBe(true);
    expect(de(false)).toBe(false);
    expect(de(null)).toBeNull();
  });

  it("un publicador derivado del nombre del agente nunca figura verificado", () => {
    // Comportamiento del mapper que el adaptador refleja sin corregir: sabemos
    // un nombre, no una identidad verificada.
    const f = fila({ publisher_name: null, agente_nombre: "Juan Pérez", publisher_verified: true });
    const p = mapSupabasePropertyToProperty(f);
    expect(p.publisher?.name).toBe("Juan Pérez");
    expect(aEntradaDeScore(p, f, analizarCalidad(aPublicacionAnalizable(p, f))).publisherVerified).toBeNull();
  });
});

describe("duplicados no se evalúan", () => {
  it("siempre pasa NO_MATCH, que acá significa 'no evaluado'", () => {
    // Detectarlos exige comparar contra el resto del catálogo. Consecuencia:
    // el REJECT de scrapeadas dará 0 por construcción, no por medición.
    const f = fila();
    const p = mapSupabasePropertyToProperty(f);
    expect(aEntradaDeModeracion(p, f, analizarCalidad(aPublicacionAnalizable(p, f))).duplicate).toBe(
      "NO_MATCH",
    );
  });
});

describe("no muta nada", () => {
  it("adaptar no toca la fila ni la propiedad", () => {
    const f = fila();
    const p = mapSupabasePropertyToProperty(f);
    const copiaFila = structuredClone(f);
    const copiaProp = structuredClone(p);

    const calidad = analizarCalidad(aPublicacionAnalizable(p, f));
    aEntradaDeModeracion(p, f, calidad);
    aEntradaDeScore(p, f, calidad);

    expect(f).toEqual(copiaFila);
    expect(p).toEqual(copiaProp);
  });
});
