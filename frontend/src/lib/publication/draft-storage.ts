// Borrador guardado EN ESTE DISPOSITIVO.
//
// Válido porque es explícitamente local: no promete una cuenta que no existe.
// La UI tiene que decirlo con esas palabras — "borrador en este dispositivo"—
// y nunca "guardado en tu cuenta".
//
// ---------------------------------------------------------------------------
// POR QUÉ VERSIONADO
// ---------------------------------------------------------------------------
//
// El formulario va a cambiar: se agregan campos, se renombran, se parten en
// dos. Un borrador guardado con la forma vieja, restaurado sobre el formulario
// nuevo, produce una pantalla rota o —peor— campos silenciosamente vacíos que
// la persona cree haber completado.
//
// Con `draftVersion` eso se detecta. Lo que NO se hace es adivinar la
// migración: si la versión no coincide y no hay una migración escrita, el
// borrador se descarta y se avisa. Restaurar a medias es la peor de las tres
// opciones, porque parece que funcionó.
//
// ---------------------------------------------------------------------------
// LO QUE NO SE GUARDA
// ---------------------------------------------------------------------------
//
// Las imágenes. Un `localStorage` tiene unos pocos megabytes y una sola foto de
// celular los llena; guardarlas en base64 rompería el guardado de TODO lo demás
// y lo haría justo cuando más contenido hay. Se guardan los nombres para poder
// decir "faltan volver a cargar las fotos", que es honesto y barato.

import type { BorradorDePublicacion } from "@/domain/publishing";

/** Sube cuando la forma del borrador cambia de manera incompatible. */
export const DRAFT_VERSION = 1;

export const CLAVE_BORRADOR = "eretz:publicacion:borrador";

/** Tope de seguridad. Si el borrador supera esto, algo se está guardando mal. */
export const TAMANO_MAXIMO_BYTES = 256 * 1024;

export type BorradorLocal = {
  draftVersion: number;
  savedAt: number;
  /** Sin imágenes: ver el encabezado. */
  draft: Omit<BorradorDePublicacion, "images">;
  /** Nombres de los archivos elegidos, para poder pedirlos de nuevo. */
  imageNames: string[];
};

export type ResultadoDeRestauracion =
  | { estado: "SIN_BORRADOR" }
  | { estado: "RESTAURABLE"; borrador: BorradorLocal }
  /** Existe pero es de otra versión del formulario. No se restaura solo. */
  | { estado: "INCOMPATIBLE"; versionGuardada: number }
  | { estado: "ILEGIBLE" };

type Almacen = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/**
 * El almacenamiento del navegador, o `null` donde no hay.
 *
 * Puede fallar por modo privado o por configuración, y en ese caso el wizard
 * tiene que seguir funcionando sin autosave en vez de romperse.
 */
function almacenPorDefecto(): Almacen | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

export function guardarBorrador(
  draft: BorradorDePublicacion,
  imageNames: string[],
  ahora: number = Date.now(),
  almacen: Almacen | null = almacenPorDefecto(),
): boolean {
  if (!almacen) return false;

  // Las imágenes se sacan explícitamente. Copiar y borrar, en vez de
  // desestructurar, hace lo mismo sin dejar una variable sin usar — y sigue
  // guardando solo cualquier campo nuevo del borrador.
  const sinImagenes: Omit<BorradorDePublicacion, "images"> & { images?: unknown } = { ...draft };
  delete sinImagenes.images;
  const payload: BorradorLocal = {
    draftVersion: DRAFT_VERSION,
    savedAt: ahora,
    draft: sinImagenes,
    imageNames: imageNames.slice(0, 40),
  };

  try {
    const texto = JSON.stringify(payload);
    // Se comprueba ANTES de escribir: pasado el tope, el navegador lanza y
    // según cuál sea puede dejar el valor anterior corrupto.
    if (texto.length > TAMANO_MAXIMO_BYTES) return false;
    almacen.setItem(CLAVE_BORRADOR, texto);
    return true;
  } catch {
    // Cuota llena o almacenamiento bloqueado. No es motivo para romper nada.
    return false;
  }
}

export function leerBorrador(almacen: Almacen | null = almacenPorDefecto()): ResultadoDeRestauracion {
  if (!almacen) return { estado: "SIN_BORRADOR" };

  let crudo: string | null;
  try {
    crudo = almacen.getItem(CLAVE_BORRADOR);
  } catch {
    return { estado: "ILEGIBLE" };
  }
  if (!crudo) return { estado: "SIN_BORRADOR" };

  let parseado: unknown;
  try {
    parseado = JSON.parse(crudo);
  } catch {
    return { estado: "ILEGIBLE" };
  }

  if (typeof parseado !== "object" || parseado === null) return { estado: "ILEGIBLE" };
  const candidato = parseado as Partial<BorradorLocal>;

  if (typeof candidato.draftVersion !== "number") return { estado: "ILEGIBLE" };
  if (candidato.draftVersion !== DRAFT_VERSION) {
    // No se intenta adivinar la migración. Restaurar a medias es peor que no
    // restaurar, porque parece que funcionó.
    return { estado: "INCOMPATIBLE", versionGuardada: candidato.draftVersion };
  }
  if (typeof candidato.draft !== "object" || candidato.draft === null) return { estado: "ILEGIBLE" };

  return {
    estado: "RESTAURABLE",
    borrador: {
      draftVersion: candidato.draftVersion,
      savedAt: typeof candidato.savedAt === "number" ? candidato.savedAt : 0,
      draft: candidato.draft as BorradorLocal["draft"],
      imageNames: Array.isArray(candidato.imageNames)
        ? candidato.imageNames.filter((n): n is string => typeof n === "string")
        : [],
    },
  };
}

export function descartarBorrador(almacen: Almacen | null = almacenPorDefecto()): void {
  try {
    almacen?.removeItem(CLAVE_BORRADOR);
  } catch {
    // Nada que hacer, y nada que romper.
  }
}

// --- autosave --------------------------------------------------------------

/** Cuánto se espera desde la última tecla antes de guardar. */
export const RETARDO_AUTOSAVE_MS = 800;

/**
 * Guardado con retardo.
 *
 * Sin retardo se escribiría en cada tecla, que es sincrónico y bloquea el hilo
 * de la interfaz mientras alguien escribe una descripción larga.
 *
 * `cerrar()` guarda lo pendiente inmediatamente. Se llama al desmontar: sin eso
 * se pierde hasta un segundo de tipeo, que es justo el que más molesta perder.
 */
export function crearAutosave(
  guardar: () => void,
  retardoMs: number = RETARDO_AUTOSAVE_MS,
): { programar: () => void; cerrar: () => void } {
  let temporizador: ReturnType<typeof setTimeout> | null = null;
  let pendiente = false;

  return {
    programar() {
      pendiente = true;
      if (temporizador) clearTimeout(temporizador);
      temporizador = setTimeout(() => {
        temporizador = null;
        pendiente = false;
        guardar();
      }, retardoMs);
    },
    cerrar() {
      if (temporizador) {
        clearTimeout(temporizador);
        temporizador = null;
      }
      if (pendiente) {
        pendiente = false;
        guardar();
      }
    },
  };
}
