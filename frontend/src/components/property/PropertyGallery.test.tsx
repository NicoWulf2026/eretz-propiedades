import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PropertyGallery } from "@/components/property/PropertyGallery";

describe("PropertyGallery", () => {
  it("renders a meaningful empty state", () => {
    render(<PropertyGallery images={[]} title="Casa" />);
    expect(screen.getByRole("img", { name: "Esta publicación no incluye fotos" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("falls back when an image is broken", () => {
    render(<PropertyGallery images={["https://images.example.invalid/broken.jpg"]} title="Casa" />);
    fireEvent.error(screen.getByRole("img", { name: "Casa, imagen 1" }));
    expect(screen.getByRole("img", { name: "Imagen no disponible" })).toBeInTheDocument();
  });

  it("supports modal navigation, Escape and focus restoration", () => {
    render(<PropertyGallery images={["https://img.test/1.jpg", "https://img.test/2.jpg"]} title="Casa" />);
    const opener = screen.getByRole("button", { name: "Ampliar imagen" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("dialog", { name: "Galería de fotos" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar galería" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "ArrowRight" });
    expect(screen.getByText("Foto 2 de 2")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("traps keyboard focus inside the lightbox", () => {
    render(<PropertyGallery images={["https://img.test/1.jpg", "https://img.test/2.jpg"]} title="Casa" />);
    fireEvent.click(screen.getByRole("button", { name: "Ampliar imagen" }));
    const close = screen.getByRole("button", { name: "Cerrar galería" });
    const next = screen.getByRole("button", { name: "Ver foto siguiente" });
    next.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(next).toHaveFocus();
  });
});
