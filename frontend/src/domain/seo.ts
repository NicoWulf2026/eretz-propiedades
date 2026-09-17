// Política de indexación y URLs canónicas.
//
// NADA DE ESTO SE ACTIVA. `app/robots.ts` devuelve `disallow: "/"` sin escape
// posible y `app/sitemap.ts` devuelve vacío; los dos siguen igual y sus tests
// también. Preview permanece NOINDEX/NOFOLLOW.
//
// Lo que se agrega es la política, testeable, para el día que haya producción.
//
// ---------------------------------------------------------------------------
// EL PROBLEMA DE LAS FACETAS
// ---------------------------------------------------------------------------
//
// El buscador tiene más de treinta parámetros. Cualquier combinación produce
// una URL distinta con, esencialmente, el mismo contenido reordenado. Dejar que
// se indexen todas genera cientos de miles de páginas casi idénticas: el
// presupuesto de rastreo se gasta en variantes de filtros en vez de en las
// fichas, y las páginas que sí importan quedan sin visitar.
//
// La regla, entonces: se indexa lo que tiene identidad propia —una ficha, una
// inmobiliaria, una ciudad— y no lo que es un estado de la interfaz.
//
// ---------------------------------------------------------------------------
// FAIL-CLOSED
// ---------------------------------------------------------------------------
//
// Una ruta desconocida NO es indexable. Es la misma lógica del Quality Gate: si
// la política fuera permisiva por defecto, agregar una ruta nueva la expondría
// a los buscadores sin que nadie lo decidiera. Al revés, el olvido se nota
// —falta tráfico— y se corrige.

/** Parámetros que NUNCA pertenecen a una URL canónica. */
export const PARAMS_NO_CANONICOS = Object.freeze([
  // Orden y paginación: mismo contenido, otra vista.
  "sort",
  "page",
  "cursor",
  "direction",
  // Estado del mapa y de la interfaz.
  "map",
  "viewport",
  "zoom",
  "mode",
  "selected",
  "selectedId",
  "zones",
  "near",
  // Campañas y seguimiento.
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "gclid",
  "fbclid",
  "ref",
]);

export const TIPOS_DE_PAGINA = [
  "HOME",
  "LISTING_DETAIL",
  "ORGANIZATION_PROFILE",
  "AGENT_PROFILE",
  "CITY_LANDING",
  "NEIGHBORHOOD_LANDING",
  "SEARCH_RESULTS",
  "MAP",
  "MY_ERETZ",
  "COMPARE",
  "ADMIN",
  "ACCOUNT",
  "REPORT_FLOW",
  "LEGAL",
] as const;
export type TipoDePagina = (typeof TIPOS_DE_PAGINA)[number];

/**
 * Qué tipos de página podrían indexarse alguna vez.
 *
 * `SEARCH_RESULTS` no está: es el estado de un formulario, no un documento.
 * Las páginas de ciudad y barrio existen justamente para cubrir esa intención
 * de búsqueda con URLs curadas y estables.
 */
const INDEXABLES: readonly TipoDePagina[] = Object.freeze([
  "HOME",
  "LISTING_DETAIL",
  "ORGANIZATION_PROFILE",
  "AGENT_PROFILE",
  "CITY_LANDING",
  "NEIGHBORHOOD_LANDING",
  "LEGAL",
]);

export type ContextoDeIndexacion = {
  tipo: TipoDePagina;
  /** Falso en Preview. Hoy siempre falso. */
  produccion: boolean;
  /** La entidad pasa el Quality Gate. Sólo aplica a fichas. */
  elegible?: boolean;
  /** Tiene contenido propio suficiente para justificar una página. */
  contenidoSuficiente?: boolean;
  /** Para agentes: la persona reclamó el perfil. */
  reclamado?: boolean;
  /** Parámetros presentes en la URL. */
  params?: readonly string[];
};

export type VeredictoDeIndexacion = {
  indexable: boolean;
  motivo: string;
};

/**
 * ¿Se puede indexar esta página?
 *
 * Fail-closed en todos los caminos. El primer chequeo es producción: mientras
 * no lo sea, ninguna página se indexa por ningún motivo, y eso hace que la
 * política sea imposible de activar por accidente al agregar un tipo de página.
 */
