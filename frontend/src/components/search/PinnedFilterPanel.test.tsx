import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FilterForm } from "@/components/search/FilterForm";
import { parsePropertyFilters } from "@/lib/property-query";

// Fase C/D: el mismo FilterForm se reutiliza en modal y fijado (sin duplicar).
describe("FilterForm — panel fijable y modo Análisis", () => {
  it("el parser acepta el modo 'analysis' y cae a 'balanced' si es inválido", () => {
    expect(parsePropertyFilters({ modo: "analysis" }).mode).toBe("analysis");
    expect(parsePropertyFilters({ modo: "inexistente" }).mode).toBe("balanced");
  });

  it("fijado: muestra el CTA de conteo y 'Desfijar' (llama onUnpin)", () => {
    const onUnpin = vi.fn();
    render(<FilterForm filters={parsePropertyFilters({ modo: "analysis" })} pinned onUnpin={onUnpin} />);
    expect(screen.getByText("Filtros fijados")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Calculando resultados|Ver .* propiedades|Aplicar filtros/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Desfijar" }));
    expect(onUnpin).toHaveBeenCalledOnce();
  });

  it("modal: 'Fijar panel' invoca onPin", () => {
    const onPin = vi.fn();
    const { container } = render(<FilterForm filters={parsePropertyFilters({})} onPin={onPin} />);
    fireEvent.click(container.querySelector('[aria-controls="advanced-filters"]') as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Fijar panel" }));
    expect(onPin).toHaveBeenCalledOnce();
  });

  it("fijado: reutiliza los mismos campos avanzados sin abrir modal", () => {
    render(<FilterForm filters={parsePropertyFilters({})} pinned />);
    expect(screen.getByText("Provincia")).toBeInTheDocument();
    expect(screen.getByText("Superficie total mín.")).toBeInTheDocument();
    expect(screen.getByText("Cocheras mín.")).toBeInTheDocument();
  });
});
