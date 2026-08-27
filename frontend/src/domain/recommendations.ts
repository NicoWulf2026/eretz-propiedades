// Propiedades relacionadas, con el porqué de cada una.
//
// ---------------------------------------------------------------------------
// QUÉ HABÍA Y QUÉ FALTA
// ---------------------------------------------------------------------------
//
// `getRelatedProperties` filtra por operación, tipo y PROVINCIA, y devuelve los
// primeros cuatro que llegan. Eso significa que a un departamento en Rosario le
// pueden aparecer como relacionados cuatro departamentos de una localidad a 300
// kilómetros, sin ninguna relación de precio ni de tamaño, y sin que la persona
// entienda por qué se los muestran.
//
// El filtro no está mal —acota bien el universo—; lo que falta es ORDENAR lo
// que quedó, y poder explicarlo.
//
// Este módulo es puro: recibe candidatos ya traídos y los puntúa. No consulta
// nada, así que no cambia cuántas filas se leen ni agrega latencia.
//
// ---------------------------------------------------------------------------
// NEUTRALIDAD DEL RANKING
// ---------------------------------------------------------------------------
//
// No existe `paidBoost`, ni `sponsoredWeight`, ni `commercialPriority`. No
// están comentados ni puestos en cero: no existen como concepto. La forma de
// que nadie los agregue por accidente es que no haya dónde ponerlos, y un test
// verifica que el tipo de entrada no tenga campos comerciales.
//
// Si alguna vez hay publicidad, va en un carril separado y rotulado, nunca
// mezclada en este puntaje.
//
// Tampoco hay personalización por comportamiento. Sin cuentas no hay a quién
// personalizarle nada, y hacerlo con el historial local convertiría una función
// de descubrimiento en una de seguimiento.

export type CandidatoRelacionado = {
  id: string;
  operation: string | null;
  propertyType: string | null;
  province: string | null;
  city: string | null;
  neighborhood: string | null;
  price: number | null;
  currency: string | null;
  bedrooms: number | null;
  rooms: number | null;
  totalArea: number | null;
};

/** Una razón legible de por qué se parece. */
export type RazonDeSimilitud = {
  code: string;
  label: string;
  /** Cuánto sumó al puntaje. */
  weight: number;
};

export type PropiedadRelacionada = {
  id: string;
  score: number;
  reasons: RazonDeSimilitud[];
};

/**
 * Pesos de cada señal. Suman 1 cuando todas coinciden en el nivel máximo.
 *
 * La ubicación pesa casi la mitad porque en inmuebles es lo primero que
 * descarta: nadie que busca en un barrio considera seriamente otro a veinte
 * cuadras sólo porque el precio coincide.
 */
export const PESOS_SIMILITUD = Object.freeze({
  ubicacion: 0.45,
  precio: 0.25,
  dormitorios: 0.15,
  superficie: 0.1,
  tipo: 0.05,
});

/** Diferencia relativa de precio a partir de la cual deja de parecerse. */
export const TOLERANCIA_PRECIO = 0.4;
/** Ídem superficie. */
export const TOLERANCIA_SUPERFICIE = 0.4;

const positivo = (n: number | null): n is number => n !== null && Number.isFinite(n) && n > 0;

