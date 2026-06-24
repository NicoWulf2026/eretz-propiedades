export type PropertyOperation =
  | "venta"
  | "alquiler"
  | "inversion"
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
  | "otro";
export type PropertyStatus =
  | "activa"
  | "pausada"
  | "reservada"
  | "vendida"
  | "alquilada"
  | "desconocida"
  | "no_detectada_en_ultimo_scraping";
export type PropertyCurrency = "USD" | "ARS";

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
  piso: number | null;
  superficie_total: number | null;
  superficie_cubierta: number | null;
  superficie_terreno: number | null;
  direccion: string | null;
  barrio: string | null;
  // Campos directos de propiedades (query directa, Sprint F)
  ciudad: string | null;
  provincia: string | null;
  // Campos de la view (opcionales — presentes solo cuando se queryea v_propiedades_frontend_mapa)
  ciudad_original?: string | null;
  provincia_original?: string | null;
  ciudad_final?: string | null;
  provincia_final?: string | null;
  pais: string | null;
  latitud: number | null;
  longitud: number | null;
  imagenes: string[] | null;
  imagen_principal_real?: string | null;
  tiene_imagen_real?: boolean | null;
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
  inmobiliaria_nombre?: string | null;
  inmobiliaria_web?: string | null;
  inmobiliaria_telefono?: string | null;
  inmobiliaria_email?: string | null;
};

export type Property = {
  id: string;
  agencyId: string | null;
  sourceUrl: string;
  externalId: string | null;
  dedupHash: string | null;
  title: string;
  description: string;
  /**
   * Precio publicado original de la propiedad. Es el valor que debe mostrarse
   * como precio principal en la UI publica junto con `currency`.
   */
  price: number;
  /**
   * Moneda publicada original. No representa una preferencia de conversion.
   */
  currency: PropertyCurrency;
  /**
   * Valor normalizado a USD para analisis interno o modulos analiticos.
   * No debe mostrarse como precio principal en la busqueda publica.
   */
  priceUsd: number | null;
  /**
   * Valor normalizado a ARS para analisis interno o modulos analiticos.
   * No debe mostrarse como precio principal en la busqueda publica.
   */
  priceArs: number | null;
  expenses: number | null;
  expensesCurrency: PropertyCurrency | null;
  propertyType: PropertyType;
  operation: PropertyOperation;
  rooms: number;
  bedrooms: number;
  bathrooms: number;
  toilettes: number;
  garages: number;
  age: number | null;
  floor: number | null;
  totalArea: number;
  coveredArea: number;
  landArea: number | null;
  address: string;
  neighborhood: string;
  city: string;
  province: string;
  country: string;
  latitude: number | null;
  longitude: number | null;
  images: string[];
  hasRealImage: boolean;
  videoUrl: string | null;
  floorPlanUrl: string | null;
  amenities: string[];
  agencyName: string;
  agencyWeb: string | null;
  agencyPhone: string | null;
  agencyEmail: string | null;
  agentName: string | null;
  agentPhone: string | null;
  extractionSource: string | null;
  originCms: string | null;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  status: PropertyStatus;
  mortgageEligible: boolean;
  badges: string[];
};
