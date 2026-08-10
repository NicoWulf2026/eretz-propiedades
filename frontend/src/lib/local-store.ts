// Almacenamiento local por usuario/dispositivo (sin cuenta, sin backend) para
// ERETZ Functional v3: favoritos, vistas recientes, búsquedas recientes,
// propiedades ocultas y lista de comparación.
//
// - SSR-safe: en el servidor todas las lecturas devuelven vacío y las escrituras
//   son no-op (localStorage sólo existe en el browser).
// - Resiliente: JSON malformado o storage inaccesible nunca rompe la app.
// - Acotado: cada lista tiene un límite razonable para no crecer sin control.
// - Reactivo: cada mutación emite un evento para que los hooks re-lean.
// - Arquitectura preparada para que una cuenta futura pueda importar/sincronizar
//   estas listas (son datos planos, serializables y namespaced).

export const STORE_KEYS = {
  favorites: "eretz:favorites",
  recent: "eretz:recent",
  recentSearches: "eretz:recent-searches",
  hidden: "eretz:hidden",
  compare: "eretz:compare",
  visited: "eretz:visited",
  collections: "eretz:collections",
} as const;

export type StoreName = keyof typeof STORE_KEYS;

export const STORE_LIMITS: Record<StoreName, number> = {
  favorites: 500,
  recent: 40,
  recentSearches: 20,
  hidden: 1000,
  compare: 4,
  visited: 2000,
  collections: 100,
};

export const CHANGE_EVENT = "eretz:local-store-change";

export type RecentView = { id: string; title: string; price: string | null; at: number };
export type RecentSearch = { url: string; label: string; at: number };
export type Collection = { id: string; name: string; ids: string[]; at: number };

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function read<T>(key: string): T[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function write<T>(name: StoreName, value: T[]): void {
  if (!isBrowser()) return;
  try {
    const bounded = value.slice(0, STORE_LIMITS[name]);
    window.localStorage.setItem(STORE_KEYS[name], JSON.stringify(bounded));
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: name }));
  } catch {
    // Storage lleno o bloqueado: la función es best-effort, no rompe la UI.
  }
}

// ----------------------------------------------------------------- IDs simples
function idList(name: StoreName): string[] {
  return read<string>(STORE_KEYS[name]).map(String);
}

function toggleId(name: StoreName, id: string, max?: number): { active: boolean; list: string[] } {
  const key = String(id);
  const current = idList(name);
  let next: string[];
  let active: boolean;
  if (current.includes(key)) {
    next = current.filter((x) => x !== key);
    active = false;
  } else {
    // nuevos primero; respeta un tope opcional (ej. comparar = 4)
    next = [key, ...current];
    if (typeof max === "number") next = next.slice(0, max);
    active = next.includes(key);
  }
  write(name, next);
  return { active, list: next };
}

// ----------------------------------------------------------------- Favoritos
export const getFavorites = (): string[] => idList("favorites");
export const isFavorite = (id: string): boolean => idList("favorites").includes(String(id));
export const toggleFavorite = (id: string): boolean => toggleId("favorites", id).active;

// ----------------------------------------------------------------- Ocultas
export const getHidden = (): string[] => idList("hidden");
export const isHidden = (id: string): boolean => idList("hidden").includes(String(id));
export function hideProperty(id: string): void {
  const key = String(id);
  const current = idList("hidden");
  if (!current.includes(key)) write("hidden", [key, ...current]);
}
export function unhideProperty(id: string): void {
  write("hidden", idList("hidden").filter((x) => x !== String(id)));
}
export const clearHidden = (): void => write("hidden", []);

