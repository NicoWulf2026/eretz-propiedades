// Metodología de ERETZ Mercado: cómo se calcula una estadística de zona, y
// cuándo NO se publica.
//
// El orden importa: esto viene antes que cualquier página de Mercado, porque
// una estadística mal hecha no se ve mal. "Precio promedio en Fisherton: USD
// 2.340/m²" se lee con la misma autoridad esté calculada sobre 800 avisos o
// sobre 3, y quien la lee puede tomar una decisión de cientos de miles de
// dólares con ella.
//
// ---------------------------------------------------------------------------
// CUATRO DECISIONES, Y POR QUÉ CADA UNA
// ---------------------------------------------------------------------------
//
// 1. MEDIANA, NO PROMEDIO. Un country de USD 3.000.000 entre veinte
//    departamentos de USD 90.000 mueve el promedio un 15% y la mediana nada. En
//    inmuebles los extremos son reales pero no representativos. El promedio se
//    calcula igual y se informa, para quien lo pida; la cifra que se muestra es
//    la mediana.
//
// 2. SE CUENTAN PROPIEDADES, NO AVISOS. La misma propiedad publicada por tres
//    inmobiliarias son tres filas y un solo inmueble. Contar filas infla la
//    oferta por un factor que además varía por zona —en zonas caras hay más
//    multi-publicación—, así que ni siquiera es un error parejo que se pueda
//    descontar después. Ver `property-entity.ts`.
//
// 3. UNA SOLA MONEDA POR SERIE. Mezclar pesos y dólares en una mediana da un
//    número sin significado. Las publicaciones sin precio en USD conocido no
//    entran en la serie en USD: se informan como excluidas, no se convierten
//    con una cotización supuesta.
//
// 4. SI LA MUESTRA NO ALCANZA, NO SE PUBLICA. No se publica con una advertencia
//    al pie: no se publica. Una advertencia que nadie lee al lado de un número
//    grande no protege a nadie.

/**
 * Propiedades mínimas para publicar una estadística.
 *
 * El mínimo se exige sobre la muestra FINAL, la que queda tras deduplicar y
 * recortar colas, y no sobre la de entrada. Consecuencia práctica que conviene
 * tener presente: con el recorte por defecto del 5% por cola, llegar a 30
 * propiedades finales requiere unas 34 de entrada. Es deliberado —el número
 * que importa es sobre cuántas observaciones se calculó la cifra publicada—
 * pero sorprende si uno espera que 30 de entrada alcancen.
 */
export const MUESTRA_MINIMA = 30;

/**
 * Muestra mínima para publicar precio por m².
 *
 * Más alta que la general porque el precio por m² arrastra el error de DOS
 * campos —precio y superficie— y la superficie es el peor dato del catálogo:
 * se confunde total con cubierta, y una publicación con la superficie mal
 * cargada produce un valor por m² absurdo que sobrevive al recorte de outliers
 * si hay pocas observaciones.
 */
export const MUESTRA_MINIMA_M2 = 50;

/** Fracción que se recorta de cada cola antes de calcular. */
export const RECORTE_POR_COLA = 0.05;

export const CONFIANZAS = ["ALTA", "MEDIA", "BAJA", "INSUFICIENTE"] as const;
export type Confianza = (typeof CONFIANZAS)[number];

export type Observacion = {
  /** Id de la propiedad física, NO del aviso. Se deduplica por acá. */
  propertyEntityId: string;
  value: number;
};

export type EstadisticaDeZona = {
  /** Cuántas propiedades distintas quedaron tras deduplicar y recortar. */
  n: number;
  /** Cuántas observaciones se descartaron por duplicado. */
  duplicadasDescartadas: number;
  /** Cuántas se recortaron por extremas. */
  recortadas: number;
  mediana: number;
  promedio: number;
  p25: number;
  p75: number;
  minimo: number;
  maximo: number;
  confianza: Confianza;
};

export type ResultadoDeZona =
  | { publicable: true; estadistica: EstadisticaDeZona }
  | { publicable: false; motivo: string; n: number };

/** Percentil por interpolación lineal sobre una serie ya ordenada. */
function percentil(ordenados: readonly number[], p: number): number {
  if (ordenados.length === 1) return ordenados[0];
  const pos = (ordenados.length - 1) * p;
  const bajo = Math.floor(pos);
  const alto = Math.ceil(pos);
  if (bajo === alto) return ordenados[bajo];
  return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo);
}

/**
 * Confianza según el tamaño de la muestra.
 *
 * Los cortes son convención, no estadística formal: no hay intervalo de
 * confianza acá porque la muestra no es aleatoria —es "lo que está publicado
 * y logramos scrapear"—, y poner un ± sobre una muestra sesgada le daría una
 * precisión que no tiene. La confianza es cualitativa a propósito.
 */
