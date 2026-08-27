import { describe, expect, it } from "vitest";
import { listingId, organizationId } from "./ids";
import {
  CLAVES_PROHIBIDAS,
  PROFESSIONAL_EVENTS,
  type EventoProfesional,
  esContacto,
  eventoProfesionalDe,
  formaDeBusqueda,
  problemasDeEvento,
} from "./professional-analytics";

function evento(o: Partial<EventoProfesional> = {}): EventoProfesional {
  return {
    name: "listing_view",
    occurredAt: "2026-08-27T12:00:00Z",
    context: { sessionId: "s-abc", isNewSession: false },
    surface: "SEARCH_RESULTS",
    listingId: listingId("l-1"),
    organizationId: organizationId("org-1"),
    agentId: null,
    search: null,
    ...o,
  };
}

const campos = (e: EventoProfesional) => problemasDeEvento(e).map((p) => p.campo);

describe("no se guarda el texto de búsqueda", () => {
  it("reduce la búsqueda a sus nombres de filtro", () => {
    // Una búsqueda libre puede traer una calle con altura o un nombre propio:
    // guardarlo y mostrarlo en un panel es exponer un dato de un tercero.
    const forma = formaDeBusqueda({ q: "casa de los Pérez en Salta 1234", city: "Rosario", minPrice: 50_000 });
    expect(forma.hadFreeText).toBe(true);
    expect(forma.filterNames).toEqual(["city", "minPrice"]);
    expect(JSON.stringify(forma)).not.toContain("Pérez");
    expect(JSON.stringify(forma)).not.toContain("Salta");
  });

  it("registra que hubo texto libre, no cuál", () => {
    expect(formaDeBusqueda({ q: "" }).hadFreeText).toBe(false);
    expect(formaDeBusqueda({ q: "x" }).hadFreeText).toBe(true);
    expect(formaDeBusqueda({ q: "x" }).filterNames).toEqual([]);
  });

  it("ignora los campos de presentación", () => {
    const forma = formaDeBusqueda({ sort: "price_asc", page: 3, viewport: {}, city: "Rosario" });
    expect(forma.filterNames).toEqual(["city"]);
  });

  it("no cuenta filtros vacíos ni banderas apagadas", () => {
    expect(formaDeBusqueda({ city: "", locations: [], hasVideo: false }).filterNames).toEqual([]);
  });

  it("es determinista y ordenado", () => {
    expect(formaDeBusqueda({ minPrice: 1, city: "x" }).filterNames).toEqual(["city", "minPrice"]);
    expect(formaDeBusqueda({ city: "x", minPrice: 1 }).filterNames).toEqual(["city", "minPrice"]);
  });

  it("guarda el conteo de resultados, que no identifica a nadie", () => {
    expect(formaDeBusqueda({ city: "x" }, 42).resultCount).toBe(42);
  });
});

describe("qué no puede viajar en un evento", () => {
  it("rechaza claves con datos personales", () => {
    for (const clave of ["email", "phone", "userId", "query", "ip"]) {
      const e = { ...evento(), [clave]: "algo" } as unknown as EventoProfesional;
      expect(campos(e)).toContain(clave);
    }
  });

  it("la lista de prohibidas cubre lo esperable", () => {
    for (const c of ["email", "phone", "userId", "token", "password", "q"]) {
      expect(CLAVES_PROHIBIDAS).toContain(c);
    }
  });

  it("detecta valores disfrazados de nombres de filtro", () => {
    // `precio=250000` identifica una búsqueda concreta.
    const e = evento({ search: { filterNames: ["precio=250000"], hadFreeText: false, resultCount: null } });
    expect(campos(e)).toContain("search.filterNames");
  });

  it("acepta nombres de filtro legítimos", () => {
    const e = evento({ search: { filterNames: ["city", "minPrice"], hadFreeText: true, resultCount: 12 } });
    expect(problemasDeEvento(e)).toEqual([]);
  });

  it("el contexto es anónimo: no hay campo de usuario en el tipo", () => {
    // Cuando existan cuentas habrá que decidir explícitamente si se atribuye;
    // esa decisión no debe poder tomarse por omisión.
    expect(Object.keys(evento().context).sort()).toEqual(["isNewSession", "sessionId"]);
  });
});

describe("validación de forma", () => {
  it("acepta un evento bien formado", () => {
    expect(problemasDeEvento(evento())).toEqual([]);
  });

  it("rechaza un evento desconocido", () => {
    expect(campos(evento({ name: "inventado" as never }))).toContain("name");
  });

  it("rechaza una superficie desconocida", () => {
    expect(campos(evento({ surface: "X" as never }))).toContain("surface");
  });

  it("exige identificador de sesión", () => {
    const e = evento({ context: { sessionId: "", isNewSession: true } });
    expect(campos(e)).toContain("context.sessionId");
  });

  it("los eventos sobre una publicación exigen la publicación", () => {
    for (const name of ["listing_view", "contact_intent", "favorite", "share"] as const) {
      expect(campos(evento({ name, listingId: null }))).toContain("listingId");
    }
  });

  it("los que no la necesitan no la exigen", () => {
    expect(problemasDeEvento(evento({ name: "profile_view", listingId: null }))).toEqual([]);
  });
});

describe("relación con la analítica de interacción", () => {
  it("traduce las interacciones que le importan a una inmobiliaria", () => {
    expect(eventoProfesionalDe("property_opened")).toBe("listing_view");
    expect(eventoProfesionalDe("contact_started")).toBe("contact_intent");
    expect(eventoProfesionalDe("whatsapp_clicked")).toBe("contact_channel_used");
    expect(eventoProfesionalDe("real_estate_opened")).toBe("profile_view");
  });

  it("descarta las que no le dicen nada", () => {
    // Mover el mapa o cambiar el orden son datos de producto, no de la
    // organización: meterlos en su panel sería ruido.
    for (const i of ["map_moved", "sort_changed", "filter_applied", "zero_results"]) {
      expect(eventoProfesionalDe(i)).toBeNull();
    }
  });

  it("una interacción desconocida no inventa un evento", () => {
    expect(eventoProfesionalDe("cualquier_cosa")).toBeNull();
  });
});

describe("intención y contacto son distintos", () => {
  it("los dos son contacto pero no el mismo evento", () => {
    // La diferencia entre abrir el panel y apretar WhatsApp es exactamente la
    // tasa de conversión que le interesa a una inmobiliaria.
    expect(esContacto("contact_intent")).toBe(true);
    expect(esContacto("contact_channel_used")).toBe(true);
    expect(PROFESSIONAL_EVENTS).toContain("contact_intent");
    expect(PROFESSIONAL_EVENTS).toContain("contact_channel_used");
  });

  it("lo demás no es contacto", () => {
    for (const e of ["listing_view", "favorite", "share", "profile_view"] as const) {
      expect(esContacto(e)).toBe(false);
    }
  });

  it("el lead figura como futuro, no como existente", () => {
    expect(PROFESSIONAL_EVENTS).toContain("lead_future");
  });
});
