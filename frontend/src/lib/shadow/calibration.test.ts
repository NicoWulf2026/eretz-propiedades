import { describe, expect, it } from "vitest";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";
import type { SupabaseProperty } from "@/types/property";
import { advertencias, evaluarLote, type ParaEvaluar, type ResumenShadow } from "./evaluate";
import type { ConfiguracionShadow } from "./flag";

// Calibración de las reglas contra un corpus REPRESENTATIVO, no contra el
// catálogo real.
//
// ---------------------------------------------------------------------------
// QUÉ MIDE ESTO Y QUÉ NO
// ---------------------------------------------------------------------------
//
// NO mide la distribución del catálogo. Para eso hace falta una conexión a la
// base, que este entorno no tiene y que no se va a crear.
//
// SÍ mide si las reglas se disparan de más sobre publicaciones plausibles. Es
// una pregunta distinta y también importante: si una regla marca a una
// publicación normal, el problema está en la regla, y eso se detecta sin
// conocer la distribución real.
//
// El corpus cubre los ejes que importan: moneda, presencia de precio, fotos,
// niveles de confianza geográfica, tipos de propiedad, y publicador
// identificado o no. Las proporciones son deliberadamente PAREJAS —una por
// variante— y por lo tanto NO representan al catálogo, donde por ejemplo el
// 74,7% no tiene coordenadas. Leer estos porcentajes como si fueran los reales
// sería el error que este comentario existe para evitar.

const ENCENDIDO: ConfiguracionShadow = { activo: true, fraccion: 1 };

let siguienteId = 10_000;
function variante(o: Partial<SupabaseProperty>): ParaEvaluar {
  const item = { ...completeRow, id: siguienteId++, ...o };
  return { property: mapSupabasePropertyToProperty(item), item };
}

/**
 * Publicaciones plausibles: cosas que existen de verdad en el mercado.
 *
 * Ninguna tiene datos rotos. Si una de éstas se marca, es un falso positivo.
 */
function corpusPlausible(): ParaEvaluar[] {
  return [
    // --- monedas y modalidad de precio ---
    variante({ moneda: "USD", precio: 85_000, precio_usd: 85_000 }),
    variante({ moneda: "ARS", precio: 95_000_000, precio_usd: null }),
    variante({ operacion: "alquiler", moneda: "ARS", precio: 450_000, precio_usd: null, expensas: 90_000 }),
    variante({ operacion: "alquiler", moneda: "USD", precio: 900, precio_usd: 900 }),
    // A consultar: legítimo y frecuente.
    variante({ precio: null, precio_usd: null, moneda: null }),
    variante({ operacion: "temporario", precio: 60_000, moneda: "ARS", precio_usd: null }),

    // --- tipos ---
    variante({ tipo_propiedad: "departamento", superficie_total: 45, superficie_cubierta: 45, ambientes: 2, dormitorios: 1 }),
    variante({ tipo_propiedad: "casa", superficie_total: 300, superficie_cubierta: 180, ambientes: 5, dormitorios: 3 }),
    variante({ tipo_propiedad: "ph", superficie_total: 90, superficie_cubierta: 75 }),
    variante({ tipo_propiedad: "terreno", superficie_total: 500, superficie_cubierta: null, ambientes: null, dormitorios: null, banos: null }),
    variante({ tipo_propiedad: "local", superficie_total: 120, superficie_cubierta: 120 }),
    // Un campo grande es legítimo: la regla lo exceptúa.
    variante({ tipo_propiedad: "campo", superficie_total: 450_000, superficie_cubierta: null, superficie_terreno: 450_000, ambientes: null, dormitorios: null, banos: null }),
    variante({ tipo_propiedad: "cochera", superficie_total: 15, superficie_cubierta: 15, ambientes: null, dormitorios: null, banos: null }),
    // Monoambiente chico: raro pero real.
    variante({ tipo_propiedad: "departamento", superficie_total: 22, superficie_cubierta: 22, ambientes: 1, dormitorios: null }),

    // --- geografía ---
    variante({ latitud: -32.95, longitud: -60.66, direccion: "Córdoba 1234" }),
    variante({ latitud: -34.6, longitud: -58.38, direccion: "Av. Corrientes 500" }),
    // Sin coordenadas: tres de cada cuatro del catálogo real.
    variante({ latitud: null, longitud: null }),
    variante({ latitud: null, longitud: null, direccion: null, barrio: "Fisherton" }),

    // --- fotos ---
    variante({ imagenes: ["https://e.com/1.jpg"] }),
    variante({ imagenes: Array.from({ length: 12 }, (_, i) => `https://e.com/${i}.jpg`) }),

    // --- publicador ---
    variante({ publisher_name: "Inmobiliaria López", publisher_verified: true, publisher_phone: "3410000000" }),
    variante({ publisher_name: "Inmobiliaria Sur", publisher_verified: false, publisher_phone: "3410000001" }),
    variante({ publisher_name: null, agente_nombre: "Juan Pérez", agente_telefono: "3410000002" }),

    // --- antigüedad ---
    variante({ antiguedad: 0 }),
    variante({ antiguedad: 80 }),
  ];
}

