import { beforeEach, describe, expect, it, vi } from "vitest";
import { userId } from "@/domain/ids";
import type { BorradorDePublicacion } from "@/domain/publishing";
import {
  CLAVE_BORRADOR,
  DRAFT_VERSION,
  TAMANO_MAXIMO_BYTES,
  crearAutosave,
  descartarBorrador,
  guardarBorrador,
  leerBorrador,
} from "./draft-storage";

/** Almacenamiento de mentira, controlable. */
function almacenFalso(inicial: Record<string, string> = {}) {
  const datos = new Map(Object.entries(inicial));
  return {
    getItem: (k: string) => datos.get(k) ?? null,
    setItem: (k: string, v: string) => void datos.set(k, v),
    removeItem: (k: string) => void datos.delete(k),
    _datos: datos,
  };
}

function borrador(o: Partial<BorradorDePublicacion> = {}): BorradorDePublicacion {
  return {
    publisherType: "INDIVIDUAL",
    authorUserId: userId("u-1"),
    organizationId: null,
    agentId: null,
    operation: "venta",
    propertyType: "casa",
    precio: { kind: "MONTO", amount: 120_000, currency: "USD" },
    expenses: null,
    province: "Santa Fe",
    city: "Rosario",
    neighborhood: null,
    address: null,
    title: "Casa con patio en Rosario",
    description: "Una descripción con suficiente detalle para pasar la validación.",
    rooms: 4,
    bedrooms: 3,
    bathrooms: 2,
    totalArea: 180,
    coveredArea: 120,
    images: ["blob:una", "blob:dos"],
    contactPhone: "3410000000",
    contactEmail: null,
    legitimacyAccepted: true,
    ...o,
  };
}

describe("no se guardan las imágenes", () => {
  it("el borrador guardado no contiene los blobs", () => {
    // Una sola foto de celular llena localStorage y rompería el guardado de
    // todo lo demás, justo cuando más contenido hay.
    const almacen = almacenFalso();
    guardarBorrador(borrador(), ["patio.jpg", "frente.jpg"], 1000, almacen);

    const crudo = almacen._datos.get(CLAVE_BORRADOR) as string;
    expect(crudo).not.toContain("blob:");
    expect(crudo).not.toContain("base64");
  });

  it("guarda los nombres para poder pedirlas de nuevo", () => {
    const almacen = almacenFalso();
    guardarBorrador(borrador(), ["patio.jpg"], 1000, almacen);
    const r = leerBorrador(almacen);
    expect(r.estado).toBe("RESTAURABLE");
    if (r.estado === "RESTAURABLE") expect(r.borrador.imageNames).toEqual(["patio.jpg"]);
  });
});

describe("ida y vuelta", () => {
  it("lo guardado se recupera igual", () => {
    const almacen = almacenFalso();
    const original = borrador({ title: "Casa con patio y quincho" });
    guardarBorrador(original, [], 1234, almacen);

    const r = leerBorrador(almacen);
    expect(r.estado).toBe("RESTAURABLE");
    if (r.estado === "RESTAURABLE") {
      expect(r.borrador.draft.title).toBe("Casa con patio y quincho");
      expect(r.borrador.draft.precio).toEqual({ kind: "MONTO", amount: 120_000, currency: "USD" });
      expect(r.borrador.savedAt).toBe(1234);
    }
  });

  it("preserva 'a consultar' como decisión, no como ausencia", () => {
    const almacen = almacenFalso();
    guardarBorrador(borrador({ precio: { kind: "CONSULTAR" } }), [], 1, almacen);
    const r = leerBorrador(almacen);
    if (r.estado === "RESTAURABLE") expect(r.borrador.draft.precio).toEqual({ kind: "CONSULTAR" });
    else expect.unreachable("debería restaurar");
  });

  it("sin borrador previo no inventa uno", () => {
    expect(leerBorrador(almacenFalso()).estado).toBe("SIN_BORRADOR");
  });

  it("descartar lo borra", () => {
    const almacen = almacenFalso();
    guardarBorrador(borrador(), [], 1, almacen);
    descartarBorrador(almacen);
    expect(leerBorrador(almacen).estado).toBe("SIN_BORRADOR");
  });
});

