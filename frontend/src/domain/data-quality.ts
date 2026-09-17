// Análisis de calidad de una publicación: qué está mal, y por qué lo decimos.
//
// Módulo puro. NO corrige nada, y esa restricción es del encargo pero también
// es la decisión correcta: "corregir" un dato scrapeado es reemplazar lo que
// dice la fuente por lo que suponemos, y después nadie puede distinguir el dato
// real del inventado. Detectar y marcar conserva ambas cosas.
//
// ---------------------------------------------------------------------------
// DOS CLASES DE SEÑAL, Y UNA IMPORTA MUCHO MÁS QUE LA OTRA
// ---------------------------------------------------------------------------
//
// INCOHERENCIAS INTERNAS. La superficie cubierta es mayor que la total. Hay más
// dormitorios que ambientes. Son contradicciones aritméticas: no dependen de
// ninguna suposición sobre el mercado argentino, sobre inflación ni sobre la
// zona. Si el dato se contradice a sí mismo, está mal, y punto.
//
// VALORES ATÍPICOS. Un departamento de 12 m². Un precio de USD 300. Un
// edificio de 400 años. Acá NO afirmamos que esté mal: afirmamos que es raro.
// Un monoambiente de 12 m² existe; una casona de 1650 en Salta existe. Los
// umbrales son juicios sobre qué es lo bastante raro como para mirarlo, y por
// eso están todos juntos, con nombre, y son configurables.
//
// La consecuencia práctica: sólo las incoherencias internas y los imposibles
// duros producen INVALID. Todo lo atípico produce SUSPICIOUS, que significa
// "que lo mire alguien", no "está mal".

import { hasValidArgentinaCoordinates } from "@/lib/geo-confidence";

