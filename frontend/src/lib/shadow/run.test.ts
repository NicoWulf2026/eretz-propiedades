import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { _setEscritor } from "@/lib/observability/logger";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";
import type { SupabaseProperty } from "@/types/property";
import type { ParaEvaluar } from "./evaluate";
import { VAR_MUESTREO, VAR_SHADOW } from "./flag";
import { CORRELACION_SHADOW, ejecutarShadow } from "./run";

// Se captura la ESCRITURA con el hook que el logger ya expone, no se mockea
// `logEvent`: así el redactor y el descarte de campos no escalares siguen
// corriendo, que es justamente lo que estos tests verifican.
let lineas: Record<string, unknown>[] = [];
let restaurar: () => void;

const guardado = { ...process.env };

beforeEach(() => {
  lineas = [];
  restaurar = _setEscritor((l) => lineas.push(JSON.parse(l) as Record<string, unknown>));
  delete process.env[VAR_SHADOW];
  delete process.env[VAR_MUESTREO];
});

afterEach(() => {
  restaurar();
  process.env = { ...guardado };
});

const encender = () => {
  process.env[VAR_SHADOW] = "true";
};

function entrada(o: Partial<SupabaseProperty> = {}): ParaEvaluar {
  const item = { ...completeRow, ...o };
  return { property: mapSupabasePropertyToProperty(item), item };
}

const lote = (n: number, o: Partial<SupabaseProperty> = {}): ParaEvaluar[] =>
  Array.from({ length: n }, (_, i) => entrada({ ...o, id: 2000 + i }));

describe("flag apagada", () => {
  it("no escribe ninguna línea", () => {
    ejecutarShadow(lote(10), "ruta");
    expect(lineas).toEqual([]);
  });

  it("no toca el lote", () => {
    const l = lote(10);
    const copia = structuredClone(l);
    ejecutarShadow(l, "ruta");
    expect(l).toEqual(copia);
  });

  it("con un lote vacío tampoco hace nada", () => {
    ejecutarShadow([], "ruta");
    expect(lineas).toEqual([]);
  });
});

describe("flag encendida", () => {
  beforeEach(encender);

  it("escribe exactamente una línea por lote, no una por propiedad", () => {
    // 24 líneas por request de listado no serían legibles.
    ejecutarShadow(lote(24), "ruta");
    expect(lineas).toHaveLength(1);
    expect(lineas[0].event).toBe("domain_shadow_summary");
  });

  it("sigue sin tocar el lote", () => {
    const l = lote(10);
    const copia = structuredClone(l);
    ejecutarShadow(l, "ruta");
    expect(l).toEqual(copia);
  });

  it("no devuelve nada, así que nadie puede decidir con el resultado", () => {
    expect(ejecutarShadow(lote(3), "ruta")).toBeUndefined();
  });

  it("incluye la ruta y la correlación", () => {
    ejecutarShadow(lote(3), "mapRowsToProperties");
    expect(lineas[0].route).toBe("mapRowsToProperties");
    expect(lineas[0].requestId).toBe(CORRELACION_SHADOW);
  });

  it("incluye el tiempo que tardó la evaluación", () => {
    ejecutarShadow(lote(5), "ruta");
    expect(typeof lineas[0].domain_shadow_ms).toBe("number");
  });

  it("no escribe nada si el muestreo deja el lote sin evaluar", () => {
    process.env[VAR_MUESTREO] = "0";
    ejecutarShadow(lote(10), "ruta");
    expect(lineas).toEqual([]);
  });

  it("los campos del resumen sobreviven al logger", () => {
    // El logger descarta lo no escalar en silencio: si el aplanado fallara, la
    // línea saldría vacía y nadie se enteraría.
    ejecutarShadow(lote(6, { imagenes: null }), "ruta");
    const l = lineas[0];
    expect(l.evaluadas).toBe(6);
    expect(typeof l.mod_allow).toBe("number");
    expect(typeof l.mod_review).toBe("number");
    expect(typeof l.dq_valid).toBe("number");
    expect(typeof l.score_p50).toBe("number");
    expect(typeof l.razon_1).toBe("string");
  });

  it("marca warn cuando se pasa un umbral diagnóstico, sin ocultar nada", () => {
    ejecutarShadow(lote(10, { imagenes: null }), "ruta");
    expect(lineas[0].level).toBe("warn");
    expect(typeof lineas[0].advertencias).toBe("string");
  });

  it("marca info cuando la muestra está sana", () => {
    ejecutarShadow(lote(10), "ruta");
    expect(lineas[0].level).toBe("info");
  });
});

