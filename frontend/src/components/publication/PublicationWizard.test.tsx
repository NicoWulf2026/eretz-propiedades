import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CLAVE_BORRADOR, DRAFT_VERSION } from "@/lib/publication/draft-storage";
import { PublicationWizard } from "./PublicationWizard";

/** Completa un paso y avanza. */
function completar(campos: Array<[RegExp, string]>) {
  for (const [etiqueta, valor] of campos) {
    fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });
  }
}

const continuar = () => fireEvent.click(screen.getByRole("button", { name: /continuar$/i }));

/**
 * Carga una foto de mentira.
 *
 * Hace falta porque el dominio exige al menos una imagen para publicar, asi que
 * el paso de fotos BLOQUEA el avance: no es opcional.
 */
function cargarFoto(nombre = "frente.jpg") {
  const archivo = new File(["contenido"], nombre, { type: "image/jpeg" });
  fireEvent.change(screen.getByLabelText(/elegí las fotos/i), { target: { files: [archivo] } });
}

/** Recorre el wizard hasta la revisión con un borrador válido. */
function completarTodo() {
  fireEvent.click(screen.getByLabelText(/^venta$/i));
  completar([[/tipo de propiedad/i, "departamento"]]);
  continuar();

  completar([[/provincia/i, "Santa Fe"], [/ciudad/i, "Rosario"]]);
  continuar();

  fireEvent.click(screen.getByLabelText(/con un monto/i));
  completar([[/^monto$/i, "85000"]]);
  continuar();

  completar([[/ambientes/i, "2"], [/dormitorios/i, "1"]]);
  continuar();

  completar([[/^título$/i, "Departamento de 2 ambientes en Rosario centro"]]);
  // Por rol y no por etiqueta: la <section> del paso se llama igual que el
  // campo, porque se etiqueta con el título del paso.
  fireEvent.change(screen.getByRole("textbox", { name: /descripción/i }), {
    target: { value: "Luminoso, con balcón al frente y cocina separada. A dos cuadras del río." },
  });
  continuar();

  // Al menos una foto es obligatoria: el validador del dominio la exige.
  cargarFoto();
  continuar();

  completar([[/^teléfono$/i, "3410000000"]]);
  fireEvent.click(screen.getByLabelText(/autorizado a publicar/i));
  continuar();
}

beforeEach(() => {
  window.localStorage.clear();
  // jsdom no implementa estas dos.
  URL.createObjectURL = vi.fn(() => `blob:${Math.random().toString(36).slice(2)}`);
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => window.localStorage.clear());

describe("no promete lo que no puede cumplir", () => {
  it("dice que el borrador es de este dispositivo, no de una cuenta", () => {
    render(<PublicationWizard />);
    expect(screen.getByText(/borrador en este dispositivo/i)).toBeInTheDocument();
    expect(screen.queryByText(/guardado en tu cuenta/i)).toBeNull();
  });

  it("no hay botón de publicar, porque no hay dónde guardar", () => {
    render(<PublicationWizard />);
    completarTodo();
    expect(screen.queryByRole("button", { name: /^publicar$/i })).toBeNull();
    expect(screen.getByText(/falta conectar el guardado/i)).toBeInTheDocument();
  });

  it("llega hasta 'listo para publicar' y se detiene ahí", () => {
    render(<PublicationWizard />);
    completarTodo();
    expect(screen.getByText(/listo para publicar/i)).toBeInTheDocument();
  });
});

describe("validación por paso", () => {
  it("no deja avanzar sin los datos del paso", () => {
    render(<PublicationWizard />);
    continuar();
    // Sigue en el primer paso.
    expect(screen.getByRole("heading", { name: "Qué publicás" })).toBeInTheDocument();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
  });

  it("el error desaparece al corregir el campo", () => {
    render(<PublicationWizard />);
    continuar();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "casa"]]);
    expect(screen.queryAllByRole("alert")).toHaveLength(0);
  });

  it("avanza cuando el paso está completo", () => {
    render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "departamento"]]);
    continuar();
    expect(screen.getByRole("heading", { name: "Dónde está" })).toBeInTheDocument();
  });

  it("volver no pierde lo cargado", () => {
    render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "casa"]]);
    continuar();
    fireEvent.click(screen.getByRole("button", { name: /volver/i }));
    expect(screen.getByLabelText(/tipo de propiedad/i)).toHaveValue("casa");
  });
});

describe("precio", () => {
  function llegarAPrecio() {
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "departamento"]]);
    continuar();
    completar([[/provincia/i, "Santa Fe"], [/ciudad/i, "Rosario"]]);
    continuar();
  }

  it("'a consultar' es una decisión, no un campo vacío", () => {
    render(<PublicationWizard />);
    llegarAPrecio();
    fireEvent.click(screen.getByLabelText(/a consultar/i));
    // Con "a consultar" no hay campo de monto: no se pide un número que no aplica.
    expect(screen.queryByLabelText(/^monto$/i)).toBeNull();
    continuar();
    expect(screen.getByRole("heading", { name: "Características" })).toBeInTheDocument();
  });

  it("no deja avanzar sin decidir el precio", () => {
    render(<PublicationWizard />);
    llegarAPrecio();
    continuar();
    expect(screen.getByRole("heading", { name: "Precio" })).toBeInTheDocument();
  });

  it("acepta pesos y dólares sin convertir entre ellos", () => {
    render(<PublicationWizard />);
    llegarAPrecio();
    fireEvent.click(screen.getByLabelText(/con un monto/i));
    fireEvent.change(screen.getByLabelText(/moneda/i), { target: { value: "ARS" } });
    completar([[/^monto$/i, "95000000"]]);
    continuar();
    expect(screen.getByRole("heading", { name: "Características" })).toBeInTheDocument();
  });
});

