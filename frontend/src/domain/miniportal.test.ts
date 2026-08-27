import { describe, expect, it } from "vitest";
import {
  CONFIG_POR_DEFECTO,
  CONTRASTE_MINIMO,
  LARGO_MAXIMO_DESCRIPCION,
  MAXIMO_DESTACADAS,
  PLANTILLAS,
  SECCIONES,
  SECCIONES_OBLIGATORIAS,
  contraste,
  contrasteSuficiente,
  destacadasAjenas,
  esColorValido,
  normalizarConfig,
  seccionesVisibles,
  validarConfig,
} from "./miniportal";

const codigos = (v: unknown) => validarConfig(v).map((p) => `${p.campo}:${p.code}`);

describe("sin configuración se ve bien igual", () => {
  it("normaliza undefined a una configuración completa", () => {
    // Miles de inmobiliarias y ninguna configuró nada: si dependiera de que
    // exista config, el 100% se vería roto.
    const c = normalizarConfig(undefined);
    expect(c.plantilla).toBe("CLASICA");
    expect(c.tokens.primario).toMatch(/^#[0-9a-f]{6}$/i);
    expect(c.secciones).toHaveLength(SECCIONES.length);
  });

  it("nunca falla, con la entrada que sea", () => {
    for (const basura of [null, 0, "x", [], true, { tokens: "no" }, { secciones: 42 }]) {
      expect(() => normalizarConfig(basura)).not.toThrow();
      expect(normalizarConfig(basura).secciones.length).toBeGreaterThan(0);
    }
  });

  it("nunca devuelve null", () => {
    expect(normalizarConfig(null)).not.toBeNull();
  });

  it("la config por defecto pasa su propia validación", () => {
    expect(validarConfig(CONFIG_POR_DEFECTO)).toEqual([]);
  });
});

describe("la personalización no es código", () => {
  it("descarta cualquier color que no sea #rrggbb estricto", () => {
    // Es lo que impide colar `red; background: url(//espia)`.
    for (const malo of [
      "red",
      "#fff",
      "rgb(1,2,3)",
      "#2f5d50; background: url(//espia)",
      "javascript:alert(1)",
      "var(--x)",
      "#gggggg",
    ]) {
      expect(esColorValido(malo)).toBe(false);
      const c = normalizarConfig({ tokens: { primario: malo } });
      expect(c.tokens.primario).toBe(CONFIG_POR_DEFECTO.tokens.primario);
    }
  });

  it("acepta hexadecimal válido en cualquier caja", () => {
    expect(normalizarConfig({ tokens: { primario: "#AABBCC" } }).tokens.primario).toBe("#AABBCC");
  });

  it("descarta plantillas inventadas", () => {
    expect(normalizarConfig({ plantilla: "<script>" }).plantilla).toBe("CLASICA");
    expect(codigos({ plantilla: "MIA" })).toContain("plantilla:DESCONOCIDA");
  });

  it("descarta secciones que no existen", () => {
    const c = normalizarConfig({ secciones: [{ id: "INYECCION", visible: true }] });
    expect(c.secciones.every((s) => (SECCIONES as readonly string[]).includes(s.id))).toBe(true);
  });

  it("rechaza URLs con protocolos peligrosos", () => {
    for (const malo of ["javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd"]) {
      expect(normalizarConfig({ logoUrl: malo }).logoUrl).toBeNull();
      expect(codigos({ logoUrl: malo })).toContain("logoUrl:URL_INVALIDA");
    }
  });

  it("no hay ningún campo donde entre CSS, HTML ni JS", () => {
    const c = normalizarConfig({
      css: "body{display:none}",
      html: "<script>alert(1)</script>",
      script: "alert(1)",
    });
    expect(c).not.toHaveProperty("css");
    expect(c).not.toHaveProperty("html");
    expect(c).not.toHaveProperty("script");
  });
});

describe("contraste", () => {
  it("calcula la relación conocida entre negro y blanco", () => {
    expect(contraste("#000000", "#ffffff")).toBeCloseTo(21, 4);
  });

  it("un color contra sí mismo da 1", () => {
    expect(contraste("#2f5d50", "#2f5d50")).toBeCloseTo(1, 6);
  });

  it("es simétrico", () => {
    expect(contraste("#123456", "#fedcba")).toBeCloseTo(contraste("#fedcba", "#123456"), 10);
  });

  it("detecta el error más común: texto ilegible sobre el fondo elegido", () => {
    // No es malicioso: es una inmobiliaria eligiendo su color de marca.
    expect(contrasteSuficiente("#ffffff", "#fffffe")).toBe(false);
    expect(contrasteSuficiente("#000000", "#ffffff")).toBe(true);
    expect(CONTRASTE_MINIMO).toBe(4.5);
  });

  it("al normalizar prefiere una página legible antes que todos los colores", () => {
    const c = normalizarConfig({ tokens: { fondo: "#ffffff", texto: "#fffffe" } });
    expect(contrasteSuficiente(c.tokens.texto, c.tokens.fondo)).toBe(true);
  });

  it("al validar sí avisa en vez de corregir en silencio", () => {
    expect(codigos({ tokens: { fondo: "#ffffff", texto: "#fffffe" } })).toContain(
      "tokens.texto:CONTRASTE_INSUFICIENTE",
    );
  });
});

describe("secciones", () => {
  it("respeta el orden que se pide", () => {
    const c = normalizarConfig({
      secciones: [
        { id: "CONTACTO", visible: true },
        { id: "HERO", visible: true },
        { id: "PROPIEDADES", visible: true },
      ],
    });
    expect(c.secciones.slice(0, 3).map((s) => s.id)).toEqual(["CONTACTO", "HERO", "PROPIEDADES"]);
  });

  it("completa al final las secciones que falten", () => {
    // Una config vieja no pierde secciones nuevas ni queda incompleta.
    const c = normalizarConfig({ secciones: [{ id: "CONTACTO", visible: true }] });
    expect(c.secciones).toHaveLength(SECCIONES.length);
    expect(new Set(c.secciones.map((s) => s.id)).size).toBe(SECCIONES.length);
  });

  it("no deja ocultar las obligatorias", () => {
    const c = normalizarConfig({
      secciones: SECCIONES_OBLIGATORIAS.map((id) => ({ id, visible: false })),
    });
    for (const id of SECCIONES_OBLIGATORIAS) {
      expect(c.secciones.find((s) => s.id === id)?.visible).toBe(true);
    }
  });

  it("descarta secciones repetidas", () => {
    const c = normalizarConfig({
      secciones: [
        { id: "CONTACTO", visible: true },
        { id: "CONTACTO", visible: false },
      ],
    });
    expect(c.secciones.filter((s) => s.id === "CONTACTO")).toHaveLength(1);
  });

  it("devuelve las visibles en orden", () => {
    const c = normalizarConfig(undefined);
    expect(seccionesVisibles(c)).toEqual(["HERO", "PROPIEDADES", "CONTACTO"]);
  });
});

describe("redes sociales", () => {
  it("acepta un enlace que apunta de verdad a esa red", () => {
    const c = normalizarConfig({ redes: [{ red: "instagram", url: "https://instagram.com/lopez" }] });
    expect(c.redes).toEqual([{ red: "instagram", url: "https://instagram.com/lopez" }]);
  });

  it("descarta un enlace que no apunta a la red que dice", () => {
    // Sin esto, el ícono de Instagram podría llevar a cualquier lado.
    const c = normalizarConfig({ redes: [{ red: "instagram", url: "https://sitio-raro.com/x" }] });
    expect(c.redes).toEqual([]);
    expect(codigos({ redes: [{ red: "instagram", url: "https://sitio-raro.com/x" }] })).toContain(
      "redes:ENLACE_NO_COINCIDE",
    );
  });

  it("acepta subdominios y www del host oficial", () => {
    const c = normalizarConfig({ redes: [{ red: "facebook", url: "https://www.facebook.com/lopez" }] });
    expect(c.redes).toHaveLength(1);
  });

  it("acepta los hosts alternativos conocidos", () => {
    const c = normalizarConfig({
      redes: [
        { red: "x", url: "https://twitter.com/lopez" },
        { red: "youtube", url: "https://youtu.be/abc" },
      ],
    });
    expect(c.redes).toHaveLength(2);
  });

  it("descarta redes desconocidas y repetidas", () => {
    const c = normalizarConfig({
      redes: [
        { red: "myspace", url: "https://myspace.com/x" },
        { red: "instagram", url: "https://instagram.com/a" },
        { red: "instagram", url: "https://instagram.com/b" },
      ],
    });
    expect(c.redes).toHaveLength(1);
    expect(c.redes[0].url).toContain("/a");
  });
});

describe("destacadas", () => {
  it("acota la cantidad", () => {
    const muchas = Array.from({ length: 50 }, (_, i) => `p${i}`);
    expect(normalizarConfig({ destacadas: muchas }).destacadas).toHaveLength(MAXIMO_DESTACADAS);
    expect(codigos({ destacadas: muchas })).toContain("destacadas:DEMASIADAS");
  });

  it("quita repetidas y valores que no son ids", () => {
    const c = normalizarConfig({ destacadas: ["p1", "p1", "", null, 5, "a b", "p2"] });
    expect(c.destacadas).toEqual(["p1", "p2"]);
  });

  it("detecta destacar propiedades de otra inmobiliaria", () => {
    const propias = new Set(["p1", "p2"]);
    expect(destacadasAjenas(["p1", "p9"], propias)).toEqual(["p9"]);
    expect(destacadasAjenas(["p1", "p2"], propias)).toEqual([]);
  });
});

describe("descripción", () => {
  it("recorta al máximo y avisa", () => {
    const larga = "x".repeat(LARGO_MAXIMO_DESCRIPCION + 500);
    expect(normalizarConfig({ descripcion: larga }).descripcion).toHaveLength(
      LARGO_MAXIMO_DESCRIPCION,
    );
    expect(codigos({ descripcion: larga })).toContain("descripcion:MUY_LARGA");
  });

  it("una descripción en blanco es ausencia, no cadena vacía", () => {
    expect(normalizarConfig({ descripcion: "   " }).descripcion).toBeNull();
  });
});

describe("normalizar y validar son momentos distintos", () => {
  it("normalizar no falla nunca; validar sí puede decir que no", () => {
    // Si fueran lo mismo, o la página se rompe o el editor acepta cualquier
    // cosa en silencio.
    const mala = { plantilla: "X", tokens: { primario: "red" }, logoUrl: "javascript:1" };
    expect(() => normalizarConfig(mala)).not.toThrow();
    expect(validarConfig(mala).length).toBeGreaterThan(0);
  });

  it("es idempotente: normalizar lo ya normalizado no cambia nada", () => {
    const una = normalizarConfig({ plantilla: "COMPACTA", tokens: { primario: "#123456" } });
    expect(normalizarConfig(una)).toEqual(una);
  });

  it("todo lo que normaliza pasa la validación", () => {
    for (const entrada of [undefined, { plantilla: "X" }, { redes: [{ red: "instagram", url: "x" }] }]) {
      expect(validarConfig(normalizarConfig(entrada))).toEqual([]);
    }
  });

  it("las plantillas declaradas son las que se aceptan", () => {
    for (const p of PLANTILLAS) {
      expect(normalizarConfig({ plantilla: p }).plantilla).toBe(p);
    }
  });
});