/**
 * Problemas que SÍ llegan al dominio y se detectan.
 *
 * Son los que el mapper deja pasar tal cual: incoherencias entre campos y
 * valores atípicos dentro de rango.
 */
function corpusDetectable(): ParaEvaluar[] {
  return [
    variante({ superficie_cubierta: 900, superficie_total: 100 }),
    variante({ ambientes: 2, dormitorios: 7 }),
    variante({ antiguedad: 900 }),
  ];
}

/**
 * Problemas que el MAPPER neutraliza antes de que el dominio los vea.
 *
 * Hallazgo de este bloque, y de los que sólo aparecen al enfrentar el código
 * con datos: `mapSupabasePropertyToProperty` no traduce, SANEA. Convierte a
 * `null` las coordenadas fuera de la Argentina (`hasValidArgentinaCoordinates`)
 * y los números no positivos (`positiveNumber`).
 *
 * Consecuencia para leer cualquier medición del modo sombra: varias reglas de
 * `data-quality` —`COORDENADAS_FUERA_DE_RANGO`, `COORDENADAS_CERO`,
 * `VALOR_NEGATIVO`— **no pueden dispararse en este camino**. No porque el dato
 * esté bien, sino porque llega ya convertido en ausencia.
 *
 * No se corrige leyendo la fila cruda, y es deliberado: el modo sombra mide lo
 * que la APLICACIÓN ve, que es lo que decidiría si las reglas se activaran acá.
 * Medir la calidad del dato crudo es una pregunta distinta y su lugar es el
 * pipeline de ingesta, no el camino de lectura.
 */
function corpusSaneadoPorElMapper(): ParaEvaluar[] {
  return [
    variante({ latitud: 40.7, longitud: -74 }),
    variante({ latitud: 0, longitud: 0 }),
    variante({ precio: -5000, precio_usd: null }),
  ];
}

const pct = (n: number, total: number) => (total === 0 ? 0 : Math.round((n / total) * 1000) / 10);

function tabla(r: ResumenShadow): string {
  const n = r.evaluadas;
  return [
    `evaluadas=${n}`,
    `ALLOW=${pct(r.moderacion.ALLOW, n)}% REVIEW=${pct(r.moderacion.REVIEW, n)}% REJECT=${pct(r.moderacion.REJECT, n)}%`,
    `VALID=${pct(r.calidadDeDatos.VALID, n)}% SUSPICIOUS=${pct(r.calidadDeDatos.SUSPICIOUS, n)}% INVALID=${pct(r.calidadDeDatos.INVALID, n)}% QUARANTINE=${pct(r.calidadDeDatos.QUARANTINE, n)}%`,
    `score p10=${r.puntaje?.p10} p50=${r.puntaje?.p50} p90=${r.puntaje?.p90}`,
    `dims ${JSON.stringify(r.puntaje?.dimensiones)}`,
    `razones ${r.razones.map((x) => `${x.code}:${x.count}`).join(" ")}`,
  ].join("\n  ");
}

describe("las reglas no se disparan sobre publicaciones plausibles", () => {
  const resumen = evaluarLote(corpusPlausible(), ENCENDIDO) as ResumenShadow;

  it("imprime la distribución del corpus plausible", () => {
    // No es una aserción: es la evidencia que se lee en el informe.
    console.info(`\n[calibración · corpus plausible]\n  ${tabla(resumen)}\n`);
    expect(resumen.evaluadas).toBeGreaterThan(20);
  });

  it("ninguna publicación plausible se rechaza", () => {
    // Un REJECT acá sería un falso positivo puro.
    expect(resumen.moderacion.REJECT).toBe(0);
  });

  it("ninguna se marca como dato inválido", () => {
    expect(resumen.calidadDeDatos.INVALID).toBe(0);
    expect(resumen.calidadDeDatos.QUARANTINE).toBe(0);
  });

  it("un campo grande no se marca por superficie", () => {
    // La excepción para uso rural funciona sobre un caso real.
    const razones = resumen.razones.map((r) => r.code);
    expect(razones).not.toContain("SUPERFICIE_MUY_GRANDE");
  });

  it("un alquiler en pesos no dispara los rangos de venta en dólares", () => {
    const razones = resumen.razones.map((r) => r.code);
    expect(razones).not.toContain("PRECIO_VENTA_MUY_BAJO");
    expect(razones).not.toContain("ALQUILER_MUY_ALTO");
  });

  it("una publicación a consultar no se penaliza como si le faltara el precio", () => {
    expect(resumen.razones.map((r) => r.code)).not.toContain("PRECIO_CERO");
  });

  it("la mayoría queda en ALLOW", () => {
    // Si el corpus plausible diera mayoría REVIEW, las reglas serían
    // impracticables sobre el catálogo real.
    expect(resumen.moderacion.ALLOW).toBeGreaterThan(resumen.moderacion.REVIEW);
  });

  it("no dispara los umbrales diagnósticos", () => {
    expect(advertencias(resumen).map((a) => a.code)).not.toContain("REJECT_ALTO");
  });
});

