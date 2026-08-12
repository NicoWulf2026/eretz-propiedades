import type { SearchParams } from "@/lib/property-query";

// Interpretación de lenguaje natural → filtros ESTRUCTURADOS de ERETZ.
//
// Principio anti-Roomix (secciones 12/13 del brief): NUNCA inventa filtros. Sólo
// setea un parámetro cuando el término aparece explícitamente. La operación no se
// asume por defecto. Los términos que no mapean a un filtro con respaldo de datos
// (p. ej. amenities como "balcón", que hoy son ~100% NULL) se devuelven en
// `notInterpreted` para mostrarlos como "no interpretado", en vez de inventar.

export type InterpretedChip = { field: string; label: string };
export type NlResult = {
  params: SearchParams;
  interpreted: InterpretedChip[];
  notInterpreted: string[];
  original: string;
};

const norm = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Operación: sólo si es explícita.
const OPERATION_WORDS: Array<[RegExp, string, string]> = [
  [/\b(comprar|compra|venta|vender|en venta)\b/, "venta", "Venta"],
  [/\b(alquiler temporal|temporario|temporal)\b/, "temporario", "Alquiler temporal"],
  [/\b(alquilar|alquiler|renta|rentar)\b/, "alquiler", "Alquiler"],
];

const TYPE_WORDS: Array<[RegExp, string, string]> = [
  [/\b(departamento|departamentos|depto|dpto|depa)\b/, "departamento", "Departamento"],
  [/\b(casas?|chalet)\b/, "casa", "Casa"],
  [/\bph\b/, "ph", "PH"],
  [/\b(terrenos?|lotes?)\b/, "terreno", "Terreno"],
  [/\b(oficinas?)\b/, "oficina", "Oficina"],
  [/\b(locales?)\b/, "local", "Local"],
  [/\b(cocheras?|garages?)\b/, "cochera", "Cochera"],
  [/\b(galpones?|galpon|dep[oó]sitos?)\b/, "galpon", "Galpón"],
  [/\b(campos?|chacras?)\b/, "campo", "Campo"],
];

const CURRENCY_WORDS: Array<[RegExp, string, string]> = [
  [/\b(usd|u\$s|d[oó]lares?|d[oó]lar)\b/, "USD", "USD"],
  [/\b(ars|pesos?|\$)\b/, "ARS", "ARS"],
];

// Amenities/atributos SIN filtro con respaldo de datos hoy → se listan como no
// interpretados (transparencia), nunca se inventan como filtro.
const KNOWN_UNBACKED = /\b(balc[oó]n|pileta|piscina|patio|parrilla|terraza|quincho|luminoso|amoblado|cochera|garage)\b/g;

