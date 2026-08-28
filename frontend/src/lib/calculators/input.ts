// Parseo y formateo para las calculadoras.
//
// ---------------------------------------------------------------------------
// EL PORCENTAJE ES DONDE SE ROMPE TODO
// ---------------------------------------------------------------------------
//
// `domain/finance.ts` recibe las tasas como FRACCIÓN: 0,08 para un 8%. La
// gente escribe 8. Si la conversión falla, la cuota sale por un factor de cien
// y el número tiene toda la apariencia de estar bien.
//
// `finance.ts` ya se defiende —rechaza cualquier fracción mayor que 1— pero esa
// defensa es la última, no la primera. Acá se convierte una sola vez, en
// `fraccionDesdePorcentaje`, y ninguna pantalla vuelve a dividir por cien por
// su cuenta.
//
// ---------------------------------------------------------------------------
// VACÍO NO ES CERO
// ---------------------------------------------------------------------------
//
// Un campo sin completar devuelve `null`, no `0`. La diferencia importa: con 0
// la calculadora devolvería un resultado —equivocado y con aire de válido— en
// lugar de decir que falta un dato.

/** Separador decimal en castellano: se acepta coma y punto. */
const NUMERO = /^-?\d*(?:[.,]\d*)?$/;

/**
 * Convierte lo que hay en un input en un número, o en `null`.
 *
 * Devuelve `null` para el campo vacío y para cualquier cosa que no sea un
 * número finito. Nunca devuelve `NaN` ni `Infinity`: son los dos valores que
 * atraviesan los cálculos sin fallar y salen del otro lado como resultado.
 */
export function parsearNumero(valor: string): number | null {
  const limpio = valor.trim().replace(",", ".");
  if (limpio === "" || limpio === "-" || limpio === ".") return null;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

/** ¿Este texto puede seguir escribiéndose hasta ser un número? */
export function esEntradaNumericaParcial(valor: string): boolean {
  return valor === "" || NUMERO.test(valor.replace(",", "."));
}

/**
 * Convierte un porcentaje escrito por una persona en la fracción que espera el
 * dominio. Único lugar donde se divide por cien.
 */
export function fraccionDesdePorcentaje(porcentaje: number | null): number | null {
  return porcentaje === null ? null : porcentaje / 100;
}

export function porcentajeDesdeFraccion(fraccion: number): number {
  return fraccion * 100;
}

// --- validación de rango ---------------------------------------------------

export type Limite = { min?: number; max?: number; entero?: boolean };

/**
 * Qué tiene de malo un valor, en castellano y para mostrar bajo el campo.
 *
 * Devuelve `null` cuando está bien o cuando está vacío: un campo que todavía no
 * se completó no es un campo con error, y marcarlo en rojo apenas se abre la
 * pantalla es hostil.
 */
export function problemaDeValor(valor: number | null, limite: Limite = {}): string | null {
  if (valor === null) return null;
  if (!Number.isFinite(valor)) return "Ingresá un número";
  if (limite.entero && !Number.isInteger(valor)) return "Tiene que ser un número entero";
  if (limite.min !== undefined && valor < limite.min) {
    return limite.min === 0 ? "No puede ser negativo" : `Tiene que ser ${limite.min} o más`;
  }
  if (limite.max !== undefined && valor > limite.max) return `Tiene que ser ${limite.max} o menos`;
  return null;
}

// --- formateo --------------------------------------------------------------

const enteros = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const dosDecimales = new Intl.NumberFormat("es-AR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const unDecimal = new Intl.NumberFormat("es-AR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export type Moneda = "USD" | "ARS";

/**
 * Importe con su moneda.
 *
 * Muestra centavos sólo cuando **existen y aportan**: una cuota de USD 599,55
 * pierde información si se redondea a 600, pero un total de USD 7.300 exacto no
 * gana nada con un ",00" que además sugiere una precisión que no tiene.
 *
 * Por encima de diez mil se redondea siempre: los centavos de un total de
 * USD 215.838 son ruido.
 */
export function formatearDinero(valor: number, moneda: Moneda): string {
  const abs = Math.abs(valor);
  const tieneFraccion = !Number.isInteger(valor);
  const cuerpo = tieneFraccion && abs < 10_000
    ? dosDecimales.format(valor)
    : enteros.format(Math.round(valor));
  return `${moneda} ${cuerpo}`;
}

/** Porcentaje a partir de una FRACCIÓN. Recibe 0,06 y muestra "6,0%". */
export function formatearPorcentaje(fraccion: number): string {
  return `${unDecimal.format(fraccion * 100)}%`;
}

export function formatearNumero(valor: number): string {
  return enteros.format(valor);
}

/** Superficie con su unidad. */
export function formatearSuperficie(valor: number): string {
  return `${enteros.format(valor)} m²`;
}
