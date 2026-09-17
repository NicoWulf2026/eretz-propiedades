import { describe, expect, it } from "vitest";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import {
  PARAMS_NO_CANONICOS,
  TIPOS_DE_PAGINA,
  type ContextoDeIndexacion,
  construirSitemap,
  directivaRobots,
  esCanonica,
  esIndexable,
  urlCanonica,
} from "./seo";

const prod = (o: Partial<ContextoDeIndexacion> = {}): ContextoDeIndexacion => ({
  tipo: "HOME",
  produccion: true,
  ...o,
});

describe("Preview sigue cerrado y esto no lo cambia", () => {
  it("robots sigue prohibiendo todo", () => {
    process.env.NEXT_PUBLIC_SITE_INDEXING = "true";
    expect(robots()).toEqual({ rules: { userAgent: "*", disallow: "/" } });
  });

  it("el sitemap de la aplicación sigue vacío", () => {
    expect(sitemap()).toEqual([]);
  });

  it("fuera de producción nada es indexable, por ningún motivo", () => {
    for (const tipo of TIPOS_DE_PAGINA) {
      const v = esIndexable({ tipo, produccion: false, elegible: true, contenidoSuficiente: true, reclamado: true });
      expect(v.indexable).toBe(false);
      expect(v.motivo).toMatch(/Preview es noindex/);
    }
  });
});

describe("fail-closed", () => {
  it("un tipo de página desconocido no es indexable", () => {
    // Si fuera permisivo por defecto, agregar una ruta la expondría sin que
    // nadie lo decidiera.
    expect(esIndexable({ tipo: "NUEVA" as never, produccion: true }).indexable).toBe(false);
  });

  it("los estados de interfaz no se indexan", () => {
    for (const tipo of ["SEARCH_RESULTS", "MAP", "MY_ERETZ", "COMPARE", "ADMIN", "ACCOUNT", "REPORT_FLOW"] as const) {
      const v = esIndexable(prod({ tipo, contenidoSuficiente: true, elegible: true }));
      expect(v.indexable).toBe(false);
      expect(v.motivo).toMatch(/identidad propia/);
    }
  });
});

describe("qué sí podría indexarse", () => {
  it("la home", () => {
    expect(esIndexable(prod({ tipo: "HOME" })).indexable).toBe(true);
  });

  it("una ficha que pasa el Quality Gate", () => {
    expect(esIndexable(prod({ tipo: "LISTING_DETAIL", elegible: true })).indexable).toBe(true);
  });

  it("nunca una ficha que el Gate excluye", () => {
    // Indexarla contradiría al Gate desde afuera.
    for (const elegible of [false, undefined]) {
      expect(esIndexable(prod({ tipo: "LISTING_DETAIL", elegible })).indexable).toBe(false);
    }
  });

  it("un perfil de agente sólo si la persona lo reclamó", () => {
    expect(esIndexable(prod({ tipo: "AGENT_PROFILE", reclamado: true })).indexable).toBe(true);
    const v = esIndexable(prod({ tipo: "AGENT_PROFILE", reclamado: false }));
    expect(v.indexable).toBe(false);
    expect(v.motivo).toMatch(/no reclamó/);
  });

  it("inmobiliarias y páginas de zona sólo con contenido propio", () => {
    // Una página de ciudad con dos propiedades perjudica al sitio entero.
    for (const tipo of ["ORGANIZATION_PROFILE", "CITY_LANDING", "NEIGHBORHOOD_LANDING"] as const) {
      expect(esIndexable(prod({ tipo, contenidoSuficiente: true })).indexable).toBe(true);
      expect(esIndexable(prod({ tipo, contenidoSuficiente: false })).indexable).toBe(false);
      expect(esIndexable(prod({ tipo })).indexable).toBe(false);
    }
  });

  it("una URL con parámetros no canónicos no se indexa", () => {
    const v = esIndexable(prod({ tipo: "HOME", params: ["sort", "utm_source"] }));
    expect(v.indexable).toBe(false);
    expect(v.motivo).toMatch(/no canónicos/);
  });

  it("siempre explica el veredicto", () => {
    for (const tipo of TIPOS_DE_PAGINA) {
      expect(esIndexable(prod({ tipo })).motivo.length).toBeGreaterThan(0);
    }
  });
});