describe("privacidad del log", () => {
  beforeEach(encender);

  it("no filtra título, descripción, dirección ni contacto", () => {
    const l = lote(4, {
      titulo: "Casa con jardin en Fisherton",
      descripcion: "Texto descriptivo que no debe aparecer en ningun log",
      direccion: "Av. Siempreviva 742",
      agente_nombre: "Juan Perez",
      agente_telefono: "3410000000",
      publisher_email: "contacto@ejemplo.com",
      publisher_website: "https://ejemplo.com",
      url: "https://ejemplo.com/propiedad/secreta",
    });
    ejecutarShadow(l, "ruta");

    const texto = JSON.stringify(lineas);
    for (const prohibido of [
      "Casa con jardin",
      "Texto descriptivo",
      "Siempreviva",
      "Juan Perez",
      "3410000000",
      "contacto@ejemplo.com",
      "propiedad/secreta",
      "ejemplo.com",
    ]) {
      expect(texto, `filtró "${prohibido}"`).not.toContain(prohibido);
    }
  });

  it("sólo viajan códigos, conteos e ids de propiedad", () => {
    ejecutarShadow(lote(5, { imagenes: null }), "ruta");
    const razon = String(lineas[0].razon_1);
    // Formato CODIGO:conteo:ids. Los ids son públicos —están en la URL de la
    // ficha— y sin un caso concreto un porcentaje no se puede investigar.
    expect(razon).toMatch(/^[A-Z_]+:\d+:[\d,]*$/);
  });

  it("un error de la evaluación no arrastra el mensaje", () => {
    // El mensaje podría traer un valor de la propiedad que lo causó.
    const roto = [{ property: null, item: null }] as unknown as ParaEvaluar[];
    expect(() => ejecutarShadow(roto, "ruta")).not.toThrow();
    expect(lineas[0]?.event).toBe("domain_shadow_error");
    expect(lineas[0]).not.toHaveProperty("errorMessage");
  });
});

describe("un observador no puede tirar abajo lo que observa", () => {
  beforeEach(encender);

  it("una entrada corrupta no propaga la excepción", () => {
    const roto = [{ property: undefined, item: undefined }] as unknown as ParaEvaluar[];
    expect(() => ejecutarShadow(roto, "ruta")).not.toThrow();
  });

  it("registra el fallo para que no pase inadvertido", () => {
    const roto = [{ property: null, item: null }] as unknown as ParaEvaluar[];
    ejecutarShadow(roto, "ruta");
    expect(lineas[0].level).toBe("warn");
    expect(lineas[0].errorName).toBeTruthy();
  });
});

describe("equivalencia de respuesta en el punto de integración", () => {
  it("el arreglo de propiedades es idéntico con la flag encendida y apagada", () => {
    // Réplica exacta del cableado en `mapRowsToProperties`: se construye el
    // arreglo, se llama a ejecutarShadow, y se devuelve el MISMO arreglo.
    const conApagada = lote(12);
    ejecutarShadow(conApagada, "mapRowsToProperties");
    const salidaApagada = conApagada.map((x) => x.property);

    encender();
    const conEncendida = lote(12);
    ejecutarShadow(conEncendida, "mapRowsToProperties");
    const salidaEncendida = conEncendida.map((x) => x.property);

    // Mismos ids, mismo orden, misma cantidad, mismos campos.
    expect(salidaEncendida.map((p) => p.id)).toEqual(salidaApagada.map((p) => p.id));
    expect(salidaEncendida).toHaveLength(salidaApagada.length);
    expect(salidaEncendida).toEqual(salidaApagada);
  });

  it("el orden no depende del puntaje de calidad", () => {
    // Mezcla de calidades muy distintas: el orden de entrada se conserva.
    encender();
    const mezcla = [
      entrada({ id: 1, imagenes: null, titulo: null }),
      entrada({ id: 2 }),
      entrada({ id: 3, superficie_cubierta: 9000 }),
    ];
    const antes = mezcla.map((x) => x.property.id);
    ejecutarShadow(mezcla, "ruta");
    expect(mezcla.map((x) => x.property.id)).toEqual(antes);
  });

  it("una publicación que el dominio marcaría REJECT sigue en el arreglo", () => {
    // Es la garantía que define el modo sombra: calcular sin decidir.
    encender();
    const l = lote(3, { superficie_cubierta: 9000, superficie_total: 100 });
    ejecutarShadow(l, "ruta");
    expect(l).toHaveLength(3);
    expect(l.every((x) => x.property !== null)).toBe(true);
  });
});
