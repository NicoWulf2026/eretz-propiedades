import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ViewModeSelector } from "./ViewModeSelector";

describe("ViewModeSelector", () => {
  it("expone sólo las tres vistas V2 con estado accesible", () => {
    const onChange = vi.fn();
    render(<ViewModeSelector mode="balanced" onChange={onChange} />);

    const combined = screen.getByRole("button", { name: "Mapa + propiedades" });
    const properties = screen.getByRole("button", { name: "Solo propiedades" });
    const map = screen.getByRole("button", { name: "Solo mapa" });
    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(combined).toHaveAttribute("aria-pressed", "true");
    expect(properties).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(map);
    expect(onChange).toHaveBeenCalledWith("map_only");
  });
});
