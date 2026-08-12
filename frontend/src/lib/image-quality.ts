// Clasificación de imágenes que no representan la propiedad.
//
// Puerto del detector de ingesta (scraper/scraper_propiedades.py). Existe acá
// porque el histórico ya almacenado nunca pasó por el detector: sin esta capa,
// el read-model entregaría al frontend recursos que no son fotos del aviso.
//
// La auditoría sobre el inventario mostró que el problema no son los logos:
// llegaron tiles de OpenStreetMap, marcadores de Google Maps, imágenes Open
// Graph del home, samples de theme, GIFs transparentes, "sinfoto", matrículas y
// avatares. Casi ninguno contiene la palabra "logo".
//
// El frontend no clasifica: consume `displayImages`, que se deriva acá.

export const IMAGE_CLASS_HIGH = "HIGH_CONFIDENCE_NON_PROPERTY_IMAGE" as const;
export const IMAGE_CLASS_POSSIBLE = "POSSIBLE_NON_PROPERTY_IMAGE" as const;
export const IMAGE_CLASS_VALID = "LIKELY_VALID_IMAGE" as const;

export type ImageClass =
  | typeof IMAGE_CLASS_HIGH
  | typeof IMAGE_CLASS_POSSIBLE
  | typeof IMAGE_CLASS_VALID;

export const IMAGE_DETECTOR_VERSION = "2026-08-12.1";

// Hosts que sirven interfaz de mapas: nunca son la foto de un aviso.
const UI_MAP_HOSTS = [
  "tile.osm.org", "tile.openstreetmap.org", "maps.gstatic.com",
  "ssl.gstatic.com", "maps.googleapis.com", "unpkg.com/leaflet",
];

// El nombre del archivo declara que no es una foto de la propiedad.
const SEMANTIC_MARKERS = [
  "sinfoto", "nofoto", "noimage", "sinimagen", "placeholder", "default",
  "sample", "dummy", "spacer", "blank", "transparent", "transparente",
  "pixel", "1x1", "avatar", "matricula", "logo", "isotipo", "imagotipo",
  "isologo", "favicon", "watermark", "oghome", "ogimage", "opengraph",
  "impressionheader", "spotlightpoi",
];

// Rutas de plantilla/CMS, no contenido cargado por el publicador.
const TEMPLATE_PATHS = [
  "/wp-content/themes/", "/wp-content/plugins/", "/static/src/img/",
  "/assets/og/", "/stthemeeditor/", "/themeeditor/", "/mapfiles/",
  "/includes/images/", "/admin/uploads/", "/slider/",
];

// Palabras del rubro: sin excluirlas, "Inmobiliaria Bessa" marcaría cualquier
// archivo que diga "inmobiliaria".
const GENERIC_PUBLISHER_WORDS = new Set([
  "inmobiliaria", "inmobiliarias", "propiedades", "negocios", "servicios",
  "bienes", "raices", "inmuebles", "desarrollos", "asociados", "grupo",
  "estudio", "consultora", "gestion",
]);

function normalizeToken(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

export function nonPropertyImageSignals(imageUrl: string, publisherName?: string | null): string[] {
  const raw = (imageUrl ?? "").trim();
  if (!raw) return ["empty_url"];

  let low = raw.toLowerCase();
  try { low = decodeURIComponent(low); } catch { /* URL mal codificada: se usa tal cual */ }

  const signals: string[] = [];

  // Plantilla de tiles sin resolver: no es una imagen concreta.
  if (/\{[szxy]\}/.test(low)) signals.push("unresolved_url_template");
  if (UI_MAP_HOSTS.some((h) => low.includes(h))) signals.push("map_ui_asset");

  const path = low.split("?")[0].split("#")[0];
  const filename = path.split("/").pop() ?? "";
  const stem = normalizeToken(filename.replace(/\.[a-z0-9]+$/, ""));

  if (SEMANTIC_MARKERS.some((m) => stem.includes(normalizeToken(m)))) {
    signals.push("semantic_marker");
  }
  if (TEMPLATE_PATHS.some((p) => low.includes(p))) signals.push("template_asset");
  if (/\.(svg|ico|gif)$/.test(path)) signals.push("non_photo_format");

  if (publisherName) {
    const parts = publisherName
      .split(/[^A-Za-zÁÉÍÓÚÑáéíóúñ]+/)
      .filter((p) => p.length >= 5 && !GENERIC_PUBLISHER_WORDS.has(normalizeToken(p)));
    if (parts.some((p) => normalizeToken(p) && stem.includes(normalizeToken(p)))) {
      signals.push("publisher_name_in_filename");
    }
  }
  // Firmas de exportación de logo.
  if (stem.includes("fondotransp") || stem.includes("transp")) {
    signals.push("declared_transparent_background");
  }
  if (/(blanc[oa]|negr[oa]|white|black)$/.test(stem)) signals.push("color_variant_marker");

  return signals;
}

export function classifyPropertyImage(
  imageUrl: string,
  publisherName?: string | null,
  repetitionScoped = 0,
): { imageClass: ImageClass; reasons: string[] } {
  const signals = nonPropertyImageSignals(imageUrl, publisherName);
  if (signals.includes("empty_url")) return { imageClass: IMAGE_CLASS_HIGH, reasons: ["empty_url"] };

  const strong = ["unresolved_url_template", "map_ui_asset", "template_asset", "non_photo_format"];
  const hasStrong = signals.some((s) => strong.includes(s));
  const hasSemantic = signals.includes("semantic_marker");
  // Nombre del publicador + firma de logo: evidencia suficiente por sí sola.
  const branding = signals.includes("publisher_name_in_filename")
    && (signals.includes("declared_transparent_background") || signals.includes("color_variant_marker"));

  if (hasStrong || hasSemantic || branding) return { imageClass: IMAGE_CLASS_HIGH, reasons: signals };

  const weak = signals.filter((s) => s === "publisher_name_in_filename"
    || s === "declared_transparent_background" || s === "color_variant_marker");
  if (weak.length && repetitionScoped >= 10) {
    return { imageClass: IMAGE_CLASS_HIGH, reasons: [...signals, "scoped_repetition"] };
  }
  if (weak.length) return { imageClass: IMAGE_CLASS_POSSIBLE, reasons: signals };

  // Repetir no invalida: la auditoría halló fotos legítimas compartidas entre
  // unidades de un mismo loteo.
  if (repetitionScoped >= 10) return { imageClass: IMAGE_CLASS_POSSIBLE, reasons: ["scoped_repetition"] };

  return { imageClass: IMAGE_CLASS_VALID, reasons: signals };
}

// Imágenes mostrables: se excluyen sólo las HIGH. POSSIBLE se conserva —
// ocultar por sospecha escondería fotos reales.
export function displayableImages(images: readonly string[], publisherName?: string | null): string[] {
  return images.filter((url) => classifyPropertyImage(url, publisherName).imageClass !== IMAGE_CLASS_HIGH);
}