const claveTexto = (v: string | null): string =>
  (v ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

/** Coinciden y ninguno es vacío. Dos ausencias no son una coincidencia. */
function coincideTexto(a: string | null, b: string | null): boolean {
  const ka = claveTexto(a);
  return ka !== "" && ka === claveTexto(b);
}

/**
 * Cercanía por texto de ubicación, de 0 a 1.
 *
 * Es texto y no geometría a propósito: sólo el 25,3% del catálogo tiene
 * coordenadas, así que un cálculo por distancia dejaría sin relacionadas a
 * tres de cada cuatro propiedades. Cuando haya geografía confiable, esta es la
 * función a reemplazar y el resto no cambia.
 */
function puntajeUbicacion(base: CandidatoRelacionado, otro: CandidatoRelacionado): [number, string] {
  if (coincideTexto(base.neighborhood, otro.neighborhood)) return [1, "el mismo barrio"];
  if (coincideTexto(base.city, otro.city)) return [0.6, "la misma ciudad"];
  if (coincideTexto(base.province, otro.province)) return [0.2, "la misma provincia"];
  return [0, ""];
}

/**
 * Cercanía numérica: 1 si son iguales, 0 si difieren más que la tolerancia.
 *
 * Se compara contra el valor de la propiedad base, no contra el promedio de
 * los dos: "20% más cara que ésta" es lo que le importa a quien mira ésta.
 */
function cercania(base: number, otro: number, tolerancia: number): number {
  const dif = Math.abs(otro - base) / base;
  return dif >= tolerancia ? 0 : 1 - dif / tolerancia;
}

/**
 * Puntúa un candidato contra la propiedad de referencia.
 *
 * Devuelve siempre las razones, aunque el puntaje sea bajo: sin ellas no se
 * puede mostrar "Similar porque…" ni depurar por qué apareció algo raro.
 */
export function puntuarSimilitud(
  base: CandidatoRelacionado,
  otro: CandidatoRelacionado,
): PropiedadRelacionada {
  const reasons: RazonDeSimilitud[] = [];
  let score = 0;

  const sumar = (code: string, label: string, fraccion: number, peso: number) => {
    if (fraccion <= 0) return;
    const weight = fraccion * peso;
    score += weight;
    reasons.push({ code, label, weight });
  };

  const [ubic, etiqueta] = puntajeUbicacion(base, otro);
  if (ubic > 0) sumar("UBICACION", etiqueta, ubic, PESOS_SIMILITUD.ubicacion);

  // El precio sólo se compara dentro de la misma moneda.
  if (positivo(base.price) && positivo(otro.price) && base.currency === otro.currency) {
    sumar("PRECIO", "precio similar", cercania(base.price, otro.price, TOLERANCIA_PRECIO), PESOS_SIMILITUD.precio);
  }

  if (positivo(base.bedrooms) && positivo(otro.bedrooms)) {
    const dif = Math.abs(otro.bedrooms - base.bedrooms);
    const fraccion = dif === 0 ? 1 : dif === 1 ? 0.5 : 0;
    const label = dif === 0 ? `${otro.bedrooms} dormitorios` : "cantidad de dormitorios parecida";
    sumar("DORMITORIOS", label, fraccion, PESOS_SIMILITUD.dormitorios);
  }

  if (positivo(base.totalArea) && positivo(otro.totalArea)) {
    sumar(
      "SUPERFICIE",
      "superficie parecida",
      cercania(base.totalArea, otro.totalArea, TOLERANCIA_SUPERFICIE),
      PESOS_SIMILITUD.superficie,
    );
  }

  if (coincideTexto(base.propertyType, otro.propertyType)) {
    sumar("TIPO", "el mismo tipo de propiedad", 1, PESOS_SIMILITUD.tipo);
  }

  reasons.sort((a, b) => b.weight - a.weight);
  return { id: otro.id, score, reasons };
}

/** Puntaje mínimo para mostrar algo como relacionado. */
export const PUNTAJE_MINIMO = 0.15;

/**
 * Ordena y recorta los candidatos.
 *
 * Excluye siempre la propia propiedad. Los empates se desempatan por id para
 * que el orden sea estable entre cargas: una lista que cambia de orden sola
 * confunde a quien vuelve.
 *
 * `minimo` es configurable por una razón concreta. Con el umbral puesto,
 * `recomendar` prefiere devolver menos —mostrar cuatro cosas sin relación es
 * peor que mostrar una sola que sí la tiene—. Pero el llamador actual filtra
 * antes por operación, tipo y provincia, y bajar de cuatro tarjetas a cero
 * haría desaparecer una sección de la ficha. Ese llamador pasa `minimo: 0` y se
 * queda sólo con la mejora de ORDEN, que es segura; subir el umbral es una
 * decisión de producto aparte, con la UI preparada para una sección vacía.
 */
export function recomendar(
  base: CandidatoRelacionado,
  candidatos: readonly CandidatoRelacionado[],
  { limite = 4, minimo = PUNTAJE_MINIMO }: { limite?: number; minimo?: number } = {},
): PropiedadRelacionada[] {
  return candidatos
    .filter((c) => c.id !== base.id)
    .map((c) => puntuarSimilitud(base, c))
    .filter((r) => r.score >= minimo)
    .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
    .slice(0, limite);
}

/** Texto de "Similar porque…" a partir de las razones. */
export function explicarSimilitud(r: PropiedadRelacionada, maximo = 2): string {
  if (!r.reasons.length) return "";
  return r.reasons.slice(0, maximo).map((x) => x.label).join(" · ");
}
