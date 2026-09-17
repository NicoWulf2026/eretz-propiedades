// Personalización del mini-portal de una inmobiliaria.
//
// ---------------------------------------------------------------------------
// LA PERSONALIZACIÓN NO ES CÓDIGO
// ---------------------------------------------------------------------------
//
// La forma obvia de dejar personalizar es aceptar CSS. Nunca se hace acá, y no
// por purismo: CSS arbitrario en una página que sirve ERETZ permite
// exfiltración por selectores de atributo, superposición de elementos falsos
// sobre los reales, y `url()` que filtra a un tercero quién visitó qué. HTML y
// JS arbitrarios son directamente XSS en nuestro dominio.
//
// El modelo es cerrado en los tres niveles:
//
//   PLANTILLA          se elige de una lista. No se escribe.
//   TOKENS DE DISEÑO   colores en `#rrggbb` estricto y nada más. Un color que
//                      no calza el formato se descarta; no hay forma de colar
//                      `red; background: url(//espia)`.
//   SECCIONES          unión discriminada con orden. Se eligen y se ordenan,
//                      no se define su marcado.
//
// ---------------------------------------------------------------------------
// SIN CONFIGURACIÓN TIENE QUE VERSE BIEN
// ---------------------------------------------------------------------------
//
// Hay miles de inmobiliarias y ninguna configuró nada. Si la página dependiera
// de que exista config, el 100% del catálogo se vería roto. Por eso
// `normalizarConfig` **nunca falla y nunca devuelve null**: recibe `undefined`,
// basura o un objeto a medias, y siempre devuelve una configuración completa y
// coherente.

import { safeExternalUrl } from "@/lib/safe-url";

export const PLANTILLAS = ["CLASICA", "COMPACTA", "ESCAPARATE"] as const;
export type Plantilla = (typeof PLANTILLAS)[number];

export const SECCIONES = [
  "HERO",
  "PROPIEDADES_DESTACADAS",
  "PROPIEDADES",
  "SOBRE_NOSOTROS",
  "EQUIPO",
  "SUCURSALES",
  "CONTACTO",
] as const;
export type SeccionId = (typeof SECCIONES)[number];

/** Secciones que no se pueden quitar: sin ellas la página no tiene sentido. */
export const SECCIONES_OBLIGATORIAS: readonly SeccionId[] = Object.freeze(["HERO", "PROPIEDADES"]);

export const REDES = ["instagram", "facebook", "linkedin", "youtube", "tiktok", "x"] as const;
export type Red = (typeof REDES)[number];

/** Host oficial de cada red. Un enlace a otro host no es esa red. */
const HOSTS_DE_RED: Readonly<Record<Red, readonly string[]>> = Object.freeze({
  instagram: ["instagram.com"],
  facebook: ["facebook.com", "fb.com"],
  linkedin: ["linkedin.com"],
  youtube: ["youtube.com", "youtu.be"],
  tiktok: ["tiktok.com"],
  x: ["x.com", "twitter.com"],
});

// --- colores ---------------------------------------------------------------

/** `#rrggbb`, estricto. Nada más entra. */
const HEX = /^#[0-9a-f]{6}$/i;

export function esColorValido(v: unknown): v is string {
  return typeof v === "string" && HEX.test(v);
}

/** Componentes 0-255 de un `#rrggbb` ya validado. */
function componentes(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

/** Luminancia relativa según WCAG 2.1. */
export function luminancia(hex: string): number {
  const canal = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = componentes(hex);
  return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);
}

/**
 * Relación de contraste entre dos colores, de 1 a 21.
 *
 * Existe porque el error de personalización más frecuente no es malicioso: es
 * una inmobiliaria eligiendo su color de marca sobre un fondo que lo vuelve
 * ilegible. Sin esta comprobación, la página queda "funcionando" y nadie puede
 * leerla.
 */
export function contraste(a: string, b: string): number {
  const [la, lb] = [luminancia(a), luminancia(b)];
  const [claro, oscuro] = la > lb ? [la, lb] : [lb, la];
  return (claro + 0.05) / (oscuro + 0.05);
}

/** Mínimo de WCAG AA para texto normal. */
export const CONTRASTE_MINIMO = 4.5;

export function contrasteSuficiente(texto: string, fondo: string): boolean {
  return contraste(texto, fondo) >= CONTRASTE_MINIMO;
}

// --- configuración ---------------------------------------------------------

export type TokensDeDiseno = {
  primario: string;
  fondo: string;
  texto: string;
};

export type SeccionConfig = {
  id: SeccionId;
  visible: boolean;
};

export type EnlaceDeRed = {
  red: Red;
  url: string;
};

