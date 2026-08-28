"use client";

import { useState } from "react";
import { cashFlowMensual, rentabilidadBruta, rentabilidadNeta } from "@/domain/finance";
import {
  formatearDinero,
  formatearPorcentaje,
  parsearNumero,
  type Moneda,
} from "@/lib/calculators/input";
import { CampoCantidad, CampoDinero, SelectorDeMoneda } from "./CalculatorFields";
import { AvisoDeCalculo, Resultado, ResultadoPendiente } from "./CalculatorResult";

// Rentabilidad de un alquiler: bruta, neta y flujo mensual.
//
// La bruta es la que todo el mundo cita y la que más engaña, porque ignora
// expensas, impuestos, mantenimiento, vacancia y los costos de compra. Se
// muestra igual —es el punto de comparación habitual— pero el número grande es
// la NETA, que es con la que se decide.
//
// La vacancia es el parámetro que más mueve el resultado y el que más se omite:
// un mes vacío se lleva el 8,3% del ingreso anual, y los gastos del propietario
// siguen corriendo esos meses.

export function YieldCalculator() {
  const [moneda, setMoneda] = useState<Moneda>("USD");
  const [precio, setPrecio] = useState("");
  const [alquiler, setAlquiler] = useState("");
  const [gastosMensuales, setGastosMensuales] = useState("");
  const [gastosAnuales, setGastosAnuales] = useState("");
  const [vacancia, setVacancia] = useState("");
  const [costosDeCompra, setCostosDeCompra] = useState("");
  const [cuota, setCuota] = useState("");

  const valores = {
    precio: parsearNumero(precio),
    alquilerMensual: parsearNumero(alquiler),
  };

  const parametros = {
    alquilerMensual: valores.alquilerMensual ?? 0,
    precio: valores.precio ?? 0,
    gastosMensuales: parsearNumero(gastosMensuales) ?? undefined,
    gastosAnuales: parsearNumero(gastosAnuales) ?? undefined,
    mesesVacanciaPorAnio: parsearNumero(vacancia) ?? undefined,
    costosDeCompra: parsearNumero(costosDeCompra) ?? undefined,
  };

  const faltanDatos = valores.precio === null || valores.alquilerMensual === null;
  const bruta = faltanDatos ? null : rentabilidadBruta(valores.alquilerMensual, valores.precio);
  const neta = faltanDatos ? null : rentabilidadNeta(parametros);
  const flujo = faltanDatos
    ? null
    : cashFlowMensual({ ...parametros, cuotaMensual: parsearNumero(cuota) ?? undefined });

  const dinero = (v: number) => formatearDinero(v, moneda);

  const supuestos = [
    parsearNumero(vacancia) !== null
      ? `${vacancia} ${parsearNumero(vacancia) === 1 ? "mes" : "meses"} de vacancia por año`
      : "Sin vacancia: asumís que se alquila los 12 meses",
    parsearNumero(gastosMensuales) !== null
      ? `Gastos mensuales a tu cargo de ${dinero(parsearNumero(gastosMensuales) as number)}`
      : "Sin gastos mensuales a tu cargo",
    parsearNumero(costosDeCompra) !== null
      ? `Costos de compra de ${dinero(parsearNumero(costosDeCompra) as number)}`
      : "La rentabilidad se calcula sobre el precio, sin sumar costos de compra",
  ];

  return (
    <div className="calc-layout">
      <form className="calc-form" onSubmit={(e) => e.preventDefault()}>
        <div className="calc-grid">
          <SelectorDeMoneda valor={moneda} onChange={setMoneda} />
          <CampoDinero etiqueta="Precio de la propiedad" moneda={moneda} valor={precio} onChange={setPrecio} />
          <CampoDinero etiqueta="Alquiler mensual" moneda={moneda} valor={alquiler} onChange={setAlquiler} />
          <CampoDinero
            etiqueta="Gastos mensuales a tu cargo"
            moneda={moneda}
            valor={gastosMensuales}
            onChange={setGastosMensuales}
            placeholder="Expensas, ABL, seguro"
          />
          <CampoDinero
            etiqueta="Gastos anuales"
            moneda={moneda}
            valor={gastosAnuales}
            onChange={setGastosAnuales}
            placeholder="Impuestos, mantenimiento"
          />
          <CampoCantidad
            etiqueta="Meses vacíos por año"
            valor={vacancia}
            onChange={setVacancia}
            limite={{ min: 0, max: 12 }}
            ayuda="Es lo que más mueve el resultado y lo que más se olvida."
          />
          <CampoDinero
            etiqueta="Costos de compra"
            moneda={moneda}
            valor={costosDeCompra}
            onChange={setCostosDeCompra}
            placeholder="Comisión, sellos, escritura"
          />
          <CampoDinero
            etiqueta="Cuota del crédito"
            moneda={moneda}
            valor={cuota}
            onChange={setCuota}
            placeholder="Si la comprás financiada"
          />
        </div>
      </form>

      <div className="calc-output">
        {faltanDatos || !neta?.ok ? (
          <ResultadoPendiente
            falta={
              faltanDatos
                ? "Poné el precio y el alquiler mensual para ver la rentabilidad."
                : mayuscula((neta as { ok: false; motivo: string }).motivo)
            }
          />
        ) : (
          <Resultado
            etiqueta="Rentabilidad neta anual"
            valor={formatearPorcentaje(neta.valor)}
            nota={neta.valor < 0 ? "Negativa: los gastos superan al ingreso" : undefined}
            desglose={[
              ...(bruta?.ok ? [{ concepto: "Rentabilidad bruta", valor: formatearPorcentaje(bruta.valor) }] : []),
              { concepto: "Rentabilidad neta", valor: formatearPorcentaje(neta.valor), total: true },
              ...(flujo?.ok
                ? [{
                    concepto: parsearNumero(cuota) !== null ? "Flujo mensual con la cuota" : "Flujo mensual",
                    valor: dinero(flujo.valor),
                  }]
                : []),
            ]}
            formula={
              <>
                <p>
                  <strong>Bruta:</strong> alquiler de doce meses sobre el precio. Es la que se cita
                  siempre y la que más engaña, porque ignora todo lo demás.
                </p>
                <p>
                  <strong>Neta:</strong> el ingreso de los meses que se cobran, menos los gastos de
                  los doce, sobre precio más costos de compra. Los gastos corren también los meses
                  vacíos —las expensas de un departamento vacío las paga el dueño—, y omitirlo
                  sobrestima la renta.
                </p>
                <p>
                  <strong>Flujo mensual:</strong> lo mismo mes a mes, restando la cuota. Puede dar
                  negativo, y ése es justamente el número que conviene mirar antes de comprar.
                </p>
              </>
            }
            supuestos={supuestos}
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
