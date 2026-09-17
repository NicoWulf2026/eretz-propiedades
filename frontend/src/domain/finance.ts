// Calculadoras inmobiliarias. Aritmética pura, sin proveedores ni cotizaciones.
//
// ---------------------------------------------------------------------------
// NINGUNA TASA ESTÁ ESCRITA ACÁ
// ---------------------------------------------------------------------------
//
// Toda tasa, comisión, alícuota y cotización es un PARÁMETRO. No hay defaults
// "razonables" escondidos, y no es purismo: los honorarios inmobiliarios y el
// impuesto de sellos varían por provincia y cambian por normativa, y la
// inflación argentina vuelve obsoleto cualquier número en meses. Una calculadora
// que trae un 3% adentro da un resultado con apariencia de autoridad que puede
// estar mal por un factor grande, y quien la usa no tiene forma de saberlo.
//
// El costo de esta decisión es que la UI tiene que pedir esos valores o
// mostrarlos como supuestos editables. Es el costo correcto.
//
// ---------------------------------------------------------------------------
// QUÉ NO ESTÁ, Y POR QUÉ
// ---------------------------------------------------------------------------
//
// Créditos UVA. Son el instrumento hipotecario dominante en la Argentina y su
// capital se ajusta por inflación, así que la cuota en pesos depende de la
// inflación FUTURA. Se puede proyectar bajo un supuesto, pero el resultado es
// una simulación, no un cálculo, y presentarla junto a las demás la haría pasar
// por lo que no es. Requiere una decisión de producto sobre cómo comunicar esa
// diferencia: queda fuera hasta tenerla.
//
// Comprar vs. alquilar. Depende de apreciación futura, costo de oportunidad e
// inflación —tres proyecciones—. Mismo motivo.

/** Todo cálculo puede no aplicar. Nunca se devuelve 0 en lugar de "no sé". */
export type Resultado<T> = { ok: true; valor: T } | { ok: false; motivo: string };

const ok = <T>(valor: T): Resultado<T> => ({ ok: true, valor });
const no = (motivo: string): Resultado<never> => ({ ok: false, motivo });

const esPositivo = (n: number | null | undefined): n is number =>
  typeof n === "number" && Number.isFinite(n) && n > 0;

const esNoNegativo = (n: number | null | undefined): n is number =>
  typeof n === "number" && Number.isFinite(n) && n >= 0;

// --- precio por m² ---------------------------------------------------------

/**
 * Precio por metro cuadrado.
 *
 * Toma la superficie explícitamente en vez de elegir entre total y cubierta:
 * son dos métricas distintas —el m² cubierto de un departamento no se compara
 * con el m² total de una casa con jardín— y elegir por la persona haría
 * incomparables resultados que parecen comparables.
 */
export function precioPorM2(precio: number | null, superficieM2: number | null): Resultado<number> {
  if (!esPositivo(precio)) return no("hace falta un precio publicado");
  if (!esPositivo(superficieM2)) return no("hace falta una superficie mayor que cero");
  return ok(precio / superficieM2);
}

// --- costos de una operación ----------------------------------------------

/**
 * Conceptos de una compra. Todos opcionales y todos parámetros.
 *
 * Las alícuotas van como fracción (0.03 = 3%) y los montos fijos aparte, porque
 * en la práctica conviven: los honorarios suelen ser porcentaje y la escritura
 * suele tener componentes fijos.
 */
export type ConceptosDeOperacion = {
  /** Honorarios inmobiliarios, como fracción del precio. */
  comisionFraccion?: number;
  /** Impuesto de sellos, como fracción. Varía por provincia. */
  sellosFraccion?: number;
  /** Honorarios de escribanía, como fracción. */
  escrituraFraccion?: number;
  /** Cualquier otro porcentaje aplicable. */
  otrosFraccion?: number;
  /** Gastos fijos: informes, certificados, gestoría. */
  montoFijo?: number;
};

export type DesgloseDeCostos = {
  comision: number;
  sellos: number;
  escritura: number;
  otros: number;
  fijos: number;
  total: number;
  /** Precio + costos, para una compra. */
  totalConPrecio: number;
};

/**
 * Costos de una operación sobre un precio.
 *
 * Sirve tanto para compra como para venta: los conceptos son los mismos y quien
 * llama decide cuáles pasa. No se asume quién paga qué, porque eso se negocia.
 */