describe("URLs canónicas", () => {
  it("quita orden, paginación y estado de la interfaz", () => {
    expect(urlCanonica("https://e.com/buscar?city=Rosario&sort=price_asc&page=3&cursor=abc")).toBe(
      "https://e.com/buscar?city=Rosario",
    );
  });

  it("quita los parámetros de campaña", () => {
    expect(urlCanonica("https://e.com/p/1?utm_source=fb&fbclid=xyz&gclid=abc")).toBe("https://e.com/p/1");
  });

  it("ordena los parámetros que sobreviven", () => {
    // Si la canónica difiere según el orden en que se escribieron, deja de
    // cumplir su función.
    const a = urlCanonica("https://e.com/buscar?b=2&a=1");
    const b = urlCanonica("https://e.com/buscar?a=1&b=2");
    expect(a).toBe(b);
    expect(a).toBe("https://e.com/buscar?a=1&b=2");
  });

  it("quita la barra final salvo en la raíz", () => {
    expect(urlCanonica("https://e.com/inmobiliaria/lopez/")).toBe("https://e.com/inmobiliaria/lopez");
    expect(urlCanonica("https://e.com/")).toBe("https://e.com/");
  });

  it("quita el fragmento", () => {
    expect(urlCanonica("https://e.com/p/1#fotos")).toBe("https://e.com/p/1");
  });

  it("es idempotente", () => {
    const u = urlCanonica("https://e.com/buscar?sort=x&city=Rosario");
    expect(urlCanonica(u)).toBe(u);
    expect(esCanonica(u)).toBe(true);
  });

  it("no rompe con una URL inválida", () => {
    expect(urlCanonica("no es una url")).toBe("no es una url");
  });

  it("cubre los parámetros que importan", () => {
    for (const p of ["sort", "page", "cursor", "viewport", "selectedId", "utm_source", "fbclid"]) {
      expect(PARAMS_NO_CANONICOS).toContain(p);
    }
  });
});

describe("sitemap", () => {
  it("hoy sale vacío para todo, porque nada es producción", () => {
    // Es la garantía de que preparar esto no activa nada.
    const candidatos = TIPOS_DE_PAGINA.map((tipo) => ({
      tipo,
      produccion: false,
      url: `https://e.com/${tipo}`,
      elegible: true,
      contenidoSuficiente: true,
      reclamado: true,
    }));
    expect(construirSitemap(candidatos)).toEqual([]);
  });

  it("sólo incluye lo que la página marcaría indexable", () => {
    // Un sitemap que ofrece URLs marcadas noindex es una contradicción.
    const r = construirSitemap([
      { tipo: "LISTING_DETAIL", produccion: true, elegible: true, url: "https://e.com/p/1" },
      { tipo: "LISTING_DETAIL", produccion: true, elegible: false, url: "https://e.com/p/2" },
      { tipo: "SEARCH_RESULTS", produccion: true, url: "https://e.com/buscar" },
    ]);
    expect(r.map((x) => x.url)).toEqual(["https://e.com/p/1"]);
  });

  it("canoniza y deduplica", () => {
    const r = construirSitemap([
      { tipo: "HOME", produccion: true, url: "https://e.com/?sort=a" },
      { tipo: "HOME", produccion: true, url: "https://e.com/?utm_source=x" },
    ]);
    expect(r).toHaveLength(1);
  });

  it("conserva la fecha de modificación cuando la hay", () => {
    const r = construirSitemap([
      { tipo: "HOME", produccion: true, url: "https://e.com/", lastModified: "2026-08-01" },
    ]);
    expect(r[0].lastModified).toBe("2026-08-01");
    const sinFecha = construirSitemap([{ tipo: "HOME", produccion: true, url: "https://e.com/" }]);
    expect(sinFecha[0].lastModified).toBeNull();
  });

  it("ordena estable", () => {
    const r = construirSitemap([
      { tipo: "HOME", produccion: true, url: "https://e.com/b" },
      { tipo: "HOME", produccion: true, url: "https://e.com/a" },
    ]);
    expect(r.map((x) => x.url)).toEqual(["https://e.com/a", "https://e.com/b"]);
  });
});

describe("directiva de robots por página", () => {
  it("nofollow además de noindex en lo no indexable", () => {
    // Sin nofollow el rastreador recorre igual los enlaces de facetas y gasta
    // el presupuesto que se quería proteger.
    expect(directivaRobots(prod({ tipo: "SEARCH_RESULTS" }))).toBe("noindex, nofollow");
    expect(directivaRobots({ tipo: "HOME", produccion: false })).toBe("noindex, nofollow");
  });

  it("index, follow sólo donde corresponde", () => {
    expect(directivaRobots(prod({ tipo: "HOME" }))).toBe("index, follow");
  });
});