// Convierte "200000", "200.000", "200 mil", "200k", "1,5 millones", "1.2m".
function parseAmount(raw: string): number | null {
  const t = norm(raw).trim();
  let mult = 1;
  if (/\b(millones?|m)\b/.test(t) || /\dm\b/.test(t)) mult = 1_000_000;
  else if (/\b(mil|k)\b/.test(t) || /\dk\b/.test(t)) mult = 1_000;
  const numMatch = t.replace(/\.(?=\d{3}\b)/g, "").replace(",", ".").match(/\d+(\.\d+)?/);
  if (!numMatch) return null;
  const n = Number(numMatch[0]) * mult;
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

// Detecta rangos de precio explícitos. Devuelve {min,max}.
function parsePrice(text: string): { min: number | null; max: number | null } {
  const t = norm(text);
  let min: number | null = null;
  let max: number | null = null;
  const between = t.match(/entre\s+([\d.,]+\s*(?:millones?|mil|k|m)?)\s+y\s+([\d.,]+\s*(?:millones?|mil|k|m)?)/);
  if (between) {
    min = parseAmount(between[1]);
    max = parseAmount(between[2]);
    return { min, max };
  }
  const maxM = t.match(/(?:hasta|m[aá]ximo|menos de|no m[aá]s de|por debajo de)\s+([\d.,]+\s*(?:millones?|mil|k|m)?)/);
  if (maxM) max = parseAmount(maxM[1]);
  const minM = t.match(/(?:desde|m[ií]nimo|m[aá]s de|por encima de)\s+([\d.,]+\s*(?:millones?|mil|k|m)?)/);
  if (minM) min = parseAmount(minM[1]);
  return { min, max };
}

// Extrae ubicaciones tras "en", separadas por "o"/"y"/",". OR entre ubicaciones.
function parseLocations(text: string): string[] {
  const t = text.replace(/\s+/g, " ");
  const out: string[] = [];
  const seen = new Set<string>();
  // toma segmentos "en X [o|y|, X2 ...]" hasta un conector de otro filtro
  const re = /\ben\s+([a-zA-ZñÑáéíóúÁÉÍÓÚ .,'-]+?)(?=\s+(?:hasta|desde|entre|con|sin|de\s+\d|por|para|venta|vender|comprar|compra|alquil\w*|temporal|\d)|$)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(t))) {
    const chunk = m[1];
    for (const piece of chunk.split(/\s+o\s+|\s+y\s+|,\s*/)) {
      const clean = piece.replace(/[(),.*%]/g, " ").replace(/\s+/g, " ").trim();
      const key = norm(clean);
      // descarta tokens que son claramente tipo/operación/moneda
      if (!clean || clean.length < 2 || seen.has(key)) continue;
      if (/^(venta|alquiler|comprar|alquilar|departamento|casa|ph|usd|ars|pesos|dolares)$/.test(key)) continue;
      seen.add(key);
      out.push(clean.replace(/\b\w/g, (c) => c.toUpperCase()));
      if (out.length >= 10) break;
    }
    if (out.length >= 10) break;
  }
  return out;
}

function firstInt(text: string, re: RegExp): number | null {
  const m = norm(text).match(re);
  if (!m) return null;
  const n = Number(m[1]);
  return Number.isFinite(n) && n > 0 && n <= 30 ? n : null;
}

export function interpretNaturalQuery(input: string): NlResult {
  const original = (input ?? "").slice(0, 200);
  const t = norm(original);
  const params: SearchParams = {};
  const interpreted: InterpretedChip[] = [];

  // Operación (sólo explícita)
  for (const [re, value, label] of OPERATION_WORDS) {
    if (re.test(t)) { params.operacion = value; interpreted.push({ field: "operacion", label }); break; }
  }
  // Tipo
  for (const [re, value, label] of TYPE_WORDS) {
    if (re.test(t)) { params.tipo = value; interpreted.push({ field: "tipo", label }); break; }
  }
  // Moneda
  for (const [re, value, label] of CURRENCY_WORDS) {
    if (re.test(t)) { params.moneda = value; interpreted.push({ field: "moneda", label: `Moneda ${label}` }); break; }
  }
  // Precio
  const price = parsePrice(original);
  if (price.min != null) { params.precio_min = String(price.min); interpreted.push({ field: "precio_min", label: `Desde ${price.min.toLocaleString("es-AR")}` }); }
  if (price.max != null) { params.precio_max = String(price.max); interpreted.push({ field: "precio_max", label: `Hasta ${price.max.toLocaleString("es-AR")}` }); }

  // Ambientes / dormitorios / baños (con respaldo de datos)
  const amb = firstInt(original, /(\d+)\s*(?:ambientes?|amb\b)/);
  if (amb != null) { params.ambientes = String(amb); interpreted.push({ field: "ambientes", label: `${amb}+ ambientes` }); }
  const dorm = firstInt(original, /(\d+)\s*(?:dormitorios?|dorm\b|habitaciones?)/);
  if (dorm != null) { params.dormitorios = String(dorm); interpreted.push({ field: "dormitorios", label: `${dorm}+ dormitorios` }); }
  const ban = firstInt(original, /(\d+)\s*(?:ba[ñn]os?)/);
  if (ban != null) { params.banos = String(ban); interpreted.push({ field: "banos", label: `${ban}+ baños` }); }

  // Ubicaciones (OR)
  const locations = parseLocations(original);
  if (locations.length) {
    params.ubicaciones = locations.join(",");
    interpreted.push({ field: "ubicaciones", label: locations.join(" o ") });
  }

  // Términos conocidos SIN filtro con respaldo → no interpretados (no se inventan)
  const notInterpreted = [...new Set((t.match(KNOWN_UNBACKED) || []))];

  return { params, interpreted, notInterpreted, original };
}