describe("borrador local", () => {
  it("guarda al escribir y ofrece restaurarlo al volver", () => {
    const { unmount } = render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "casa"]]);
    // Al desmontar se guarda lo pendiente.
    unmount();

    render(<PublicationWizard />);
    expect(screen.getByText(/encontramos un borrador en este dispositivo/i)).toBeInTheDocument();
  });

  it("continuar el borrador recupera lo cargado", () => {
    const { unmount } = render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "casa"]]);
    unmount();

    render(<PublicationWizard />);
    fireEvent.click(screen.getByRole("button", { name: /continuar el borrador/i }));
    expect(screen.getByLabelText(/tipo de propiedad/i)).toHaveValue("casa");
  });

  it("empezar de cero lo descarta de verdad", () => {
    const { unmount } = render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    completar([[/tipo de propiedad/i, "casa"]]);
    unmount();

    render(<PublicationWizard />);
    fireEvent.click(screen.getByRole("button", { name: /empezar de cero/i }));
    expect(screen.getByLabelText(/tipo de propiedad/i)).toHaveValue("");
    expect(window.localStorage.getItem(CLAVE_BORRADOR)).toBeNull();
  });

  it("avisa que las fotos hay que volver a elegirlas", () => {
    const { unmount } = render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    unmount();
    render(<PublicationWizard />);
    expect(screen.getByText(/volver a elegirlas/i)).toBeInTheDocument();
  });

  it("no restaura un borrador de otra versión del formulario", () => {
    // Restaurar a medias es peor que no restaurar, porque parece que funcionó.
    window.localStorage.setItem(
      CLAVE_BORRADOR,
      JSON.stringify({ draftVersion: DRAFT_VERSION + 1, savedAt: 1, draft: {}, imageNames: [] }),
    );
    render(<PublicationWizard />);
    expect(screen.queryByText(/encontramos un borrador/i)).toBeNull();
    expect(window.localStorage.getItem(CLAVE_BORRADOR)).toBeNull();
  });

  it("no guarda las fotos en el almacenamiento", () => {
    const { unmount } = render(<PublicationWizard />);
    fireEvent.click(screen.getByLabelText(/^venta$/i));
    unmount();
    expect(window.localStorage.getItem(CLAVE_BORRADOR)).not.toContain("blob:");
  });
});

describe("revisión final", () => {
  it("separa lo que bloquea de lo que conviene mejorar", () => {
    render(<PublicationWizard />);
    completarTodo();
    // Con una sola foto la sugerencia aparece, pero no bloquea.
    expect(screen.getByRole("heading", { name: /podés mejorarla/i })).toBeInTheDocument();
    expect(screen.getByText(/no hace falta para publicar/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /falta corregir esto/i })).toBeNull();
  });

  it("NO muestra un puntaje de calidad", () => {
    // Un "82/100" invita a optimizar la métrica en vez de la publicación.
    render(<PublicationWizard />);
    completarTodo();
    expect(screen.queryByText(/\d+\s*\/\s*100/)).toBeNull();
    expect(screen.queryByText(/puntaje|score|calidad/i)).toBeNull();
  });

  it("permite volver a editar cada dato", () => {
    render(<PublicationWizard />);
    completarTodo();
    const editar = screen.getAllByRole("button", { name: /^editar$/i });
    expect(editar.length).toBeGreaterThan(5);

    fireEvent.click(editar[0]);
    expect(screen.getByRole("heading", { name: "Qué publicás" })).toBeInTheDocument();
  });

  it("resume lo cargado sin inventar valores", () => {
    render(<PublicationWizard />);
    completarTodo();
    expect(screen.getByText("USD 85.000")).toBeInTheDocument();
    // Los baños quedaron sin cargar: el resumen dice que no hay dato, nunca
    // "0 baños". Vacío no es cero.
    const caracteristicas = screen.getByText(/2 amb\./);
    expect(caracteristicas.textContent).toContain("1 dorm.");
    expect(caracteristicas.textContent).not.toContain("0 baños");
  });
});

describe("accesibilidad", () => {
  it("cada campo tiene etiqueta real, no un placeholder", () => {
    render(<PublicationWizard />);
    expect(screen.getByLabelText(/tipo de propiedad/i)).toBeInTheDocument();
  });

  it("los errores se anuncian", () => {
    render(<PublicationWizard />);
    continuar();
    for (const alerta of screen.getAllByRole("alert")) {
      expect(alerta.textContent?.length).toBeGreaterThan(0);
    }
  });

  it("el campo con error queda marcado", () => {
    render(<PublicationWizard />);
    continuar();
    expect(screen.getByLabelText(/tipo de propiedad/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("anuncia en qué paso está", () => {
    render(<PublicationWizard />);
    expect(screen.getByText(/paso 1 de 8/i)).toBeInTheDocument();
  });

  it("marca el paso actual en la lista", () => {
    render(<PublicationWizard />);
    const actual = screen.getAllByRole("listitem").find((li) => li.getAttribute("aria-current") === "step");
    expect(actual?.textContent).toContain("Qué publicás");
  });
});
