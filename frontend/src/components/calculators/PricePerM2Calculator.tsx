"use client";

import { useState } from "react";
import { precioPorM2 } from "@/domain/finance";
import { formatearDinero, formatearSuperficie, parsearNumero, type Moneda } from "@/lib/calculators/input";
import { CampoDinero, CampoSuperficie, SelectorDeMoneda } from "./CalculatorFields";
import { AvisoDeCalculo, Resultado, ResultadoPendiente } from "./CalculatorResult";

// Precio por m². La más simple de todas y la que más fácil se usa mal.
//
// El dominio pide la superficie explícitamente en vez de elegir entre total y
// cubierta, y esa decisión se refleja acá: la persona elige cuál usa. Son dos
// métricas distintas —el m² cubierto de un departamento no se compara con el m²
// total de una casa con jardín— y elegir por ella haría incomparables
// resultados que parecen comparables.

type TipoDeSuperficie = "total" | "cubierta";

export function PricePerM2Calculator() {
  const [moneda, setMoneda] = useState<Moneda>("USD");
  const [precio, setPrecio] = useState("");
  const [superficie, setSuperficie] = useState("");
  const [tipo, setTipo] = useState<TipoDeSuperficie>("total");

  const valorPrecio = parsearNumero(precio);
  const valorSuperficie = parsearNumero(superficie);
  const r = precioPorM2(valorPrecio, valorSuperficie);

  return (
    <div className="calc-layout">
      <form className="calc-form" onSubmit={(e) => e.preventDefault()}>
        <div className="calc-grid">
          <SelectorDeMoneda valor={moneda} onChange={setMoneda} />
          <CampoDinero etiqueta="Precio" moneda={moneda} valor={precio} onChange={setPrecio} />
          <CampoSuperficie
            etiqueta="Superficie"
            valor={superficie}
            onChange={setSuperficie}
            ayuda="Usá siempre la misma para comparar entre propiedades."
          />
          <fieldset className="calc-modes">
            <legend>Qué superficie estás usando</legend>
            <div className="calc-mode-options">
              <label className="check">
                <input type="radio" name="superficie" checked={tipo === "total"} onChange={() => setTipo("total")} />
                Total
              </label>
              <label className="check">
                <input type="radio" name="superficie" checked={tipo === "cubierta"} onChange={() => setTipo("cubierta")} />
                Cubierta
              </label>
            </div>
          </fieldset>
        </div>
      </form>

      <div className="calc-output">
        {!r.ok ? (
          <ResultadoPendiente falta="Completá el precio y la superficie." />
        ) : (
          <Resultado
            etiqueta={`Precio por m² ${tipo === "total" ? "total" : "cubierto"}`}
            valor={formatearDinero(r.valor, moneda)}
            desglose={[
              { concepto: "Precio", valor: formatearDinero(valorPrecio as number, moneda) },
              { concepto: "Superficie", valor: formatearSuperficie(valorSuperficie as number) },
            ]}
            formula={
              <>
                <p>Precio dividido superficie. Nada más.</p>
                <p>
                  Lo que hace útil o inútil al número es <strong>con qué lo comparás</strong>. Un m²
                  cubierto y un m² total no son la misma medida: una casa con jardín grande tiene un
                  precio por m² total bajo sin ser más barata.
                </p>
              </>
            }
            supuestos={[`Superficie ${tipo === "total" ? "total" : "cubierta"}, según lo que elegiste`]}
          />
        )}
        <AvisoDeCalculo />
      </div>
    </div>
  );
}