export function esIndexable(c: ContextoDeIndexacion): VeredictoDeIndexacion {
  if (!c.produccion) {
    return { indexable: false, motivo: "no es producción: Preview es noindex sin excepciones" };
  }
  if (!(TIPOS_DE_PAGINA as readonly string[]).includes(c.tipo)) {
    return { indexable: false, motivo: "tipo de página desconocido" };
  }
  if (!INDEXABLES.includes(c.tipo)) {
    return { indexable: false, motivo: `${c.tipo} no es un documento con identidad propia` };
  }

  // Una URL con parámetros no canónicos es una variante, no la página. Se
  // indexa la canónica, no ésta.
  const sucios = (c.params ?? []).filter((p) => PARAMS_NO_CANONICOS.includes(p));
  if (sucios.length) {
    return { indexable: false, motivo: `tiene parámetros no canónicos: ${sucios.join(", ")}` };
  }

  if (c.tipo === "LISTING_DETAIL" && c.elegible !== true) {
    // Indexar lo que el Gate excluye contradiría al Gate desde afuera.
    return { indexable: false, motivo: "la publicación no pasa el Quality Gate" };
  }
  if (c.tipo === "AGENT_PROFILE" && c.reclamado !== true) {
    // Publicar en buscadores el perfil de una persona que no lo pidió.
    return { indexable: false, motivo: "el agente no reclamó su perfil" };
  }
  if (
    (c.tipo === "ORGANIZATION_PROFILE" ||
      c.tipo === "CITY_LANDING" ||
      c.tipo === "NEIGHBORHOOD_LANDING") &&
    c.contenidoSuficiente !== true
  ) {
    // Una página de ciudad con dos propiedades es contenido delgado: perjudica
    // al sitio entero, no sólo a esa página.
    return { indexable: false, motivo: "no tiene contenido propio suficiente" };
  }

  return { indexable: true, motivo: "documento con identidad propia y contenido" };
}

// --- URLs canónicas --------------------------------------------------------

/**
 * Quita de una URL todo lo que no la identifica.
 *
 * Ordena los parámetros que sobreviven: `?a=1&b=2` y `?b=2&a=1` son la misma
 * página, y si la canónica difiere según el orden en que se escribieron deja de
 * cumplir su función.
 *
 * También normaliza la barra final, salvo en la raíz.
 */
export function urlCanonica(url: string, base?: string): string {
  let u: URL;
  try {
    u = new URL(url, base);
  } catch {
    return url;
  }

  for (const p of PARAMS_NO_CANONICOS) u.searchParams.delete(p);

  const pares = [...u.searchParams.entries()].sort(
    ([a, av], [b, bv]) => a.localeCompare(b) || av.localeCompare(bv),
  );
  u.search = "";
  for (const [k, v] of pares) u.searchParams.append(k, v);

  if (u.pathname !== "/" && u.pathname.endsWith("/")) {
    u.pathname = u.pathname.replace(/\/+$/, "");
  }

  u.hash = "";
  return u.toString();
}

/** ¿Esta URL ya es su propia canónica? */
export function esCanonica(url: string, base?: string): boolean {
  return urlCanonica(url, base) === url;
}

// --- sitemap ---------------------------------------------------------------

export type EntradaDeSitemap = {
  url: string;
  lastModified: string | null;
};

export type CandidatoDeSitemap = ContextoDeIndexacion & { url: string; lastModified?: string | null };

/**
 * Construye las entradas del sitemap a partir de candidatos.
 *
 * Aplica exactamente `esIndexable`, para que no puedan divergir: un sitemap que
 * ofrece URLs que la página marca noindex es una contradicción que los
 * buscadores reportan y que nadie mira hasta que aparece en una consola.
 *
 * Deduplica por URL canónica: dos candidatos que canonizan igual son la misma
 * página y ofrecerla dos veces es un error de sitemap.
 *
 * Hoy devuelve vacío para todo, porque `produccion` es falso en todos lados.
 * Es la garantía de que preparar esto no activa nada.
 */
export function construirSitemap(candidatos: readonly CandidatoDeSitemap[]): EntradaDeSitemap[] {
  const porUrl = new Map<string, EntradaDeSitemap>();

  for (const c of candidatos) {
    if (!esIndexable(c).indexable) continue;
    const url = urlCanonica(c.url);
    if (porUrl.has(url)) continue;
    porUrl.set(url, { url, lastModified: c.lastModified ?? null });
  }

  return [...porUrl.values()].sort((a, b) => a.url.localeCompare(b.url));
}

/**
 * Directiva de robots para una página.
 *
 * `noindex, nofollow` para todo lo no indexable. `nofollow` además de `noindex`
 * en las páginas de resultados es deliberado: sin él, el rastreador igual
 * recorre los enlaces de facetas y gasta el presupuesto que se quería proteger.
 */
export function directivaRobots(c: ContextoDeIndexacion): string {
  return esIndexable(c).indexable ? "index, follow" : "noindex, nofollow";
}
