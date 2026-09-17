"use client";

import { useState } from "react";
import { capacidadDeCompra, relacionCuotaIngreso, resumenCredito } from "@/domain/finance";
import {
  formatearDinero,
  formatearPorcentaje,
  fraccionDesdePorcentaje,
  parsearNumero,
  type Moneda,
} from "@/lib/calculators/input";
import { CampoCantidad, CampoDinero, CampoPorcentaje, SelectorDeMoneda } from "./CalculatorFields";
import { AvisoDeCalculo, Resultado, ResultadoPendiente } from "./CalculatorResult";

// Cuota hipotecaria y capacidad de compra: la misma pantalla en los dos
// sentidos. Comparten los campos de tasa y plazo, y `capacidadDeCompra` es la
// inversa exacta de `cuotaHipotecaria` —hay un test que cierra el círculo—, así
// que separarlas en dos pantallas duplicaría el formulario para nada.
//
// LA TASA NO TIENE VALOR POR DEFECTO. Ninguna. Poner un número "razonable"
// daría un resultado con apariencia de autoridad que puede estar mal por un
// factor grande, y quien lo lee no tendría forma de saberlo.

type Modo = "cuota" | "capacidad";

const PLAZOS = [
  { meses: 60, etiqueta: "5 años" },
  { meses: 120, etiqueta: "10 años" },
  { meses: 180, etiqueta: "15 años" },
  { meses: 240, etiqueta: "20 años" },
  { meses: 360, etiqueta: "30 años" },
];

export function MortgageCalculator() {
  const [modo, setModo] = useState<Modo>("cuota");
  const [moneda, setMoneda] = useState<Moneda>("USD");
  const [capital, setCapital] = useState("");
  const [cuotaMaxima, setCuotaMaxima] = useState("");
  const [tasa, setTasa] = useState("");
  const [meses, setMeses] = useState("240");
  const [ingreso, setIngreso] = useState("");

  const tasaAnual = fraccionDesdePorcentaje(parsearNumero(tasa));
  const plazo = parsearNumero(meses);
  const ingresoMensual = parsearNumero(ingreso);

  const dinero = (v: number) => formatearDinero(v, moneda);

  return (
    <div className="calc-layout">
      <form className="calc-form" onSubmit={(e) => e.preventDefault()}>
        <fieldset className="calc-modes">
          <legend>Qué querés calcular</legend>
          <div className="calc-mode-options">
            <label className="check">
              <input type="radio" name="modo" checked={modo === "cuota"} onChange={() => setModo("cuota")} />
              Sé cuánto quiero pedir
            </label>
            <label className="check">
              <input type="radio" name="modo" checked={modo === "capacidad"} onChange={() => setModo("capacidad")} />
              Sé cuánto puedo pagar por mes
            </label>
          </div>
        </fieldset>

        <div className="calc-grid">
          <SelectorDeMoneda valor={moneda} onChange={setMoneda} />

          {modo === "cuota" ? (
            <CampoDinero
              etiqueta="Monto del préstamo"
              moneda={moneda}
              valor={capital}
              onChange={setCapital}
              placeholder="Sin contar el anticipo"
            />
          ) : (
            <CampoDinero
              etiqueta="Cuota que podés pagar"
              moneda={moneda}
              valor={cuotaMaxima}
              onChange={setCuotaMaxima}
              placeholder="Por mes"
            />
          )}

          <CampoPorcentaje
            etiqueta="Tasa nominal anual"
            valor={tasa}
            onChange={setTasa}
            placeholder="La que te ofrece el banco"
            ayuda="No traemos ninguna tasa: consultala y escribila acá."
          />

          <label className="field calc-field">
            <span>Plazo</span>
            <select value={meses} onChange={(e) => setMeses(e.target.value)}>
              {PLAZOS.map((p) => (
                <option key={p.meses} value={p.meses}>{p.etiqueta}</option>
              ))}
            </select>
          </label>

          <CampoCantidad
            etiqueta="Tu ingreso mensual (opcional)"
            valor={ingreso}
            onChange={setIngreso}
            placeholder="Para ver qué parte se lleva la cuota"
          />
        </div>
      </form>

      <div className="calc-output">
        {modo === "cuota"
          ? <SalidaCuota
              capital={parsearNumero(capital)}
              tasaAnual={tasaAnual}
              meses={plazo}
              ingresoMensual={ingresoMensual}
              dinero={dinero}
              tasaTexto={tasa}
            />
          : <SalidaCapacidad
              cuotaMaxima={parsearNumero(cuotaMaxima)}
              tasaAnual={tasaAnual}
              meses={plazo}
              dinero={dinero}
              tasaTexto={tasa}
            />}
        <AvisoDeCalculo />
      </div>
    </div>
  );
}

