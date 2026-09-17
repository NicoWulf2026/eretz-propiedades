"use client";

// Campos de las calculadoras.
//
// Se apoyan en `.field` de `globals.css`, que ya define etiqueta, control,
// foco y estados. No se crea un sistema de formularios paralelo: lo que falta
// acá es sólo el comportamiento numérico y el mensaje de error.
//
// Todos los campos son controlados por STRING, no por número. Con un número, un
// campo vacío tendría que representarse con 0 o con NaN, y las dos opciones son
// peores: 0 hace que la calculadora devuelva un resultado equivocado con aire
// de válido, y NaN se propaga en silencio.

import { useId } from "react";
import {
  esEntradaNumericaParcial,
  parsearNumero,
  problemaDeValor,
  type Limite,
  type Moneda,
} from "@/lib/calculators/input";

export type CampoNumerico = {
  valor: string;
  onChange: (valor: string) => void;
};

type BaseProps = CampoNumerico & {
  etiqueta: string;
  /** Texto de apoyo bajo el campo. Para explicar un supuesto, no para rellenar. */
  ayuda?: string;
  limite?: Limite;
  placeholder?: string;
};

/** Sólo deja escribir lo que puede llegar a ser un número. */
function alEscribir(onChange: (v: string) => void) {
  return (event: React.ChangeEvent<HTMLInputElement>) => {
    const siguiente = event.target.value;
    if (esEntradaNumericaParcial(siguiente)) onChange(siguiente);
  };
}

function Campo({
  etiqueta,
  ayuda,
  valor,
  onChange,
  limite,
  placeholder,
  sufijo,
  prefijo,
}: BaseProps & { sufijo?: React.ReactNode; prefijo?: React.ReactNode }) {
  const id = useId();
  const ayudaId = `${id}-ayuda`;
  const errorId = `${id}-error`;
  const problema = problemaDeValor(parsearNumero(valor), limite);

  return (
    <label className="field calc-field" htmlFor={id}>
      <span>{etiqueta}</span>
      <span className="calc-control">
        {prefijo ? <span className="calc-affix" aria-hidden="true">{prefijo}</span> : null}
        <input
          id={id}
          type="text"
          inputMode="decimal"
          autoComplete="off"
          value={valor}
          placeholder={placeholder}
          onChange={alEscribir(onChange)}
          aria-invalid={problema ? true : undefined}
          aria-describedby={[ayuda ? ayudaId : null, problema ? errorId : null].filter(Boolean).join(" ") || undefined}
        />
        {sufijo ? <span className="calc-affix" aria-hidden="true">{sufijo}</span> : null}
      </span>
      {problema ? (
        // `role="alert"` para que un lector de pantalla lo anuncie al aparecer:
        // un error que sólo se ve no existe para quien no mira.
        <span id={errorId} className="calc-error" role="alert">{problema}</span>
      ) : ayuda ? (
        <span id={ayudaId} className="calc-help">{ayuda}</span>
      ) : null}
    </label>
  );
}

/** Importe. El prefijo muestra la moneda elegida, sin convertir nada. */
export function CampoDinero({ moneda, ...props }: BaseProps & { moneda: Moneda }) {
  return <Campo {...props} prefijo={moneda} limite={{ min: 0, ...props.limite }} />;
}

/**
 * Porcentaje. La persona escribe 8; quien llama recibe 8 y convierte con
 * `fraccionDesdePorcentaje`. El componente NO divide por cien: si lo hiciera
 * acá y también en el cálculo, el error sería invisible.
 */
export function CampoPorcentaje(props: BaseProps) {
  return <Campo {...props} sufijo="%" limite={{ min: 0, max: 100, ...props.limite }} />;
}

export function CampoCantidad(props: BaseProps & { sufijo?: string }) {
  return <Campo {...props} limite={{ min: 0, ...props.limite }} />;
}

export function CampoSuperficie(props: BaseProps) {
  return <Campo {...props} sufijo="m²" limite={{ min: 0, ...props.limite }} />;
}

/** Selector de moneda. Dos opciones: no hay conversión entre ellas. */
export function SelectorDeMoneda({
  valor,
  onChange,
  etiqueta = "Moneda",
}: {
  valor: Moneda;
  onChange: (m: Moneda) => void;
  etiqueta?: string;
}) {
  const id = useId();
  return (
    <label className="field calc-field" htmlFor={id}>
      <span>{etiqueta}</span>
      <select id={id} value={valor} onChange={(e) => onChange(e.target.value as Moneda)}>
        <option value="USD">Dólares (USD)</option>
        <option value="ARS">Pesos (ARS)</option>
      </select>
    </label>
  );
}
