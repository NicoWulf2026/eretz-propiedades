export type PropertyOperation =
  | "venta"
  | "alquiler"
  | "temporario"
  | "consultar"
  | "venta_y_alquiler";

export type PropertyType =
  | "departamento"
  | "casa"
  | "ph"
  | "terreno"
  | "oficina"
  | "local"
  | "cochera"
  | "galpon"
  | "campo"
  | "otro";

// El Quality Gate es la autoridad de visibilidad; `estado` refleja el estado real
// de scraping y se preserva. Sólo "activa" es disponibilidad confirmada; el resto
// se muestra como "Disponibilidad no confirmada" y ordena por debajo de las activas.
export type PropertyStatus = "activa" | "no_detectada_en_ultimo_scraping" | "desconocida";
export type PropertyCurrency = "USD" | "ARS" | "EUR" | "UYU";
export type PropertySort =
  | "relevance"
  | "recent"
  | "price_asc"
  | "price_desc"
  | "area_desc"
  | "rooms_desc"
  | "price_m2_asc"
  | "nearest";

// Control ternario NULL-safe: "" = Cualquiera (no filtra), "si" = verdadero,
// "no" = falso explícito, "sininfo" = dato ausente (NULL). NULL nunca es "no".
export type TriState = "" | "si" | "no" | "sininfo";

// Precio: "" = todas (nunca excluye "consultar"), "with" = con precio publicado,
// "consult" = a consultar (sin precio).
export type PriceMode = "" | "with" | "consult";

export type GeoPoint = { lat: number; lng: number };
export type LocationConfidence = "high" | "approximate" | "doubtful" | "none";

// Zonas de búsqueda dibujadas en el mapa. OR entre zonas, AND con el resto.
// (Polígono libre se difiere: requiere PostGIS point-in-polygon validado contra
// la base viva; rectángulo y radio son aritmética lat/lng pura, testeable.)
export type MapZone =
  | { kind: "box"; north: number; east: number; south: number; west: number }
  | { kind: "radius"; lat: number; lng: number; km: number };

export type ExplorerMode = "balanced" | "map_only" | "results_only";

export type PropertyPublisher = {
  id: string | null;
  name: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  verified: boolean | null;
};

export type ContactData = Pick<PropertyPublisher, "name" | "phone" | "email" | "website">;

export type MapViewport = {
  north: number;
  east: number;
  south: number;
  west: number;
  zoom: number;
};

export type MapMarker = {
  kind: "property";
  id: string;
  latitude: number;
  longitude: number;
  price: number | null;
  currency: PropertyCurrency | null;
  propertyType: PropertyType;
  title: string;
  location: string;
  locationConfidence: Exclude<LocationConfidence, "none">;
};

export type MapCluster = {
  kind: "cluster";
  id: string;
  latitude: number;
  longitude: number;
  count: number;
};

export type MapSearchResponse = {
  points: Array<MapMarker | MapCluster>;
  visibleCount: number;
  scannedCount: number;
  truncated: boolean;
};

export type SearchSuggestion = {
  id: string;
  label: string;
  category: "id" | "provincia" | "ciudad" | "barrio" | "dirección" | "inmobiliaria" | "agente" | "tipo";
  query: string;
  // Contexto geográfico o semántico derivado de la misma fila. No se fabrican
  // conteos: el endpoint sólo lo informa cuando dispone de un dato fiable.
  context?: string;
  count?: number;
  // Navegación directa (p. ej. una coincidencia por ID ERETZ va a la ficha en
  // lugar de rellenar el término de búsqueda).
  href?: string;
};

export type QualitySignals = {
  hasValidTitle: boolean;
  hasDescription: boolean;
  hasPrice: boolean;
  hasCurrency: boolean;
  hasLocation: boolean;
  hasCoordinates: boolean;
  hasImages: boolean;
};

export type SupabaseProperty = {
  id: string | number;
  inmobiliaria_id: string | number | null;
  url: string | null;
  titulo: string | null;
  descripcion: string | null;
  precio: number | null;
  moneda: string | null;
  precio_usd: number | null;
  precio_ars: number | null;
  expensas: number | null;
  expensas_moneda: string | null;
  tipo_propiedad: string | null;
  operacion: string | null;
  ambientes: number | null;
  dormitorios: number | null;
  banos: number | null;
  toilettes: number | null;
  cocheras: number | null;
  antiguedad: number | null;
  piso: number | string | null;
  superficie_total: number | null;
  superficie_cubierta: number | null;
  superficie_terreno: number | null;
  direccion: string | null;
  barrio: string | null;
  ciudad: string | null;
  provincia: string | null;
  pais: string | null;
  latitud: number | null;
  longitud: number | null;
  imagenes: string[] | null;
  video_url: string | null;
  plano_url: string | null;
  amenities: string[] | null;
  agente_nombre: string | null;
  agente_telefono: string | null;
  fuente_extraccion: string | null;
  cms_origen: string | null;
  fecha_publicacion: string | null;
  estado: string | null;
  created_at: string | null;
  updated_at: string | null;
  apto_credito: boolean | null;
  publisher_name?: string | null;
  publisher_phone?: string | null;
  publisher_email?: string | null;
  publisher_website?: string | null;
  publisher_verified?: boolean | null;
};