function supuestosComunes(tasaAnual: number, meses: number): string[] {
  return [
    `Tasa nominal anual del ${formatearPorcentaje(tasaAnual)}`,
    `Plazo de ${meses} meses`,
    "Cuota fija por sistema francés, sin ajuste por inflación",
  ];
}

function FormulaFrances() {
  return (
    <>
      <p>
        Sistema francés, el de cuota constante: <code>cuota = C · i / (1 − (1+i)<sup>−n</sup>)</code>,
        donde <code>C</code> es el capital, <code>i</code> la tasa mensual y <code>n</code> la cantidad de meses.
      </p>
      <p>
        La tasa mensual se toma como la anual dividida 12, que es la convención con la que
        los bancos publican la TNA. Si te dieron una TEA, convertila antes.
      </p>
    </>
  );
}

function SalidaCuota({
  capital,
  tasaAnual,
  meses,
  ingresoMensual,
  dinero,
  tasaTexto,
}: {
  capital: number | null;
  tasaAnual: number | null;
  meses: number | null;
  ingresoMensual: number | null;
  dinero: (v: number) => string;
  tasaTexto: string;
}) {
  if (capital === null || tasaAnual === null || meses === null) {
    return <ResultadoPendiente falta="Completá el monto, la tasa y el plazo para ver la cuota." />;
  }

  const r = resumenCredito({ capital, tasaAnual, meses });
  if (!r.ok) return <ResultadoPendiente falta={mayuscula(r.motivo)} />;

  const relacion = ingresoMensual !== null ? relacionCuotaIngreso(r.valor.cuota, ingresoMensual) : null;

  return (
    <Resultado
      etiqueta="Cuota mensual"
      valor={dinero(r.valor.cuota)}
      nota={`Durante ${meses} meses`}
      desglose={[
        { concepto: "Capital que pedís", valor: dinero(capital) },
        { concepto: "Intereses totales", valor: dinero(r.valor.interesesTotales) },
        { concepto: "Total que devolvés", valor: dinero(r.valor.totalPagado), total: true },
        ...(relacion?.ok
          ? [{ concepto: "La cuota se lleva", valor: formatearPorcentaje(relacion.valor) + " de tu ingreso" }]
          : []),
      ]}
      formula={<FormulaFrances />}
      supuestos={[
        ...supuestosComunes(tasaAnual, meses),
        `Escribiste ${tasaTexto}% como tasa; no la trajimos de ningún lado`,
      ]}
    />
  );
}

function SalidaCapacidad({
  cuotaMaxima,
  tasaAnual,
  meses,
  dinero,
  tasaTexto,
}: {
  cuotaMaxima: number | null;
  tasaAnual: number | null;
  meses: number | null;
  dinero: (v: number) => string;
  tasaTexto: string;
}) {
  if (cuotaMaxima === null || tasaAnual === null || meses === null) {
    return <ResultadoPendiente falta="Completá la cuota, la tasa y el plazo para ver cuánto podrías pedir." />;
  }

  const r = capacidadDeCompra({ cuotaMaxima, tasaAnual, meses });
  if (!r.ok) return <ResultadoPendiente falta={mayuscula(r.motivo)} />;

  return (
    <Resultado
      etiqueta="Podrías pedir hasta"
      valor={dinero(r.valor)}
      nota="Es el capital del préstamo, no el precio de la propiedad"
      desglose={[
        { concepto: "Cuota que podés pagar", valor: dinero(cuotaMaxima) },
        { concepto: "Total que devolverías", valor: dinero(cuotaMaxima * meses), total: true },
      ]}
      formula={
        <>
          <p>
            Es la inversa de la cuota: <code>C = cuota · (1 − (1+i)<sup>−n</sup>) / i</code>.
          </p>
          <p>
            <strong>Da el capital del préstamo, no lo que podés gastar.</strong> Al precio de la
            propiedad hay que sumarle tu anticipo, y de ese anticipo una parte se va en escritura
            y sellos: no todo entra en la compra.
          </p>
        </>
      }
      supuestos={[
        ...supuestosComunes(tasaAnual, meses),
        `Escribiste ${tasaTexto}% como tasa; no la trajimos de ningún lado`,
      ]}
    />
  );
}

function mayuscula(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}