// ----------------------------------------------------------------- Comparar (2..4)
export const getCompare = (): string[] => idList("compare");
export const inCompare = (id: string): boolean => idList("compare").includes(String(id));
/** Alterna una propiedad en la comparación. Devuelve el estado y si estaba lleno. */
export function toggleCompare(id: string): { active: boolean; full: boolean; list: string[] } {
  const key = String(id);
  const current = idList("compare");
  if (current.includes(key)) {
    const list = current.filter((x) => x !== key);
    write("compare", list);
    return { active: false, full: false, list };
  }
  if (current.length >= STORE_LIMITS.compare) {
    return { active: false, full: true, list: current };
  }
  const list = [...current, key];
  write("compare", list);
  return { active: true, full: false, list };
}
export const clearCompare = (): void => write("compare", []);

// ----------------------------------------------------------------- Vistas recientes
export function addRecentView(v: { id: string; title: string; price: string | null }): void {
  const id = String(v.id);
  const current = read<RecentView>(STORE_KEYS.recent).filter((x) => String(x.id) !== id);
  write("recent", [{ id, title: v.title, price: v.price ?? null, at: Date.now() }, ...current]);
}
export const getRecentViews = (): RecentView[] => read<RecentView>(STORE_KEYS.recent);
export const clearRecentViews = (): void => write("recent", []);

// ----------------------------------------------------------------- Búsquedas recientes
export function addRecentSearch(s: { url: string; label: string }): void {
  const url = s.url.trim();
  if (!url) return;
  const current = read<RecentSearch>(STORE_KEYS.recentSearches).filter((x) => x.url !== url);
  write("recentSearches", [{ url, label: s.label || url, at: Date.now() }, ...current]);
}
export const getRecentSearches = (): RecentSearch[] => read<RecentSearch>(STORE_KEYS.recentSearches);
export const removeRecentSearch = (url: string): void =>
  write("recentSearches", read<RecentSearch>(STORE_KEYS.recentSearches).filter((x) => x.url !== url));
export const clearRecentSearches = (): void => write("recentSearches", []);

// ----------------------------------------------------------------- Visitadas
// Señal local de propiedades ya vistas (para atenuar/ocultar). No borra ni toca
// la base; sólo marca. Se registra al abrir la ficha.
export const getVisited = (): string[] => idList("visited");
export const isVisited = (id: string): boolean => idList("visited").includes(String(id));
export function markVisited(id: string): void {
  const key = String(id);
  const current = idList("visited").filter((x) => x !== key);
  write("visited", [key, ...current]);
}
export const clearVisited = (): void => write("visited", []);

// ----------------------------------------------------------------- Colecciones
// Colecciones nombrables locales (sin cuenta). Datos planos, preparados para
// sincronizar con una cuenta futura. No reemplaza a favoritos.
function slug(): string {
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}
export const getCollections = (): Collection[] => read<Collection>(STORE_KEYS.collections);
export function createCollection(name: string): Collection {
  const clean = (name || "Sin nombre").trim().slice(0, 60) || "Sin nombre";
  const collection: Collection = { id: slug(), name: clean, ids: [], at: Date.now() };
  write("collections", [collection, ...getCollections()]);
  return collection;
}
export function renameCollection(id: string, name: string): void {
  const clean = (name || "").trim().slice(0, 60);
  if (!clean) return;
  write("collections", getCollections().map((c) => (c.id === id ? { ...c, name: clean } : c)));
}
export const deleteCollection = (id: string): void =>
  write("collections", getCollections().filter((c) => c.id !== id));
export function addToCollection(collectionId: string, propertyId: string): void {
  const pid = String(propertyId);
  write("collections", getCollections().map((c) =>
    c.id === collectionId && !c.ids.includes(pid) ? { ...c, ids: [pid, ...c.ids] } : c));
}
export function removeFromCollection(collectionId: string, propertyId: string): void {
  const pid = String(propertyId);
  write("collections", getCollections().map((c) =>
    c.id === collectionId ? { ...c, ids: c.ids.filter((x) => x !== pid) } : c));
}
/** Ids de las colecciones que contienen una propiedad. */
export const collectionsWith = (propertyId: string): string[] =>
  getCollections().filter((c) => c.ids.includes(String(propertyId))).map((c) => c.id);
