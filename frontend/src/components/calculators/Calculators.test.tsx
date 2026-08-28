import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { OperationCostsCalculator } from "./OperationCostsCalculator";
import { PricePerM2Calculator } from "./PricePerM2Calculator";
import { YieldCalculator } from "./YieldCalculator";

function escribir(etiqueta: RegExp, valor: string) {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

/**
 * El valor principal del resultado.
 *
 * Hace falta apuntar al elemento y no al texto: el mismo porcentaje aparece a
 * la vez como cifra principal y como linea del desglose, y `getByText` no sabria
 * cual de los dos se esta afirmando.
 */
function valorPrincipal(container: HTMLElement): string {
  return container.querySelector(".calc-result-value")?.textContent ?? "";
}

/** La etiqueta del resultado, por el mismo motivo que `valorPrincipal`. */
function etiquetaResultado(container: HTMLElement): string {
  return container.querySelector(".calc-result-label")?.textContent ?? "";
}

describe("precio por m²", () => {
  it("calcula la división", () => {
    const { container } = render(<PricePerM2Calculator />);
    escribir(/precio/i, "100000");
    escribir(/superficie/i, "50");
    expect(valorPrincipal(container)).toBe("USD 2.000");
  });

  it("hace explícito qué superficie se usó", () => {
    // El m² cubierto de un departamento no se compara con el m² total de una
    // casa con jardín: si no se dice cuál es, el número es incomparable.
    const { container } = render(<PricePerM2Calculator />);
    escribir(/precio/i, "100000");
    escribir(/superficie/i, "50");
    expect(etiquetaResultado(container)).toBe("Precio por m² total");

    fireEvent.click(screen.getByLabelText(/^cubierta$/i));
    expect(etiquetaResultado(container)).toBe("Precio por m² cubierto");
  });

  it("no divide por cero: pide los datos", () => {
    render(<PricePerM2Calculator />);
    escribir(/precio/i, "100000");
    escribir(/superficie/i, "0");
    expect(screen.getByText(/completá el precio y la superficie/i)).toBeInTheDocument();
  });
});

describe("gastos de una operación", () => {
  it("suma alícuotas y gastos fijos", () => {
    const { container } = render(<OperationCostsCalculator />);
    escribir(/precio de la operación/i, "100000");
    escribir(/comisión inmobiliaria/i, "3");
    escribir(/impuesto de sellos/i, "1,8");
    escribir(/escritura/i, "2");
    escribir(/otros gastos fijos/i, "500");
    // 3000 + 1800 + 2000 + 500
    expect(valorPrincipal(container)).toBe("USD 7.300");
  });

  it("no trae ninguna alícuota cargada", () => {
    // Varían por provincia y cambian por normativa.
    render(<OperationCostsCalculator />);
    for (const campo of [/comisión inmobiliaria/i, /impuesto de sellos/i, /escritura/i]) {
      expect(screen.getByLabelText(campo)).toHaveValue("");
    }
  });

  it("cambia la lectura entre comprar y vender sin cambiar los conceptos", () => {
    render(<OperationCostsCalculator />);
    escribir(/precio de la operación/i, "100000");
    escribir(/comisión inmobiliaria/i, "3");
    expect(screen.getByText(/vas a necesitar además del precio/i)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/^vendo$/i));
    expect(screen.getByText(/te van a descontar/i)).toBeInTheDocument();
    expect(screen.getByText(/te quedarían/i)).toBeInTheDocument();
  });

  it("avisa cuando todavía no se cargó ninguna alícuota", () => {
    render(<OperationCostsCalculator />);
    escribir(/precio de la operación/i, "100000");
    expect(screen.getByText(/no cargaste ninguna alícuota/i)).toBeInTheDocument();
  });
});

describe("rentabilidad", () => {
  it("calcula la neta y muestra también la bruta", () => {
    const { container } = render(<YieldCalculator />);
    escribir(/precio de la propiedad/i, "100000");
    escribir(/alquiler mensual/i, "500");
    // 500 × 12 / 100.000 = 6%. Sin gastos, neta y bruta coinciden.
    expect(valorPrincipal(container)).toBe("6,0%");
    expect(screen.getByText(/rentabilidad bruta/i)).toBeInTheDocument();
  });

  it("la vacancia baja el resultado y los gastos siguen corriendo", () => {
    const { container } = render(<YieldCalculator />);
    escribir(/precio de la propiedad/i, "100000");
    escribir(/alquiler mensual/i, "500");
    escribir(/gastos mensuales a tu cargo/i, "100");
    // Sin vacancia: (500 × 12 − 100 × 12) / 100.000 = 4,8%
    expect(valorPrincipal(container)).toBe("4,8%");

    escribir(/meses vacíos por año/i, "1");
    // Un mes vacío: se cobran 11 meses pero se pagan 12 de gastos.
    // (500 × 11 − 100 × 12) / 100.000 = 4,3%
    expect(valorPrincipal(container)).toBe("4,3%");
  });

  it("muestra una rentabilidad negativa como negativa", () => {
    // Es un resultado válido y es el que conviene ver antes de comprar.
    render(<YieldCalculator />);
    escribir(/precio de la propiedad/i, "100000");
    escribir(/alquiler mensual/i, "100");
    escribir(/gastos mensuales a tu cargo/i, "300");
    expect(screen.getByText(/los gastos superan al ingreso/i)).toBeInTheDocument();
  });

  it("declara la vacancia asumida cuando no se completó", () => {
    // Omitirla en silencio sobrestimaría la renta.
    render(<YieldCalculator />);
    escribir(/precio de la propiedad/i, "100000");
    escribir(/alquiler mensual/i, "500");
    expect(screen.getByText(/asumís que se alquila los 12 meses/i)).toBeInTheDocument();
  });

  it("rechaza más de doce meses de vacancia", () => {
    render(<YieldCalculator />);
    escribir(/meses vacíos por año/i, "15");
    expect(screen.getByRole("alert")).toHaveTextContent(/12 o menos/i);
  });
});

describe("todas avisan que son estimaciones", () => {
  it.each([
    ["precio por m²", <PricePerM2Calculator key="a" />],
    ["gastos", <OperationCostsCalculator key="b" />],
    ["rentabilidad", <YieldCalculator key="c" />],
  ])("%s", (_nombre, componente) => {
    render(componente);
    expect(screen.getByText(/no es una oferta/i)).toBeInTheDocument();
  });
});
