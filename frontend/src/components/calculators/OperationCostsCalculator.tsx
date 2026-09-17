"use client";

import { useState } from "react";
import { costosDeOperacion } from "@/domain/finance";
import {
  formatearDinero,
  fraccionDesdePorcentaje,
  parsearNumero,
  type Moneda,
} from "@/lib/calculators/input";
import { CampoDinero, CampoPorcentaje, SelectorDeMoneda } from "./CalculatorFields";
import { AvisoDeCalculo, Resultado, ResultadoPendiente } from "./CalculatorResult";

// Gastos de una operación: comisión, sellos, escritura y fijos.
//
// Sirve para compra y para venta, porque los conceptos son los mismos y quien
// paga qué se negocia. Lo único que cambia es si el total se suma al precio o
// se resta, y eso lo decide el modo.
//
// NINGUNA ALÍCUOTA VIENE CARGADA. Los honorarios inmobiliarios y el impuesto de
// sellos varían por provincia y cambian por normativa: un número traído de
// fábrica daría un resultado con apariencia de autoridad que puede estar mal
// por mucho, en una operación de cientos de miles de dólares.

type Modo = "compra" | "venta";

export function OperationCostsCalculator() {
  const [modo, setModo] = useState<Modo>("compra");
  const [moneda, setMoneda] = useState<Moneda>("USD");
  const [precio, setPrecio] = useState("");
  const [comision, setComision] = useState("");
  const [sellos, setSellos] = useState("");
  const [escritura, setEscritura] = useState("");
  const [fijos, setFijos] = useState("");

  const valorPrecio = parsearNumero(precio);
  const conceptos = {
    comisionFraccion: fraccionDesdePorcentaje(parsearNumero(comision)) ?? undefined,
    sellosFraccion: fraccionDesdePorcentaje(parsearNumero(sellos)) ?? undefined,
    escrituraFraccion: fraccionDesdePorcentaje(parsearNumero(escritura)) ?? undefined,
    montoFijo: parsearNumero(fijos) ?? undefined,
  };
  const r = costosDeOperacion(valorPrecio, conceptos);
  const dinero = (v: number) => formatearDinero(v, moneda);

  const supuestos = [
    parsearNumero(comision) !== null ? `Comisión del ${comision}%` : null,
    parsearNumero(sellos) !== null ? `Sellos del ${sellos}%` : null,
    parsearNumero(escritura) !== null ? `Escritura del ${escritura}%` : null,
    parsearNumero(fijos) !== null ? `Gastos fijos de ${dinero(parsearNumero(fijos) as number)}` : null,
  ].filter((s): s is string => s !== null);

  return (
    <div className="calc-layout">
      <form className="calc-form" onSubmit={(e) => e.preventDefault()}>
        <fieldset className="calc-modes">
          <legend>De qué lado estás</legend>
          <div className="calc-mode-options">
            <label className="check">
              <input type="radio" name="modo" checked={modo === "compra"} onChange={() => setModo("compra")} />
              Compro
            </label>
            <label className="check">
              <input type="radio" name="modo" checked={modo === "venta"} onChange={() => setModo("venta")} />
              Vendo
            </label>
          </div>
        </fieldset>

        <div className="calc-grid">
          <SelectorDeMoneda valor={moneda} onChange={setMoneda} />
          <CampoDinero etiqueta="Precio de la operación" moneda={moneda} valor={precio} onChange={setPrecio} />
          <CampoPorcentaje
            etiqueta="Comisión inmobiliaria"
            valor={comision}
            onChange={setComision}
            ayuda="Varía por provincia y se negocia. Preguntala."
          />
          <CampoPorcentaje
            etiqueta="Impuesto de sellos"
            valor={sellos}
            onChange={setSellos}
            ayuda="Depende de la provincia y de si es vivienda única."
          />
          <CampoPorcentaje
            etiqueta="Escritura"
            valor={escritura}
            onChange={setEscritura}
            ayuda="Honorarios del escribano."
          />
          <CampoDinero
            etiqueta="Otros gastos fijos"
            moneda={moneda}
            valor={fijos}
            onChange={setFijos}
            placeholder="Informes, certificados, gestoría"
          />
        </div>
      </form>

      <div className="calc-output">
        {!r.ok ? (
          <ResultadoPendiente
            falta={
              valorPrecio === null
                ? "Poné el precio de la operación y las alícuotas que te informaron."
                : mayuscula(r.motivo)
            }
          />
        ) : (
          <Resultado
            etiqueta={modo === "compra" ? "Vas a necesitar además del precio" : "Te van a descontar"}
            valor={dinero(r.valor.total)}
            nota={
              modo === "compra"
                ? `Total con la propiedad: ${dinero(r.valor.totalConPrecio)}`
                : `Te quedarían ${dinero((valorPrecio as number) - r.valor.total)}`
            }
            desglose={[
              { concepto: "Comisión", valor: dinero(r.valor.comision) },
              { concepto: "Sellos", valor: dinero(r.valor.sellos) },
              { concepto: "Escritura", valor: dinero(r.valor.escritura) },
              { concepto: "Gastos fijos", valor: dinero(r.valor.fijos) },
              { concepto: "Total de gastos", valor: dinero(r.valor.total), total: true },
            ]}
            formula={
              <>
                <p>
                  Cada alícuota se aplica sobre el precio y después se suman, más los gastos fijos.
                </p>
                <p>
                  Los conceptos son los mismos comprando y vendiendo; <strong>quién paga cada uno se
                  negocia</strong>, así que la herramienta no lo supone: ponés los que te correspondan.
                </p>
              </>
            }
            supuestos={supuestos.length ? supuestos : ["No cargaste ninguna alícuota todavía"]}
          />
        )}
        <AvisoDeCalculo />
      </div>
    </div>
  );
}

function mayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