describe("versionado", () => {
  it("no restaura un borrador de otra versión del formulario", () => {
    // Restaurar a medias es peor que no restaurar, porque parece que funcionó.
    const almacen = almacenFalso({
      [CLAVE_BORRADOR]: JSON.stringify({ draftVersion: DRAFT_VERSION - 1, savedAt: 1, draft: {}, imageNames: [] }),
    });
    const r = leerBorrador(almacen);
    expect(r.estado).toBe("INCOMPATIBLE");
    if (r.estado === "INCOMPATIBLE") expect(r.versionGuardada).toBe(DRAFT_VERSION - 1);
  });

  it("tampoco restaura uno de una versión futura", () => {
    const almacen = almacenFalso({
      [CLAVE_BORRADOR]: JSON.stringify({ draftVersion: DRAFT_VERSION + 5, savedAt: 1, draft: {}, imageNames: [] }),
    });
    expect(leerBorrador(almacen).estado).toBe("INCOMPATIBLE");
  });

  it("marca la versión al guardar", () => {
    const almacen = almacenFalso();
    guardarBorrador(borrador(), [], 1, almacen);
    const guardado = JSON.parse(almacen._datos.get(CLAVE_BORRADOR) as string);
    expect(guardado.draftVersion).toBe(DRAFT_VERSION);
  });
});

describe("robustez", () => {
  it("un contenido corrupto no rompe nada", () => {
    for (const basura of ["{", "null", "[]", "no es json", '{"draftVersion":"uno"}']) {
      const r = leerBorrador(almacenFalso({ [CLAVE_BORRADOR]: basura }));
      expect(["ILEGIBLE", "SIN_BORRADOR"]).toContain(r.estado);
    }
  });

  it("sin almacenamiento el wizard sigue funcionando", () => {
    // Modo privado o almacenamiento bloqueado: se pierde el autosave, no la
    // pantalla.
    expect(guardarBorrador(borrador(), [], 1, null)).toBe(false);
    expect(leerBorrador(null).estado).toBe("SIN_BORRADOR");
    expect(() => descartarBorrador(null)).not.toThrow();
  });

  it("no escribe si supera el tope", () => {
    // Se comprueba antes de escribir: pasado el límite el navegador lanza y
    // puede dejar el valor anterior corrupto.
    const almacen = almacenFalso();
    const enorme = borrador({ description: "x".repeat(TAMANO_MAXIMO_BYTES + 1000) });
    expect(guardarBorrador(enorme, [], 1, almacen)).toBe(false);
    expect(almacen._datos.has(CLAVE_BORRADOR)).toBe(false);
  });

  it("un almacenamiento que lanza no propaga el error", () => {
    const roto = {
      getItem: () => { throw new Error("bloqueado"); },
      setItem: () => { throw new Error("cuota"); },
      removeItem: () => { throw new Error("bloqueado"); },
    };
    expect(guardarBorrador(borrador(), [], 1, roto)).toBe(false);
    expect(leerBorrador(roto).estado).toBe("ILEGIBLE");
    expect(() => descartarBorrador(roto)).not.toThrow();
  });
});

describe("autosave", () => {
  beforeEach(() => vi.useFakeTimers());

  it("no guarda en cada tecla", () => {
    // Escribir es sincrónico y bloquea el hilo de la interfaz.
    const guardar = vi.fn();
    const auto = crearAutosave(guardar, 800);
    for (let i = 0; i < 10; i++) auto.programar();
    expect(guardar).not.toHaveBeenCalled();

    vi.advanceTimersByTime(800);
    expect(guardar).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("cerrar guarda lo pendiente de inmediato", () => {
    // Sin esto se pierde hasta un segundo de tipeo al salir, que es justo el
    // que más molesta perder.
    const guardar = vi.fn();
    const auto = crearAutosave(guardar, 800);
    auto.programar();
    auto.cerrar();
    expect(guardar).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("cerrar sin nada pendiente no guarda de más", () => {
    const guardar = vi.fn();
    const auto = crearAutosave(guardar, 800);
    auto.cerrar();
    expect(guardar).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("cerrar después de guardar no vuelve a guardar", () => {
    const guardar = vi.fn();
    const auto = crearAutosave(guardar, 800);
    auto.programar();
    vi.advanceTimersByTime(800);
    auto.cerrar();
    expect(guardar).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
