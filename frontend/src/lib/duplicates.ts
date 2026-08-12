// Detección de "misma propiedad física publicada varias veces".
//
// Principios (sección 8 del brief):
// - NO O(n²): se agrupan candidatos por una CLAVE DE BLOQUEO barata y sólo se
//   comparan pares dentro del mismo bloque.
// - Scoring con señales ponderadas y normalizadas por señales disponibles.
// - Confianza en tres niveles: HIGH_CONFIDENCE / POSSIBLE_MATCH / NO_MATCH.
// - Agrupar SÓLO con alta confianza; las publicaciones originales se conservan
//   siempre (el grupo es metadato reversible, no borra ni fusiona registros).
//
// Módulo puro (sin acceso a base) para poder testear el contrato.

export type DupCandidate = {
  id: string;
  operation: string;
  propertyType: string;
  city: string | null;
  neighborhood: string | null;
  address: string | null;
  price: number | null;
  currency: string | null;
  totalArea: number | null;
  latitude: number | null;
  longitude: number | null;
  title: string;
};

export type Confidence = "HIGH_CONFIDENCE" | "POSSIBLE_MATCH" | "NO_MATCH";

function norm(value: string | null | undefined): string {
  return (value ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

// Celda geográfica ~1 km (2 decimales). Agrupa duplicados con coordenadas casi
// iguales sin comparar toda la ciudad.
function geoCell(lat: number | null, lng: number | null): string {
  if (lat == null || lng == null) return "";
  return `${lat.toFixed(2)},${lng.toFixed(2)}`;
}

// Bucket de precio (evita bloques enormes cuando no hay coordenadas).
function priceCell(price: number | null): string {
  return price == null || price <= 0 ? "np" : String(Math.round(price / 5000));
}

// Clave de bloqueo: operación + tipo + ciudad + (celda geográfica | bucket de
// precio). Sólo se comparan candidatos con la misma clave.
export function blockingKey(p: DupCandidate): string {
  const locus = geoCell(p.latitude, p.longitude) || priceCell(p.price);
  return `${norm(p.operation)}|${norm(p.propertyType)}|${norm(p.city)}|${locus}`;
}

function ratioScore(a: number | null, b: number | null): number | null {
  if (a == null || b == null || a <= 0 || b <= 0) return null;
  return Math.min(a, b) / Math.max(a, b); // 1 = idénticos
}

function tokenJaccard(a: string, b: string): number | null {
  const sa = new Set(norm(a).split(" ").filter(Boolean));
  const sb = new Set(norm(b).split(" ").filter(Boolean));
  if (sa.size === 0 || sb.size === 0) return null;
  let inter = 0;
  for (const t of sa) if (sb.has(t)) inter += 1;
  return inter / (sa.size + sb.size - inter);
}

function geoScore(a: DupCandidate, b: DupCandidate): number | null {
  if (a.latitude == null || a.longitude == null || b.latitude == null || b.longitude == null) return null;
  // distancia aproximada en grados → metros (1° ~ 111 km). <50 m ≈ 1, >500 m ≈ 0.
  const dLat = (a.latitude - b.latitude) * 111_000;
  const dLng = (a.longitude - b.longitude) * 111_000 * Math.cos((a.latitude * Math.PI) / 180);
  const meters = Math.sqrt(dLat * dLat + dLng * dLng);
  if (meters <= 50) return 1;
  if (meters >= 500) return 0;
  return 1 - (meters - 50) / 450;
}

// Similitud 0..1 entre dos candidatos, normalizada por las señales disponibles.
export function scoreMatch(a: DupCandidate, b: DupCandidate): number {
  if (a.currency && b.currency && a.currency !== b.currency) {
    // precios en monedas distintas no se comparan; se anula la señal de precio.
  }
  const signals: Array<[number, number]> = []; // [peso, score]
  const price = a.currency && b.currency && a.currency !== b.currency ? null : ratioScore(a.price, b.price);
  if (price != null) signals.push([0.3, price]);
  const area = ratioScore(a.totalArea, b.totalArea);
  if (area != null) signals.push([0.2, area]);
  const addr = tokenJaccard(a.address ?? "", b.address ?? "");
  if (addr != null) signals.push([0.25, addr]);
  const geo = geoScore(a, b);
  if (geo != null) signals.push([0.25, geo]);
  const title = tokenJaccard(a.title, b.title);
  if (title != null) signals.push([0.15, title]);
  if (signals.length === 0) return 0;
  const totalWeight = signals.reduce((sum, [w]) => sum + w, 0);
  const weighted = signals.reduce((sum, [w, s]) => sum + w * s, 0);
  return weighted / totalWeight;
}

export function classify(score: number): Confidence {
  if (score >= 0.82) return "HIGH_CONFIDENCE";
  if (score >= 0.55) return "POSSIBLE_MATCH";
  return "NO_MATCH";
}

export type DupGroup = {
  key: string;
  ids: string[];
  confidence: "HIGH_CONFIDENCE";
};

// Agrupa por bloqueo y une con union-find los pares de ALTA confianza. Cada grupo
// conserva TODOS los ids (las publicaciones originales no se borran ni fusionan).
export function groupDuplicates(items: DupCandidate[]): DupGroup[] {
  const parent = new Map<string, string>();
  const find = (x: string): string => {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root) ?? root;
    let cur = x;
    while (parent.get(cur) !== root) { const next = parent.get(cur) ?? root; parent.set(cur, root); cur = next; }
    return root;
  };
  const union = (a: string, b: string) => { parent.set(find(a), find(b)); };
  for (const item of items) parent.set(item.id, item.id);

  const blocks = new Map<string, DupCandidate[]>();
  for (const item of items) {
    const key = blockingKey(item);
    (blocks.get(key) ?? blocks.set(key, []).get(key)!).push(item);
  }
  // Sólo se comparan pares dentro de cada bloque (no O(n²) global).
  for (const [, bucket] of blocks) {
    for (let i = 0; i < bucket.length; i += 1) {
      for (let j = i + 1; j < bucket.length; j += 1) {
        if (classify(scoreMatch(bucket[i], bucket[j])) === "HIGH_CONFIDENCE") union(bucket[i].id, bucket[j].id);
      }
    }
  }
  const groups = new Map<string, string[]>();
  for (const item of items) {
    const root = find(item.id);
    (groups.get(root) ?? groups.set(root, []).get(root)!).push(item.id);
  }
  return [...groups.entries()]
    .filter(([, ids]) => ids.length > 1)
    .map(([key, ids]) => ({ key, ids: ids.sort(), confidence: "HIGH_CONFIDENCE" as const }));
}
