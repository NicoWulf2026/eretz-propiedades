import { describe, expect, it } from "vitest";
import {
  MAXIMO_IMAGENES,
  TAMANO_MAXIMO_BYTES,
  TIPOS_ACEPTADOS,
  quitar,
  reordenar,
  validarSeleccion,
  type MediaDraft,
} from "./media";

const archivo = (name: string, type = "image/jpeg", size = 1_000_000) => ({ name, size, type });
const preview = (a: { name: string }) => `blob:${a.name}`;

const seleccionar = (archivos: ReturnType<typeof archivo>[], yaCargadas = 0) =>
  validarSeleccion(archivos, yaCargadas, preview);

describe("no se sube nada", () => {
  it("la vista previa es una referencia local, no una copia", () => {
    // `URL.createObjectURL` apunta al archivo que ya está en memoria del
    // navegador. Nada viaja a ningún servidor.
    const r = seleccionar([archivo("frente.jpg")]);
    expect(r.aceptadas[0].previewUrl).toBe("blob:frente.jpg");
  });

  it("no guarda el contenido del archivo en ningún lado", () => {
    const r = seleccionar([archivo("frente.jpg")]);
    const json = JSON.stringify(r.aceptadas[0]);
    expect(json).not.toContain("base64");
    expect(Object.keys(r.aceptadas[0]).sort()).toEqual([
      "fileName", "localId", "mimeType", "previewUrl", "sizeBytes",
    ]);
  });
});

describe("una tanda mala no descarta las buenas", () => {
  it("acepta las válidas y rechaza las demás", () => {
    // Si alguien selecciona diez fotos y una es un PDF, lo razonable es cargar
    // las nueve y decir cuál no entró.
    const r = seleccionar([
      archivo("uno.jpg"),
      archivo("documento.pdf", "application/pdf"),
      archivo("dos.png", "image/png"),
    ]);
    expect(r.aceptadas.map((a) => a.fileName)).toEqual(["uno.jpg", "dos.png"]);
    expect(r.rechazadas).toHaveLength(1);
    expect(r.rechazadas[0].code).toBe("TIPO_NO_ACEPTADO");
  });

  it("cada rechazo dice por qué, con el nombre del archivo", () => {
    const r = seleccionar([archivo("enorme.jpg", "image/jpeg", TAMANO_MAXIMO_BYTES + 1)]);
    expect(r.rechazadas[0].fileName).toBe("enorme.jpg");
    expect(r.rechazadas[0].message).toMatch(/MB/);
  });
});

describe("validación", () => {
  it("acepta los formatos declarados", () => {
    for (const tipo of TIPOS_ACEPTADOS) {
      expect(seleccionar([archivo("foto", tipo)]).aceptadas).toHaveLength(1);
    }
  });

  it("rechaza formatos que no son imagen", () => {
    for (const tipo of ["application/pdf", "video/mp4", "text/html", ""]) {
      expect(seleccionar([archivo("x", tipo)]).rechazadas).toHaveLength(1);
    }
  });

  it("rechaza archivos vacíos", () => {
    expect(seleccionar([archivo("vacio.jpg", "image/jpeg", 0)]).rechazadas[0].code).toBe("VACIO");
  });

  it("respeta el cupo contando lo ya cargado", () => {
    const r = seleccionar(
      Array.from({ length: 5 }, (_, i) => archivo(`f${i}.jpg`)),
      MAXIMO_IMAGENES - 2,
    );
    expect(r.aceptadas).toHaveLength(2);
    expect(r.rechazadas).toHaveLength(3);
    expect(r.rechazadas[0].code).toBe("SIN_CUPO");
  });

  it("con el cupo lleno rechaza todo", () => {
    const r = seleccionar([archivo("una.jpg")], MAXIMO_IMAGENES);
    expect(r.aceptadas).toEqual([]);
  });

  it("genera identificadores distintos", () => {
    const r = seleccionar(Array.from({ length: 8 }, (_, i) => archivo(`f${i}.jpg`)));
    expect(new Set(r.aceptadas.map((a) => a.localId)).size).toBe(8);
  });
});

describe("orden", () => {
  const lista = (n: number): MediaDraft[] =>
    Array.from({ length: n }, (_, i) => ({
      localId: `i${i}`,
      fileName: `f${i}.jpg`,
      sizeBytes: 1,
      mimeType: "image/jpeg",
      previewUrl: `blob:${i}`,
    }));

  it("mueve una imagen sin perder el resto", () => {
    // La primera es la portada, así que el orden importa.
    const r = reordenar(lista(4), 3, 0);
    expect(r.map((x) => x.localId)).toEqual(["i3", "i0", "i1", "i2"]);
  });

  it("no muta la lista original", () => {
    const original = lista(3);
    reordenar(original, 0, 2);
    expect(original.map((x) => x.localId)).toEqual(["i0", "i1", "i2"]);
  });

  it("un índice fuera de rango no rompe ni reordena", () => {
    expect(reordenar(lista(3), 0, 9).map((x) => x.localId)).toEqual(["i0", "i1", "i2"]);
    expect(reordenar(lista(3), -1, 0).map((x) => x.localId)).toEqual(["i0", "i1", "i2"]);
  });

  it("mover al mismo lugar no cambia nada", () => {
    expect(reordenar(lista(3), 1, 1).map((x) => x.localId)).toEqual(["i0", "i1", "i2"]);
  });

  it("quita por identificador", () => {
    expect(quitar(lista(3), "i1").map((x) => x.localId)).toEqual(["i0", "i2"]);
  });

  it("quitar algo que no está deja la lista igual", () => {
    expect(quitar(lista(3), "no-existe")).toHaveLength(3);
  });
});
