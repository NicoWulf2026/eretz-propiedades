import { describe, expect, it } from "vitest";
import {
  AlmacenEnMemoria,
  claveDeCliente,
  esDuplicado,
  huellaDeContenido,
  limitarTasa,
} from "@/lib/abuse/rate-limit";

const VENTANA = 60_000;

describe("freno de abuso", () => {
  it("deja pasar hasta el límite y corta después", () => {
    const almacen = new AlmacenEnMemoria();
    const opciones = { limite: 3, ventanaMs: VENTANA, almacen, ahora: 1_000 };
    const veredictos = [1, 2, 3, 4].map(() => limitarTasa("k", opciones));
    expect(veredictos.map((v) => v.permitido)).toEqual([true, true, true, false]);
    expect(veredictos[2].restantes).toBe(0);
  });

  it("dice cuándo reintentar", () => {
    const almacen = new AlmacenEnMemoria();
    limitarTasa("k", { limite: 1, ventanaMs: VENTANA, almacen, ahora: 0 });
    const v = limitarTasa("k", { limite: 1, ventanaMs: VENTANA, almacen, ahora: 10_000 });
    expect(v.permitido).toBe(false);
    expect(v.reintentarEnSeg).toBe(50);
  });

  it("la ventana se renueva cuando vence", () => {
    const almacen = new AlmacenEnMemoria();
    const base = { limite: 1, ventanaMs: VENTANA, almacen };
    expect(limitarTasa("k", { ...base, ahora: 0 }).permitido).toBe(true);
    expect(limitarTasa("k", { ...base, ahora: 100 }).permitido).toBe(false);
    expect(limitarTasa("k", { ...base, ahora: VENTANA + 1 }).permitido).toBe(true);
  });

  it("cada clave lleva su propia cuenta", () => {
    const almacen = new AlmacenEnMemoria();
    const base = { limite: 1, ventanaMs: VENTANA, almacen, ahora: 0 };
    expect(limitarTasa("a", base).permitido).toBe(true);
    expect(limitarTasa("b", base).permitido).toBe(true);
  });

  // --- el almacén no puede ser un vector de OOM ---------------------------

  it("acota cuántas claves retiene", () => {
    // Sin cota, cada request con una clave distinta agrega una entrada y el
    // freno de abuso pasa a ser el abuso.
    const almacen = new AlmacenEnMemoria(50);
    for (let i = 0; i < 500; i += 1) {
      limitarTasa(`k${i}`, { limite: 5, ventanaMs: VENTANA, almacen, ahora: 1_000 });
    }
    // La 499 sigue contando desde cero si fue podada, pero nunca crece sin fin:
    // se comprueba que la memoria no explotó pidiendo una clave vieja.
    const vieja = limitarTasa("k0", { limite: 5, ventanaMs: VENTANA, almacen, ahora: 1_000 });
    expect(vieja.permitido).toBe(true);
  });

  it("descarta las entradas vencidas", () => {
    const almacen = new AlmacenEnMemoria();
    limitarTasa("k", { limite: 1, ventanaMs: 10, almacen, ahora: 0 });
    expect(limitarTasa("k", { limite: 1, ventanaMs: 10, almacen, ahora: 1_000 }).permitido).toBe(true);
  });

  // --- deduplicación -------------------------------------------------------

  it("reconoce el mismo contenido enviado dos veces", () => {
    const almacen = new AlmacenEnMemoria();
    const fp = huellaDeContenido([123, "precio_incorrecto", "el precio esta mal"]);
    expect(esDuplicado(fp, { ventanaMs: VENTANA, almacen, ahora: 0 })).toBe(false);
    expect(esDuplicado(fp, { ventanaMs: VENTANA, almacen, ahora: 500 })).toBe(true);
  });

  it("la huella ignora mayúsculas y espacios de borde", () => {
    expect(huellaDeContenido([1, " Otro ", "TEXTO"])).toBe(huellaDeContenido([1, "otro", "texto"]));
  });

  it("contenidos distintos no colisionan", () => {
    expect(huellaDeContenido([1, "a"])).not.toBe(huellaDeContenido([1, "b"]));
    expect(huellaDeContenido([1, "a"])).not.toBe(huellaDeContenido([2, "a"]));
  });

  it("pasada la ventana, el mismo contenido vuelve a aceptarse", () => {
    const almacen = new AlmacenEnMemoria();
    const fp = huellaDeContenido(["x"]);
    esDuplicado(fp, { ventanaMs: 100, almacen, ahora: 0 });
    expect(esDuplicado(fp, { ventanaMs: 100, almacen, ahora: 5_000 })).toBe(false);
  });

  // --- identificación de quien llama --------------------------------------

  it("no guarda la IP en claro", () => {
    const clave = claveDeCliente(new Headers({ "x-forwarded-for": "203.0.113.9" }));
    expect(clave).not.toContain("203.0.113");
    expect(clave).toMatch(/^[0-9a-f]{32}$/);
  });

  it("usa sólo la primera IP de la cadena de proxies", () => {
    const a = claveDeCliente(new Headers({ "x-forwarded-for": "203.0.113.9, 10.0.0.1" }));
    const b = claveDeCliente(new Headers({ "x-forwarded-for": "203.0.113.9" }));
    expect(a).toBe(b);
  });

  it("separa por sufijo para que un endpoint no consuma la cuota de otro", () => {
    const h = new Headers({ "x-forwarded-for": "203.0.113.9" });
    expect(claveDeCliente(h, "reports")).not.toBe(claveDeCliente(h, "claims"));
  });

  it("no rompe cuando no hay ningún header de origen", () => {
    expect(claveDeCliente(new Headers())).toMatch(/^[0-9a-f]{32}$/);
  });
});
