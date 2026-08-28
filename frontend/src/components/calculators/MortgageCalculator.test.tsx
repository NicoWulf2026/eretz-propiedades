import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MortgageCalculator } from "./MortgageCalculator";

function escribir(etiqueta: RegExp, valor: string) {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
}

describe("cuota hipotecaria de punta a punta", () => {
  it("escribir 6 como tasa da la cuota correcta, no una cien veces mayor", () => {
    // El anclaje canónico del sistema francés: USD 100.000 al 6% a 30 años son
    // USD 599,55. Este test recorre el camino completo —input de texto,
    // conversión de porcentaje a fracción, cálculo, formateo— porque es
    // exactamente donde un factor de cien pasaría inadvertido.
    render(<MortgageCalculator />);
    escribir(/monto del préstamo/i, "100000");
    escribir(/tasa nominal anual/i, "6");
    fireEvent.change(screen.getByLabelText(/plazo/i), { target: { value: "360" } });

    expect(screen.getByText("USD 599,55")).toBeInTheDocument();
  });

  it("muestra intereses y total, no sólo la cuota", () => {
    render(<MortgageCalculator />);
    escribir(/monto del préstamo/i, "100000");
    escribir(/tasa nominal anual/i, "6");
    fireEvent.change(screen.getByLabelText(/plazo/i), { target: { value: "360" } });

    // A 30 años al 6% se pagan más intereses que capital.
    expect(screen.getByText("Intereses totales")).toBeInTheDocument();
    expect(screen.getByText("Total que devolvés")).toBeInTheDocument();
  });

  it("no trae ninguna tasa cargada", () => {
    // Un número "razonable" daría un resultado con apariencia de autoridad que
    // puede estar mal por mucho.
    render(<MortgageCalculator />);
    expect(screen.getByLabelText(/tasa nominal anual/i)).toHaveValue("");
    expect(screen.getByLabelText(/monto del préstamo/i)).toHaveValue("");
  });

  it("pide los datos que faltan en vez de mostrar un número", () => {
    render(<MortgageCalculator />);
    expect(screen.getByText(/completá el monto, la tasa y el plazo/i)).toBeInTheDocument();
  });

  it("sigue sin mostrar resultado si falta la tasa", () => {
    render(<MortgageCalculator />);
    escribir(/monto del préstamo/i, "100000");
    expect(screen.getByText(/completá el monto, la tasa y el plazo/i)).toBeInTheDocument();
  });

  it("declara los supuestos con los que calculó", () => {
    render(<MortgageCalculator />);
    escribir(/monto del préstamo/i, "100000");
    escribir(/tasa nominal anual/i, "6");
    expect(screen.getByText(/supuestos que ingresaste/i)).toBeInTheDocument();
    expect(screen.getByText(/no la trajimos de ningún lado/i)).toBeInTheDocument();
  });

  it("nunca presenta el resultado como una oferta", () => {
    render(<MortgageCalculator />);
    expect(screen.getByText(/no es una oferta/i)).toBeInTheDocument();
  });
});

describe("validación de entrada", () => {
  it("no deja escribir letras", () => {
    render(<MortgageCalculator />);
    const campo = screen.getByLabelText(/monto del préstamo/i);
    fireEvent.change(campo, { target: { value: "abc" } });
    expect(campo).toHaveValue("");
  });

  it("marca un porcentaje imposible y lo anuncia", () => {
    render(<MortgageCalculator />);
    escribir(/tasa nominal anual/i, "500");
    const error = screen.getByRole("alert");
    expect(error).toHaveTextContent(/100 o menos/i);
    expect(screen.getByLabelText(/tasa nominal anual/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("marca un importe negativo", () => {
    render(<MortgageCalculator />);
    escribir(/monto del préstamo/i, "-100");
    expect(screen.getByRole("alert")).toHaveTextContent(/no puede ser negativo/i);
  });

  it("acepta coma decimal", () => {
    render(<MortgageCalculator />);
    escribir(/tasa nominal anual/i, "6,5");
    expect(screen.getByLabelText(/tasa nominal anual/i)).toHaveValue("6,5");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("capacidad de compra", () => {
  it("cierra el círculo con la cuota", () => {
    // Si 100.000 al 6% a 30 años da 599,55, entonces 599,55 al 6% a 30 años
    // tiene que devolver ~100.000. Si el círculo no cierra, una de las dos está
    // mal y las dos parecen razonables por separado.
    render(<MortgageCalculator />);
    fireEvent.click(screen.getByLabelText(/sé cuánto puedo pagar por mes/i));
    escribir(/cuota que podés pagar/i, "599,55");
    escribir(/tasa nominal anual/i, "6");
    fireEvent.change(screen.getByLabelText(/plazo/i), { target: { value: "360" } });

    expect(screen.getByText(/USD 100\.00[01]/)).toBeInTheDocument();
  });

  it("aclara que es el capital del préstamo y no lo que se puede gastar", () => {
    render(<MortgageCalculator />);
    fireEvent.click(screen.getByLabelText(/sé cuánto puedo pagar por mes/i));
    escribir(/cuota que podés pagar/i, "600");
    escribir(/tasa nominal anual/i, "6");
    expect(screen.getByText(/no el precio de la propiedad/i)).toBeInTheDocument();
  });
});