describe("las reglas sí detectan lo que está roto", () => {
  const resumen = evaluarLote(corpusDetectable(), ENCENDIDO) as ResumenShadow;

  it("imprime la distribución del corpus detectable", () => {
    console.info(`\n[calibración · corpus detectable]\n  ${tabla(resumen)}\n`);
    expect(resumen.evaluadas).toBe(3);
  });

  it("ninguna queda como VALID", () => {
    expect(resumen.calidadDeDatos.VALID).toBe(0);
  });

  it("ninguna se bloquea, porque todas son scrapeadas", () => {
    // La asimetría por origen en acción: se revisan, no se esconden.
    expect(resumen.moderacion.REJECT).toBe(0);
    expect(resumen.moderacion.REVIEW).toBe(3);
  });

  it("su puntaje es marcadamente menor que el del corpus plausible", () => {
    const sano = evaluarLote(corpusPlausible(), ENCENDIDO) as ResumenShadow;
    expect(resumen.puntaje?.p50).toBeLessThan(sano.puntaje?.p50 as number);
  });
});

describe("el mapper sanea antes que el dominio mire", () => {
  const resumen = evaluarLote(corpusSaneadoPorElMapper(), ENCENDIDO) as ResumenShadow;

  it("las coordenadas inválidas y los precios negativos llegan como ausencia", () => {
    // Hallazgo, no defecto de las reglas: el dato malo ya no está cuando el
    // dominio mira. Una medición del modo sombra SUBESTIMA los problemas del
    // dato crudo, y leerla como si midiera la ingesta sería un error.
    console.info(`\n[calibración · saneado por el mapper]\n  ${tabla(resumen)}\n`);
    expect(resumen.calidadDeDatos.VALID).toBe(3);
    expect(resumen.moderacion.ALLOW).toBe(3);
  });

  it("las reglas de coordenadas y negativos no llegan a dispararse", () => {
    const razones = resumen.razones.map((r) => r.code);
    for (const inalcanzable of ["COORDENADAS_FUERA_DE_RANGO", "COORDENADAS_CERO", "VALOR_NEGATIVO"]) {
      expect(razones).not.toContain(inalcanzable);
    }
  });

  it("un precio negativo queda indistinguible de 'a consultar'", () => {
    // `positiveNumber` lo vuelve null, que es exactamente lo que significa una
    // publicación sin precio. La información de que venía un -5000 se perdió
    // antes, en el mapeo.
    const [uno] = corpusSaneadoPorElMapper().slice(2);
    expect(uno.property.price).toBeNull();
  });
});

describe("overhead del modo sombra", () => {
  it("mide el costo de evaluar frente a no evaluar", () => {
    const lote = [...corpusPlausible(), ...corpusPlausible()];
    const vueltas = 200;

    // Apagado: `evaluarLote` sale por la primera comparación.
    const t0 = performance.now();
    for (let i = 0; i < vueltas; i++) evaluarLote(lote, { activo: false, fraccion: 0 });
    const apagado = performance.now() - t0;

    const t1 = performance.now();
    for (let i = 0; i < vueltas; i++) evaluarLote(lote, ENCENDIDO);
    const encendido = performance.now() - t1;

    const porPropiedad = (encendido - apagado) / (vueltas * lote.length);
    console.info(
      `\n[overhead] lote=${lote.length} vueltas=${vueltas}\n` +
        `  apagado=${apagado.toFixed(1)}ms  encendido=${encendido.toFixed(1)}ms\n` +
        `  por propiedad=${(porPropiedad * 1000).toFixed(1)}µs\n`,
    );

    // Cota amplia y estable: lo que se afirma es el orden de magnitud —decenas
    // de microsegundos por propiedad—, no un número exacto que dependería de
    // la máquina y haría el test frágil.
    expect(porPropiedad).toBeLessThan(1);
  });

  it("apagado el costo es indistinguible de cero", () => {
    const lote = corpusPlausible();
    const t0 = performance.now();
    for (let i = 0; i < 10_000; i++) evaluarLote(lote, { activo: false, fraccion: 0 });
    const ms = performance.now() - t0;
    // 10.000 llamadas sobre un lote de 25 en menos de 100ms: no recorre nada.
    expect(ms).toBeLessThan(100);
  });
});