export const SEVERITIES = ["INFO", "SUSPICIOUS", "INVALID"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const QUALITY_VERDICTS = ["VALID", "SUSPICIOUS", "INVALID", "QUARANTINE"] as const;
export type QualityVerdict = (typeof QUALITY_VERDICTS)[number];

export type Anomaly = {
  /** Campo afectado. `null` cuando la anomalía es entre varios. */
  field: string | null;
  code: string;
  severity: Severity;
  /** Explicación en castellano, para una persona que revisa. */
  detail: string;
};

/**
 * Umbrales. Todos juntos y con nombre, porque son juicios discutibles y no
 * verdades: dispersos por el código serían números mágicos que nadie se anima
 * a tocar.
 */
export const UMBRALES = Object.freeze({
  /** Por debajo, un precio de venta en USD es probablemente un error de carga. */
  precioVentaUsdMinimo: 5_000,
  /** Por encima, conviene mirarlo. Existen, pero son poquísimos. */
  precioVentaUsdMaximo: 50_000_000,
  /** Un alquiler mensual en USD por encima de esto es raro. */
  precioAlquilerUsdMaximo: 20_000,
  superficieMinimaM2: 10,
  /** 10 hectáreas. Por encima, salvo campo, es raro. */
  superficieMaximaM2: 100_000,
  ambientesMaximo: 30,
  banosMaximo: 20,
  cocherasMaximo: 50,
  antiguedadMaxima: 300,
  /** Expensas por encima de esta fracción del alquiler: raro. */
  fraccionExpensasSobreAlquiler: 2,
});

export type PublicacionAnalizable = {
  title: string | null;
  description: string | null;
  operation: string | null;
  propertyType: string | null;
  price: number | null;
  currency: string | null;
  priceUsd: number | null;
  expenses: number | null;
  totalArea: number | null;
  coveredArea: number | null;
  landArea: number | null;
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  garages: number | null;
  age: number | null;
  latitude: number | null;
  longitude: number | null;
  city: string | null;
  province: string | null;
  images: readonly string[];
};

const positivo = (n: number | null): n is number => n !== null && Number.isFinite(n) && n > 0;
const presente = (n: number | null): n is number => n !== null && Number.isFinite(n);

// --- reglas ----------------------------------------------------------------

/**
 * Incoherencias internas: el dato se contradice a sí mismo.
 *
 * No dependen de ninguna suposición de mercado, así que producen INVALID sin
 * discusión.
 */
function incoherenciasInternas(p: PublicacionAnalizable): Anomaly[] {
  const a: Anomaly[] = [];

  if (positivo(p.coveredArea) && positivo(p.totalArea) && p.coveredArea > p.totalArea) {
    a.push({
      field: "coveredArea",
      code: "CUBIERTA_MAYOR_QUE_TOTAL",
      severity: "INVALID",
      detail: `superficie cubierta (${p.coveredArea}) mayor que la total (${p.totalArea})`,
    });
  }
  if (positivo(p.bedrooms) && positivo(p.rooms) && p.bedrooms > p.rooms) {
    a.push({
      field: "bedrooms",
      code: "DORMITORIOS_MAYOR_QUE_AMBIENTES",
      severity: "INVALID",
      detail: `${p.bedrooms} dormitorios en ${p.rooms} ambientes`,
    });
  }
  // Los negativos no son atípicos, son imposibles.
  for (const [campo, valor] of [
    ["price", p.price], ["totalArea", p.totalArea], ["coveredArea", p.coveredArea],
    ["landArea", p.landArea], ["rooms", p.rooms], ["bedrooms", p.bedrooms],
    ["bathrooms", p.bathrooms], ["garages", p.garages], ["age", p.age],
    ["expenses", p.expenses],
  ] as const) {
    if (presente(valor) && valor < 0) {
      a.push({
        field: campo,
        code: "VALOR_NEGATIVO",
        severity: "INVALID",
        detail: `${campo} vale ${valor}`,
      });
    }
  }
  return a;
}

/** Coordenadas fuera de la Argentina o mal formadas. */
function anomaliasDeUbicacion(p: PublicacionAnalizable): Anomaly[] {
  const a: Anomaly[] = [];
  const tieneAlguna = presente(p.latitude) || presente(p.longitude);
  if (!tieneAlguna) return a;

  // El (0,0) del Golfo de Guinea: el default clásico de un geocoder que falló.
  // Se reporta como caso propio y no como "fuera de rango" porque tiene una
  // causa conocida y accionable; emitir las dos sería la misma anomalía dos
  // veces y ensuciaría el conteo que decide la cuarentena.
  if (p.latitude === 0 && p.longitude === 0) {
    a.push({
      field: "latitude",
      code: "COORDENADAS_CERO",
      severity: "INVALID",
      detail: "coordenadas en (0,0), típico de un geocoding fallido",
    });
    return a;
  }

  if (!hasValidArgentinaCoordinates(p.latitude, p.longitude)) {
    a.push({
      field: "latitude",
      code: "COORDENADAS_FUERA_DE_RANGO",
      severity: "INVALID",
      detail: "las coordenadas no caen dentro de la Argentina",
    });
  }
  return a;
}

/**
 * Valores atípicos. Raros, no imposibles: todos SUSPICIOUS.
 *
 * El precio se evalúa en USD cuando se conoce, para no comparar pesos contra
 * dólares. Si no hay `priceUsd`, no se evalúa el rango: convertir con una
 * cotización inventada sería peor que no mirar.
 */
function valoresAtipicos(p: PublicacionAnalizable): Anomaly[] {
  const a: Anomaly[] = [];
  const esAlquiler = p.operation === "alquiler" || p.operation === "temporario";

  if (positivo(p.priceUsd)) {
    if (!esAlquiler && p.priceUsd < UMBRALES.precioVentaUsdMinimo) {
      a.push({
        field: "price",
        code: "PRECIO_VENTA_MUY_BAJO",
        severity: "SUSPICIOUS",
        detail: `USD ${p.priceUsd} para una venta`,
      });
    }
    if (!esAlquiler && p.priceUsd > UMBRALES.precioVentaUsdMaximo) {
      a.push({
        field: "price",
        code: "PRECIO_VENTA_MUY_ALTO",
        severity: "SUSPICIOUS",
        detail: `USD ${p.priceUsd} para una venta`,
      });
    }
    if (esAlquiler && p.priceUsd > UMBRALES.precioAlquilerUsdMaximo) {
      a.push({
        field: "price",
        code: "ALQUILER_MUY_ALTO",
        severity: "SUSPICIOUS",
        detail: `USD ${p.priceUsd} mensuales`,
      });
    }
  }

  // El terreno de un campo puede ser enorme legítimamente: se exceptúa.
  const esRural = p.propertyType === "campo";
  if (positivo(p.totalArea)) {
    if (p.totalArea < UMBRALES.superficieMinimaM2) {
      a.push({
        field: "totalArea",
        code: "SUPERFICIE_MUY_CHICA",
        severity: "SUSPICIOUS",
        detail: `${p.totalArea} m² totales`,
      });
    }
    if (!esRural && p.totalArea > UMBRALES.superficieMaximaM2) {
      a.push({
        field: "totalArea",
        code: "SUPERFICIE_MUY_GRANDE",
        severity: "SUSPICIOUS",
        detail: `${p.totalArea} m² para un ${p.propertyType ?? "inmueble"}`,
      });
    }
  }

  for (const [campo, valor, tope, code] of [
    ["rooms", p.rooms, UMBRALES.ambientesMaximo, "AMBIENTES_EXCESIVOS"],
    ["bathrooms", p.bathrooms, UMBRALES.banosMaximo, "BANOS_EXCESIVOS"],
    ["garages", p.garages, UMBRALES.cocherasMaximo, "COCHERAS_EXCESIVAS"],
    ["age", p.age, UMBRALES.antiguedadMaxima, "ANTIGUEDAD_EXCESIVA"],
  ] as const) {
    if (positivo(valor) && valor > tope) {
      a.push({ field: campo, code, severity: "SUSPICIOUS", detail: `${campo} = ${valor}` });
    }
  }

  if (esAlquiler && positivo(p.expenses) && positivo(p.price)) {
    if (p.expenses > p.price * UMBRALES.fraccionExpensasSobreAlquiler) {
      a.push({
        field: "expenses",
        code: "EXPENSAS_DESPROPORCIONADAS",
        severity: "SUSPICIOUS",
        detail: `expensas ${p.expenses} contra alquiler ${p.price}`,
      });
    }
  }

  return a;
}

/**
 * Un precio con moneda pero sin valor, o al revés.
 *
 * Se distingue del precio ausente: "a consultar" es legítimo y frecuente. Lo
 * raro es tener la mitad del dato.
 */
function coherenciaDePrecio(p: PublicacionAnalizable): Anomaly[] {
  const a: Anomaly[] = [];
  if (positivo(p.price) && !p.currency) {
    a.push({
      field: "currency",
      code: "PRECIO_SIN_MONEDA",
      severity: "SUSPICIOUS",
      detail: "hay precio pero no se sabe en qué moneda",
    });
  }
  // Un 0 explícito como precio no es "gratis": es un campo que se llenó mal.
  if (p.price === 0) {
    a.push({
      field: "price",
      code: "PRECIO_CERO",
      severity: "SUSPICIOUS",
      detail: "precio en 0, probablemente un campo sin completar",
    });
  }
  return a;
}

/**
 * Campos esenciales ausentes. Severidad INFO: no está MAL, está incompleto.
 *
 * Es una distinción que importa: una publicación sin fotos es peor que una con
 * fotos, pero no es un dato erróneo, y tratarla como inválida sacaría del
 * catálogo publicaciones perfectamente reales.
 */
function camposEsencialesAusentes(p: PublicacionAnalizable): Anomaly[] {
  const a: Anomaly[] = [];
  const falta = (campo: string, hay: boolean, detalle: string) => {
    if (!hay) a.push({ field: campo, code: "CAMPO_ESENCIAL_AUSENTE", severity: "INFO", detail: detalle });
  };

  falta("title", Boolean(p.title?.trim()), "sin título");
  falta("operation", Boolean(p.operation), "sin operación");
  falta("propertyType", Boolean(p.propertyType), "sin tipo de propiedad");
  falta("city", Boolean(p.city?.trim()), "sin ciudad");
  falta("images", p.images.length > 0, "sin imágenes");
  return a;
}

// --- veredicto -------------------------------------------------------------

export type QualityReport = {
  verdict: QualityVerdict;
  anomalies: Anomaly[];
  /** Resumen legible del porqué del veredicto. */
  reason: string;
};

/**
 * Cuántas anomalías SUSPICIOUS hacen falta para cuarentena.
 *
 * Una publicación rara en un aspecto suele ser un dato mal cargado. Rara en
 * tres a la vez suele ser una publicación basura entera, y ahí conviene sacarla
 * de circulación hasta que alguien mire.
 */
export const SUSPICIOSAS_PARA_CUARENTENA = 3;

/**
 * Analiza una publicación y emite un veredicto explicado.
 *
 * Nunca modifica la entrada. El veredicto sale de las anomalías, y las
 * anomalías siempre viajan con él: un veredicto sin razones no se puede
 * discutir ni corregir.
 */
export function analizarCalidad(p: PublicacionAnalizable): QualityReport {
  const anomalies = [
    ...incoherenciasInternas(p),
    ...anomaliasDeUbicacion(p),
    ...coherenciaDePrecio(p),
    ...valoresAtipicos(p),
    ...camposEsencialesAusentes(p),
  ];

  const invalidas = anomalies.filter((x) => x.severity === "INVALID");
  const sospechosas = anomalies.filter((x) => x.severity === "SUSPICIOUS");

  if (invalidas.length > 0) {
    return {
      verdict: "INVALID",
      anomalies,
      reason: `datos que se contradicen: ${invalidas.map((x) => x.code).join(", ")}`,
    };
  }
  if (sospechosas.length >= SUSPICIOSAS_PARA_CUARENTENA) {
    return {
      verdict: "QUARANTINE",
      anomalies,
      reason: `${sospechosas.length} señales atípicas a la vez`,
    };
  }
  if (sospechosas.length > 0) {
    return {
      verdict: "SUSPICIOUS",
      anomalies,
      reason: `señales atípicas: ${sospechosas.map((x) => x.code).join(", ")}`,
    };
  }
  return {
    verdict: "VALID",
    anomalies,
    reason: anomalies.length ? "sin anomalías; faltan campos no esenciales" : "sin anomalías",
  };
}