export function costosDeOperacion(
  precio: number | null,
  conceptos: ConceptosDeOperacion = {},
): Resultado<DesgloseDeCostos> {
  if (!esPositivo(precio)) return no("hace falta un precio publicado");

  const fr = (v: number | undefined, nombre: string): Resultado<number> => {
    if (v === undefined) return ok(0);
    if (!esNoNegativo(v)) return no(`${nombre} tiene que ser un número no negativo`);
    // Una fracción mayor que 1 es casi siempre haber escrito 3 en vez de 0,03.
    if (v > 1) return no(`${nombre} parece un porcentaje: se espera una fracción (0,03 = 3%)`);
    return ok(v * precio);
  };

  const partes = {
    comision: fr(conceptos.comisionFraccion, "la comisión"),
    sellos: fr(conceptos.sellosFraccion, "el sellado"),
    escritura: fr(conceptos.escrituraFraccion, "la escritura"),
    otros: fr(conceptos.otrosFraccion, "otros gastos"),
  };
  for (const r of Object.values(partes)) if (!r.ok) return r;

  if (conceptos.montoFijo !== undefined && !esNoNegativo(conceptos.montoFijo)) {
    return no("los gastos fijos tienen que ser un número no negativo");
  }
  const fijos = conceptos.montoFijo ?? 0;

  const comision = (partes.comision as { ok: true; valor: number }).valor;
  const sellos = (partes.sellos as { ok: true; valor: number }).valor;
  const escritura = (partes.escritura as { ok: true; valor: number }).valor;
  const otros = (partes.otros as { ok: true; valor: number }).valor;
  const total = comision + sellos + escritura + otros + fijos;

  return ok({ comision, sellos, escritura, otros, fijos, total, totalConPrecio: precio + total });
}

// --- rentabilidad ----------------------------------------------------------

/**
 * Rentabilidad bruta anual: alquiler de un año sobre el precio.
 *
 * Es la métrica que todo el mundo cita y la que más engaña, porque ignora
 * expensas, impuestos, vacancia, mantenimiento y los costos de compra. Se
 * incluye porque es el punto de comparación habitual, no porque sea la buena.
 * Para decidir, `rentabilidadNeta`.
 */
export function rentabilidadBruta(
  alquilerMensual: number | null,
  precio: number | null,
): Resultado<number> {
  if (!esPositivo(alquilerMensual)) return no("hace falta un alquiler mensual");
  if (!esPositivo(precio)) return no("hace falta un precio");
  return ok((alquilerMensual * 12) / precio);
}

export type ParametrosRentabilidadNeta = {
  alquilerMensual: number;
  precio: number;
  /** Gastos mensuales a cargo del propietario: expensas, ABL, seguro. */
  gastosMensuales?: number;
  /** Impuestos y mantenimiento anuales. */
  gastosAnuales?: number;
  /**
   * Meses vacíos esperados por año. Es el parámetro que más mueve el resultado
   * y el que más se omite: un mes de vacancia se lleva el 8,3% del ingreso.
   */
  mesesVacanciaPorAnio?: number;
  /** Costos de compra, si se quiere rentabilidad sobre la inversión total. */
  costosDeCompra?: number;
};

/**
 * Rentabilidad neta anual sobre la inversión total.
 *
 * A diferencia de la bruta, descuenta gastos y vacancia, y divide por lo que
 * realmente costó adquirir —precio más costos— y no sólo por el precio.
 */
export function rentabilidadNeta(p: ParametrosRentabilidadNeta): Resultado<number> {
  if (!esPositivo(p.alquilerMensual)) return no("hace falta un alquiler mensual");
  if (!esPositivo(p.precio)) return no("hace falta un precio");

  const vacancia = p.mesesVacanciaPorAnio ?? 0;
  if (!esNoNegativo(vacancia) || vacancia > 12) return no("la vacancia va de 0 a 12 meses");

  const gastosMes = p.gastosMensuales ?? 0;
  const gastosAnio = p.gastosAnuales ?? 0;
  const costos = p.costosDeCompra ?? 0;
  if (![gastosMes, gastosAnio, costos].every(esNoNegativo)) {
    return no("los gastos y costos tienen que ser no negativos");
  }

  const mesesCobrados = 12 - vacancia;
  const ingreso = p.alquilerMensual * mesesCobrados;
  // Los gastos del propietario corren también los meses vacíos: las expensas de
  // un departamento vacío las paga el dueño. Omitirlo sobrestima la renta.
  const egreso = gastosMes * 12 + gastosAnio;
  const inversion = p.precio + costos;

  return ok((ingreso - egreso) / inversion);
}

/**
 * Flujo de caja mensual promedio.
 *
 * Puede ser negativo, y ése es justamente el resultado que interesa ver.
 */
