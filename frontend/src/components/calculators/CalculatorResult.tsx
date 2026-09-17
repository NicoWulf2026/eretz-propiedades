"use client";

// Cómo se presenta un resultado.
//
// Cuatro partes, y ninguna es decorativa:
//
//   RESULTADO    el número que se vino a buscar;
//   DESGLOSE     de dónde sale, línea por línea;
//   FÓRMULA      qué se hizo, en una oración;
//   SUPUESTOS    qué valores puso la persona y no vinieron de ningún lado.
//
// Las dos últimas existen porque un número solo, grande y bien tipografiado, se
// lee como un dato. Y no lo es: es aritmética sobre lo que alguien ingresó. Los
// supuestos son la diferencia entre una herramienta y una afirmación.

import type { ReactNode } from "react";

export type LineaDeDesglose = {
  concepto: string;
  valor: string;
  /** Destaca el total frente a sus componentes. */
  total?: boolean;
};

export function ResultadoPendiente({ falta }: { falta: string }) {
  return (
    <div className="calc-result calc-result-pending">
      <p className="calc-result-pending-text">{falta}</p>
    </div>
  );
}

export function Resultado({
  etiqueta,
  valor,
  nota,
  desglose,
  formula,
  supuestos,
}: {
  etiqueta: string;
  valor: string;
  /** Aclaración inmediata bajo la cifra. Por ejemplo, "por mes". */
  nota?: string;
  desglose?: LineaDeDesglose[];
  formula?: ReactNode;
  supuestos?: string[];
}) {
  return (
    <div className="calc-result">
      <p className="calc-result-label">{etiqueta}</p>
      {/* aria-live: el resultado cambia sin recargar ni enviar nada, así que
          alguien con lector de pantalla no se enteraría de que se actualizó. */}
      <p className="calc-result-value" aria-live="polite">{valor}</p>
      {nota ? <p className="calc-result-note">{nota}</p> : null}

      {desglose?.length ? (
        <dl className="calc-breakdown">
          {desglose.map((linea) => (
            <div key={linea.concepto} className={linea.total ? "calc-breakdown-row is-total" : "calc-breakdown-row"}>
              <dt>{linea.concepto}</dt>
              <dd>{linea.valor}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {formula ? (
        <details className="calc-formula">
          <summary>Cómo se calcula</summary>
          <div className="calc-formula-body">{formula}</div>
        </details>
      ) : null}

      {supuestos?.length ? (
        <div className="calc-assumptions">
          <p className="calc-assumptions-title">Supuestos que ingresaste</p>
          <ul>
            {supuestos.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Aviso que acompaña a toda calculadora.
 *
 * No es letra chica defensiva: es la afirmación exacta de qué es y qué no es
 * esto. ERETZ no es un banco ni un asesor, y el resultado no compromete a
 * nadie.
 */
export function AvisoDeCalculo() {
  return (
    <p className="calc-disclaimer">
      Es una estimación calculada con los valores que ingresás. No es una oferta,
      ni una cotización, ni asesoramiento financiero. Confirmá siempre las
      condiciones reales con el banco, la inmobiliaria o el escribano.
    </p>
  );
}