export type MiniportalConfig = {
  plantilla: Plantilla;
  tokens: TokensDeDiseno;
  logoUrl: string | null;
  coverUrl: string | null;
  avatarUrl: string | null;
  descripcion: string | null;
  /** Orden y visibilidad. El orden del array ES el orden en la página. */
  secciones: SeccionConfig[];
  redes: EnlaceDeRed[];
  /** Ids de publicaciones propias a destacar. Sólo propias: ver el validador. */
  destacadas: string[];
};

export const LARGO_MAXIMO_DESCRIPCION = 1_000;
export const MAXIMO_DESTACADAS = 12;

/**
 * La configuración por defecto. Completa, no un esqueleto vacío.
 *
 * Los colores son los neutros de la identidad base, no los de marca: una
 * inmobiliaria que no eligió nada no debería aparecer con un color inventado
 * por nosotros que después parezca suyo.
 */
export const CONFIG_POR_DEFECTO: Readonly<MiniportalConfig> = Object.freeze({
  plantilla: "CLASICA" as Plantilla,
  tokens: Object.freeze({ primario: "#2f5d50", fondo: "#ffffff", texto: "#1a1a1a" }),
  logoUrl: null,
  coverUrl: null,
  avatarUrl: null,
  descripcion: null,
  secciones: Object.freeze([
    { id: "HERO", visible: true },
    { id: "PROPIEDADES_DESTACADAS", visible: false },
    { id: "PROPIEDADES", visible: true },
    { id: "SOBRE_NOSOTROS", visible: false },
    { id: "EQUIPO", visible: false },
    { id: "SUCURSALES", visible: false },
    { id: "CONTACTO", visible: true },
  ]) as unknown as SeccionConfig[],
  redes: Object.freeze([]) as unknown as EnlaceDeRed[],
  destacadas: Object.freeze([]) as unknown as string[],
});

const esObjeto = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function normalizarRedes(v: unknown): EnlaceDeRed[] {
  if (!Array.isArray(v)) return [];
  const vistas = new Set<Red>();
  const out: EnlaceDeRed[] = [];

  for (const item of v) {
    if (!esObjeto(item)) continue;
    const red = item.red;
    if (typeof red !== "string" || !(REDES as readonly string[]).includes(red)) continue;
    if (vistas.has(red as Red)) continue;

    const url = safeExternalUrl(item.url);
    if (!url) continue;

    // El enlace tiene que apuntar realmente a esa red. Sin esta comprobación,
    // "instagram" podría llevar a cualquier lado bajo el ícono de Instagram.
    let host: string;
    try {
      host = new URL(url).hostname.replace(/^www\./, "").toLowerCase();
    } catch {
      continue;
    }
    const permitidos = HOSTS_DE_RED[red as Red];
    if (!permitidos.some((h) => host === h || host.endsWith(`.${h}`))) continue;

    vistas.add(red as Red);
    out.push({ red: red as Red, url });
  }
  return out;
}

function normalizarSecciones(v: unknown): SeccionConfig[] {
  const pedidas = Array.isArray(v) ? v : [];
  const out: SeccionConfig[] = [];
  const vistas = new Set<SeccionId>();

  for (const item of pedidas) {
    if (!esObjeto(item)) continue;
    const id = item.id;
    if (typeof id !== "string" || !(SECCIONES as readonly string[]).includes(id)) continue;
    if (vistas.has(id as SeccionId)) continue;
    vistas.add(id as SeccionId);
    // Las obligatorias se fuerzan visibles aunque la config diga lo contrario.
    const obligatoria = SECCIONES_OBLIGATORIAS.includes(id as SeccionId);
    out.push({ id: id as SeccionId, visible: obligatoria ? true : item.visible === true });
  }

  // Se completan las que falten, con el valor por defecto y al final: así una
  // config vieja no pierde secciones nuevas ni queda incompleta.
  for (const def of CONFIG_POR_DEFECTO.secciones) {
    if (!vistas.has(def.id)) out.push({ ...def });
  }
  return out;
}

function normalizarTokens(v: unknown): TokensDeDiseno {
  const base = CONFIG_POR_DEFECTO.tokens;
  if (!esObjeto(v)) return { ...base };

  const tomar = (k: keyof TokensDeDiseno) => (esColorValido(v[k]) ? (v[k] as string) : base[k]);
  const tokens: TokensDeDiseno = {
    primario: tomar("primario"),
    fondo: tomar("fondo"),
    texto: tomar("texto"),
  };

  // Si la combinación elegida es ilegible se vuelve al texto por defecto. Se
  // prefiere una página legible con un color menos a una ilegible con todos.
  if (!contrasteSuficiente(tokens.texto, tokens.fondo)) {
    tokens.texto = base.texto;
    if (!contrasteSuficiente(tokens.texto, tokens.fondo)) tokens.fondo = base.fondo;
  }
  return tokens;
}

/**
 * Convierte cualquier entrada en una configuración completa y segura.
 *
 * Nunca falla y nunca devuelve null. Descarta en silencio lo que no valida,
 * porque el objetivo es que la página se vea bien: si una URL de logo es
 * inválida, la página va sin logo, no rota.
 *
 * Para saber QUÉ se descartó y avisarle a quien configuró, `validarConfig`.
 */