export function cashFlowMensual(p: ParametrosRentabilidadNeta & { cuotaMensual?: number }): Resultado<number> {
  const neta = rentabilidadNeta(p);
  if (!neta.ok) return neta;

  const vacancia = p.mesesVacanciaPorAnio ?? 0;
  const ingresoAnual = p.alquilerMensual * (12 - vacancia);
  const egresoAnual = (p.gastosMensuales ?? 0) * 12 + (p.gastosAnuales ?? 0);
  const cuota = p.cuotaMensual ?? 0;
  if (!esNoNegativo(cuota)) return no("la cuota tiene que ser no negativa");

  return ok((ingresoAnual - egresoAnual) / 12 - cuota);
}

// --- crédito hipotecario ---------------------------------------------------

export type ParametrosCredito = {
  /** Monto del préstamo, ya descontado el anticipo. */
  capital: number;
  /** Tasa nominal ANUAL, como fracción (0.08 = 8%). Parámetro, nunca supuesto. */
  tasaAnual: number;
  /** Plazo en meses. */
  meses: number;
};

/**
 * Cuota fija por sistema francés.
 *
 *     cuota = C · i / (1 − (1+i)^−n)
 *
 * con `i` la tasa mensual y `n` los meses. Es el sistema de cuota constante,
 * que es como se expresan los créditos hipotecarios en la Argentina.
 *
 * La tasa mensual se toma como la anual dividida 12 —tasa nominal—, que es la
 * convención con la que los bancos publican la TNA. No es la tasa efectiva:
 * quien quiera partir de una TEA tiene que convertirla antes.
 *
 * El caso de tasa cero se trata aparte porque la fórmula se indefine ahí.
 */
export function cuotaHipotecaria(p: ParametrosCredito): Resultado<number> {
  if (!esPositivo(p.capital)) return no("hace falta un capital mayor que cero");
  if (!esNoNegativo(p.tasaAnual)) return no("la tasa no puede ser negativa");
  if (p.tasaAnual > 1) return no("la tasa se espera como fracción (0,08 = 8%)");
  if (!Number.isInteger(p.meses) || p.meses <= 0) return no("el plazo tiene que ser un número entero de meses");

  const i = p.tasaAnual / 12;
  if (i === 0) return ok(p.capital / p.meses);

  const factor = 1 - Math.pow(1 + i, -p.meses);
  return ok((p.capital * i) / factor);
}

export type ResumenCredito = {
  cuota: number;
  totalPagado: number;
  interesesTotales: number;
};

export function resumenCredito(p: ParametrosCredito): Resultado<ResumenCredito> {
  const c = cuotaHipotecaria(p);
  if (!c.ok) return c;
  const totalPagado = c.valor * p.meses;
  return ok({ cuota: c.valor, totalPagado, interesesTotales: totalPagado - p.capital });
}

/**
 * Capacidad de compra: qué capital se puede pedir con una cuota máxima.
 *
 * Es la inversa de la cuota:  C = cuota · (1 − (1+i)^−n) / i
 *
 * Devuelve el CAPITAL del préstamo, no el precio de la propiedad. Sumarle el
 * anticipo es decisión de quien llama, porque no todo anticipo disponible se
 * destina íntegro a la compra: parte paga escritura y sellos.
 */
export function capacidadDeCompra(p: {
  cuotaMaxima: number;
  tasaAnual: number;
  meses: number;
}): Resultado<number> {
  if (!esPositivo(p.cuotaMaxima)) return no("hace falta una cuota máxima mayor que cero");
  if (!esNoNegativo(p.tasaAnual)) return no("la tasa no puede ser negativa");
  if (p.tasaAnual > 1) return no("la tasa se espera como fracción (0,08 = 8%)");
  if (!Number.isInteger(p.meses) || p.meses <= 0) return no("el plazo tiene que ser un número entero de meses");

  const i = p.tasaAnual / 12;
  if (i === 0) return ok(p.cuotaMaxima * p.meses);
  return ok((p.cuotaMaxima * (1 - Math.pow(1 + i, -p.meses))) / i);
}

/**
 * Relación cuota/ingreso, el límite que aplican los bancos.
 *
 * No se fija un máximo acá: cada banco tiene el suyo y cambia. Se devuelve la
 * fracción para que quien llame la compare con el límite que corresponda.
 */
export function relacionCuotaIngreso(cuota: number | null, ingresoMensual: number | null): Resultado<number> {
  if (!esPositivo(cuota)) return no("hace falta una cuota");
  if (!esPositivo(ingresoMensual)) return no("hace falta un ingreso mensual");
  return ok(cuota / ingresoMensual);
}
