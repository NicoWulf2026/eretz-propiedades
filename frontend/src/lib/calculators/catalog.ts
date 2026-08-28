// Qué calculadoras existen, y cuáles NO y por qué.
//
// La lista sale de lo que `domain/finance.ts` puede calcular de forma
// determinista, no de lo que sería lindo tener. Cada entrada de abajo se apoya
// en una función testeada; ninguna se implementó por intuición.

export type CalculadoraId =
  | "cuota-hipotecaria"
  | "capacidad-de-compra"
  | "precio-por-m2"
  | "gastos-de-operacion"
  | "rentabilidad";

export type Calculadora = {
  id: CalculadoraId;
  titulo: string;
  /** Una línea, para la card del hub. */
  resumen: string;
  /** Qué pregunta responde, en primera persona de quien la usa. */
  pregunta: string;
  /** Si necesita que la persona aporte una tasa o alícuota. */
  requiereSupuestos: boolean;
};

export const CALCULADORAS: readonly Calculadora[] = Object.freeze([
  {
    id: "cuota-hipotecaria",
    titulo: "Cuota hipotecaria",
    resumen: "Cuánto pagarías por mes, cuánto en total y cuánto de intereses.",
    pregunta: "¿Cuál sería mi cuota?",
    requiereSupuestos: true,
  },
  {
    id: "capacidad-de-compra",
    titulo: "Capacidad de compra",
    resumen: "Hasta cuánto podrías pedir con la cuota que podés pagar.",
    pregunta: "¿Cuánto puedo pedir?",
    requiereSupuestos: true,
  },
  {
    id: "precio-por-m2",
    titulo: "Precio por m²",
    resumen: "Para comparar propiedades de distinto tamaño.",
    pregunta: "¿Está cara para lo que mide?",
    requiereSupuestos: false,
  },
  {
    id: "gastos-de-operacion",
    titulo: "Gastos de una operación",
    resumen: "Comisión, sellos, escritura y gastos fijos, sobre el precio.",
    pregunta: "¿Cuánto necesito además del precio?",
    requiereSupuestos: true,
  },
  {
    id: "rentabilidad",
    titulo: "Rentabilidad de un alquiler",
    resumen: "Bruta, neta y flujo mensual, descontando gastos y vacancia.",
    pregunta: "¿Cuánto deja por año?",
    requiereSupuestos: false,
  },
]);

export function calculadoraPorId(id: string): Calculadora | undefined {
  return CALCULADORAS.find((c) => c.id === id);
}

/**
 * Lo que NO está, con el motivo.
 *
 * Se publica en el hub en vez de omitirse: quien busca una calculadora de UVA
 * y no la encuentra merece saber que la decisión fue deliberada, no un olvido.
 */
export type Pendiente = { titulo: string; motivo: string };

export const PENDIENTES: readonly Pendiente[] = Object.freeze([
  {
    titulo: "Créditos UVA",
    motivo:
      "El capital se ajusta por inflación, así que la cuota en pesos depende de la inflación futura. " +
      "Se puede proyectar bajo un supuesto, pero el resultado sería una simulación y no un cálculo, " +
      "y mostrarla junto a las demás la haría pasar por lo que no es.",
  },
  {
    titulo: "Comprar o alquilar",
    motivo:
      "Depende de tres proyecciones a futuro —apreciación, costo de oportunidad e inflación— " +
      "y el resultado cambia por completo según qué se suponga. Mismo motivo.",
  },
]);