export type Property = {
  id: string;
  agencyId: string | null;
  publisher: PropertyPublisher | null;
  sourceUrl: string | null;
  title: string;
  description: string | null;
  price: number | null;
  currency: PropertyCurrency | null;
  priceUsd: number | null;
  priceArs: number | null;
  expenses: number | null;
  expensesCurrency: PropertyCurrency | null;
  propertyType: PropertyType;
  rawPropertyType: string | null;
  operation: PropertyOperation;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  toilettes: number | null;
  garages: number | null;
  age: number | null;
  floor: number | null;
  totalArea: number | null;
  coveredArea: number | null;
  landArea: number | null;
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  locationConfidence: LocationConfidence;
  images: string[];
  videoUrl: string | null;
  floorPlanUrl: string | null;
  amenities: string[];
  agentName: string | null;
  agentPhone: string | null;
  publishedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  status: PropertyStatus;
  mortgageEligible: boolean;
  quality: QualitySignals;
};

export type PropertyFilters = {
  q: string;
  operation: "" | PropertyOperation;
  propertyType: "" | PropertyType;
  province: string;
  city: string;
  neighborhood: string;
  locations: string[];
  zones: MapZone[];
  minPrice: number | null;
  maxPrice: number | null;
  currency: "" | PropertyCurrency;
  minRooms: number | null;
  minBedrooms: number | null;
  minBathrooms: number | null;
  minGarages: number | null;
  minArea: number | null;
  maxArea: number | null;
  minCoveredArea: number | null;
  minLandArea: number | null;
  maxExpenses: number | null;
  maxAge: number | null;
  publisher: string;
  recentDays: number | null;
  hasImages: boolean;
  priceMode: PriceMode;
  hasLocation: boolean;
  hasVideo: boolean;
  hasFloorPlan: boolean;
  mortgageState: TriState;
  sort: PropertySort;
  near: GeoPoint | null;
  page: number;
  cursor: string;
  direction: "next" | "prev";
  mode: ExplorerMode;
  viewport: MapViewport | null;
  selectedId: string;
};

export type PropertySearchResult = {
  properties: PropertySummary[];
  count: number | null;
  totalCount: number | null;
  mapCount: number | null;
  page: number;
  pageSize: number;
  hasNext: boolean;
  hasPrevious: boolean;
  nextCursor: string | null;
  previousCursor: string | null;
  source: "database" | "fixture" | "unconfigured" | "error";
  error: boolean;
  invalidCursor: boolean;
};

export type PropertySummary = Pick<
  Property,
  | "id" | "agencyId" | "publisher" | "title" | "price" | "currency"
  | "propertyType" | "rawPropertyType" | "operation" | "rooms" | "bedrooms"
  | "bathrooms" | "garages" | "totalArea" | "coveredArea" | "address"
  | "neighborhood" | "city" | "province" | "country" | "latitude" | "longitude"
  | "locationConfidence"
  | "images" | "publishedAt" | "updatedAt" | "status" | "mortgageEligible"
  | "description" | "amenities"
>;
export type RealEstateSummary = {
  id: string;
  name: string;
  slug: string;
  verified: boolean;
  website: string | null;
  city: string | null;
  province: string | null;
  listingsCount: number;
};

export type RealEstateProfile = RealEstateSummary & {
  phone: string | null;
  email: string | null;
};

export type ClaimStatus = "pending" | "approved" | "rejected" | "needs_review";

export type AgentSummary = {
  slug: string;
  name: string;
  city: string | null;
  province: string | null;
  listingsCount: number;
};

export type AgentProfile = AgentSummary & {
  phone: string | null;
};

export type PropertyDetail = Property;
export type RelatedProperty = PropertySummary;
export type SearchFilters = PropertyFilters;
export type SearchCursor = string;
export type SearchResponse = PropertySearchResult;
export type PropertyLocation = Pick<
  Property,
  "address" | "neighborhood" | "city" | "province" | "country" | "latitude" | "longitude"
>;