export function confianzaPorTamano(n: number, minimo = MUESTRA_MINIMA): Confianza {
  if (n < minimo) return "INSUFICIENTE";
  if (n >= minimo * 6) return "ALTA";
  if (n >= minimo * 2) return "MEDIA";
  return "BAJA";
}

/**
 * Calcula la estadística de una zona, o explica por qué no se puede.
 *
 * Deduplica por propiedad física, recorta colas, y sólo entonces calcula. Si
 * tras todo eso la muestra no alcanza, devuelve `publicable: false` y no hay
 * número que mostrar. Es la función que evita la página de Mercado inventada.
 */
export function calcularZona(
  observaciones: readonly Observacion[],
  { muestraMinima = MUESTRA_MINIMA, recorte = RECORTE_POR_COLA } = {},
): ResultadoDeZona {
  // 1. Deduplicar por propiedad física. La primera observación de cada entidad
  // gana; el orden lo fija quien llama y es estable.
  const porEntidad = new Map<string, number>();
  let duplicadas = 0;
  for (const o of observaciones) {
    if (!Number.isFinite(o.value) || o.value <= 0) continue;
    if (porEntidad.has(o.propertyEntityId)) {
      duplicadas += 1;
      continue;
    }
    porEntidad.set(o.propertyEntityId, o.value);
  }

  const valores = [...porEntidad.values()].sort((a, b) => a - b);
  if (valores.length < muestraMinima) {
    return {
      publicable: false,
      motivo: `hacen falta al menos ${muestraMinima} propiedades y hay ${valores.length}`,
      n: valores.length,
    };
  }

  // 2. Recortar colas. Se recorta DESPUÉS de deduplicar: si se recortara antes,
  // un aviso repetido tres veces contaría triple para decidir qué es extremo.
  const aRecortar = Math.floor(valores.length * recorte);
  const centro = aRecortar > 0 ? valores.slice(aRecortar, valores.length - aRecortar) : valores;

  if (centro.length < muestraMinima) {
    return {
      publicable: false,
      motivo: `tras recortar extremos quedan ${centro.length}, por debajo de ${muestraMinima}`,
      n: centro.length,
    };
  }

  const suma = centro.reduce((a, b) => a + b, 0);
  return {
    publicable: true,
    estadistica: {
      n: centro.length,
      duplicadasDescartadas: duplicadas,
      recortadas: valores.length - centro.length,
      mediana: percentil(centro, 0.5),
      promedio: suma / centro.length,
      p25: percentil(centro, 0.25),
      p75: percentil(centro, 0.75),
      minimo: centro[0],
      maximo: centro[centro.length - 1],
      confianza: confianzaPorTamano(centro.length, muestraMinima),
    },
  };
}

// --- qué se puede publicar HOY ---------------------------------------------

/**
 * Diagnóstico de si el catálogo actual sostiene una página de Mercado.
 *
 * Existe porque la respuesta hoy es que no, y conviene que eso sea una
 * comprobación ejecutable y no una opinión en un documento que envejece.
 *
 * Los dos bloqueos son concretos y están medidos sobre producción:
 *
 * - Sólo el 25,3% de las publicaciones tiene coordenadas (65.033 de 257.073),
 *   así que cualquier corte por barrio se apoya en texto de ciudad/barrio sin
 *   normalizar, no en geografía.
 * - No existe todavía la resolución de propiedad física, así que no se puede
 *   deduplicar y toda serie contaría avisos.
 */
export type DiagnosticoDeMercado = {
  puedePublicar: boolean;
  bloqueos: string[];
};

export function diagnosticarMercado(estado: {
  resolucionDeEntidadesDisponible: boolean;
  fraccionConUbicacionFiable: number;
  fraccionConPrecioUsd: number;
}): DiagnosticoDeMercado {
  const bloqueos: string[] = [];

  if (!estado.resolucionDeEntidadesDisponible) {
    bloqueos.push("sin resolución de propiedad física, toda serie contaría avisos y no inmuebles");
  }
  if (estado.fraccionConUbicacionFiable < 0.5) {
    bloqueos.push(
      `sólo el ${Math.round(estado.fraccionConUbicacionFiable * 100)}% tiene ubicación fiable: ` +
        "un corte por barrio no sería representativo",
    );
  }
  if (estado.fraccionConPrecioUsd < 0.5) {
    bloqueos.push(
      `sólo el ${Math.round(estado.fraccionConPrecioUsd * 100)}% tiene precio en USD conocido`,
    );
  }

  return { puedePublicar: bloqueos.length === 0, bloqueos };
}