export function normalizarConfig(entrada: unknown): MiniportalConfig {
  const v = esObjeto(entrada) ? entrada : {};

  const plantilla =
    typeof v.plantilla === "string" && (PLANTILLAS as readonly string[]).includes(v.plantilla)
      ? (v.plantilla as Plantilla)
      : CONFIG_POR_DEFECTO.plantilla;

  const descripcion =
    typeof v.descripcion === "string" && v.descripcion.trim()
      ? v.descripcion.trim().slice(0, LARGO_MAXIMO_DESCRIPCION)
      : null;

  const destacadas = Array.isArray(v.destacadas)
    ? [...new Set(v.destacadas.filter((x): x is string => typeof x === "string" && /^[\w.:-]{1,128}$/.test(x)))]
        .slice(0, MAXIMO_DESTACADAS)
    : [];

  return {
    plantilla,
    tokens: normalizarTokens(v.tokens),
    logoUrl: safeExternalUrl(v.logoUrl),
    coverUrl: safeExternalUrl(v.coverUrl),
    avatarUrl: safeExternalUrl(v.avatarUrl),
    descripcion,
    secciones: normalizarSecciones(v.secciones),
    redes: normalizarRedes(v.redes),
    destacadas,
  };
}

// --- validación ------------------------------------------------------------

export type ProblemaDeConfig = {
  campo: string;
  code: string;
  mensaje: string;
};

/**
 * Qué tiene de malo la configuración que alguien envió.
 *
 * Separado de `normalizarConfig` porque son dos momentos: normalizar es para
 * RENDERIZAR y no puede fallar nunca; validar es para GUARDAR y tiene que
 * poder decir que no. Si fueran lo mismo, o la página se rompe o el editor
 * acepta cualquier cosa en silencio.
 */
export function validarConfig(entrada: unknown): ProblemaDeConfig[] {
  const problemas: ProblemaDeConfig[] = [];
  const v = esObjeto(entrada) ? entrada : {};
  const p = (campo: string, code: string, mensaje: string) => problemas.push({ campo, code, mensaje });

  if (v.plantilla !== undefined && !(PLANTILLAS as readonly string[]).includes(String(v.plantilla))) {
    p("plantilla", "DESCONOCIDA", "Esa plantilla no existe");
  }

  if (esObjeto(v.tokens)) {
    for (const k of ["primario", "fondo", "texto"] as const) {
      const c = v.tokens[k];
      if (c !== undefined && !esColorValido(c)) {
        p(`tokens.${k}`, "COLOR_INVALIDO", "Los colores se indican como #rrggbb");
      }
    }
    const t = v.tokens.texto;
    const f = v.tokens.fondo;
    if (esColorValido(t) && esColorValido(f) && !contrasteSuficiente(t, f)) {
      p("tokens.texto", "CONTRASTE_INSUFICIENTE", "Ese texto sobre ese fondo no se puede leer");
    }
  }

  for (const k of ["logoUrl", "coverUrl", "avatarUrl"] as const) {
    if (v[k] !== undefined && v[k] !== null && !safeExternalUrl(v[k])) {
      p(k, "URL_INVALIDA", "La dirección tiene que ser http o https");
    }
  }

  if (typeof v.descripcion === "string" && v.descripcion.length > LARGO_MAXIMO_DESCRIPCION) {
    p("descripcion", "MUY_LARGA", `Máximo ${LARGO_MAXIMO_DESCRIPCION} caracteres`);
  }

  if (Array.isArray(v.redes)) {
    const normalizadas = normalizarRedes(v.redes);
    if (normalizadas.length < v.redes.length) {
      p("redes", "ENLACE_NO_COINCIDE", "Algún enlace no apunta a la red que dice");
    }
  }

  if (Array.isArray(v.destacadas) && v.destacadas.length > MAXIMO_DESTACADAS) {
    p("destacadas", "DEMASIADAS", `Se pueden destacar hasta ${MAXIMO_DESTACADAS}`);
  }

  return problemas;
}

/**
 * Las destacadas tienen que ser publicaciones de la propia organización.
 *
 * Se verifica aparte porque necesita saber cuáles son suyas, y eso viene de la
 * base. Sin esta comprobación, una inmobiliaria podría destacar en su portal
 * las propiedades de otra.
 */
export function destacadasAjenas(
  destacadas: readonly string[],
  propias: ReadonlySet<string>,
): string[] {
  return destacadas.filter((id) => !propias.has(id));
}

/** Secciones visibles, en orden. Lo que la página recorre para renderizar. */
export function seccionesVisibles(config: MiniportalConfig): SeccionId[] {
  return config.secciones.filter((s) => s.visible).map((s) => s.id);
}
