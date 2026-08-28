// Imágenes de una publicación.
//
// ---------------------------------------------------------------------------
// NO SE SUBE NADA
// ---------------------------------------------------------------------------
//
// No hay proveedor de almacenamiento decidido, y elegir uno para "ir probando"
// significa migrar archivos de personas reales cuando se cambie. Lo que sí se
// puede hacer sin proveedor —y es la mayor parte del trabajo— es elegir,
// previsualizar, ordenar, quitar y validar.
//
// Las previsualizaciones usan `URL.createObjectURL`, que no copia el archivo:
// crea una referencia al que ya está en memoria del navegador. Por eso hay que
// revocarlas, y por eso no se guarda base64 en ningún lado.

export const MAXIMO_IMAGENES = 20;
export const MINIMO_IMAGENES = 1;
/** Por archivo. Una foto de celular ronda los 3-5 MB. */
export const TAMANO_MAXIMO_BYTES = 12 * 1024 * 1024;

export const TIPOS_ACEPTADOS = ["image/jpeg", "image/png", "image/webp", "image/avif"] as const;

/** Una imagen elegida, todavía sólo en este dispositivo. */
export type MediaDraft = {
  /** Identificador local. No es el id que tendrá cuando exista storage. */
  localId: string;
  fileName: string;
  sizeBytes: number;
  mimeType: string;
  /** URL de objeto para la vista previa. Hay que revocarla al quitarla. */
  previewUrl: string;
};

export type ProblemaDeImagen = { fileName: string; code: string; message: string };

export type ResultadoDeSeleccion = {
  aceptadas: MediaDraft[];
  rechazadas: ProblemaDeImagen[];
};

type ArchivoMinimo = { name: string; size: number; type: string };

/**
 * Valida una tanda de archivos contra las que ya hay.
 *
 * Devuelve aceptadas y rechazadas por separado en vez de fallar entera: si
 * alguien selecciona diez fotos y una es un PDF, lo razonable es cargar las
 * nueve y decir cuál no entró.
 */
export function validarSeleccion(
  archivos: readonly ArchivoMinimo[],
  yaCargadas: number,
  crearPreview: (archivo: ArchivoMinimo, indice: number) => string,
): ResultadoDeSeleccion {
  const aceptadas: MediaDraft[] = [];
  const rechazadas: ProblemaDeImagen[] = [];
  let cupo = MAXIMO_IMAGENES - yaCargadas;

  archivos.forEach((archivo, indice) => {
    if (!(TIPOS_ACEPTADOS as readonly string[]).includes(archivo.type)) {
      rechazadas.push({
        fileName: archivo.name,
        code: "TIPO_NO_ACEPTADO",
        message: "Sólo se aceptan imágenes JPG, PNG, WebP o AVIF.",
      });
      return;
    }
    if (archivo.size > TAMANO_MAXIMO_BYTES) {
      rechazadas.push({
        fileName: archivo.name,
        code: "DEMASIADO_GRANDE",
        message: `Pesa más de ${Math.round(TAMANO_MAXIMO_BYTES / (1024 * 1024))} MB.`,
      });
      return;
    }
    if (archivo.size === 0) {
      rechazadas.push({ fileName: archivo.name, code: "VACIO", message: "El archivo está vacío." });
      return;
    }
    if (cupo <= 0) {
      rechazadas.push({
        fileName: archivo.name,
        code: "SIN_CUPO",
        message: `Se pueden subir hasta ${MAXIMO_IMAGENES} fotos.`,
      });
      return;
    }

    cupo -= 1;
    aceptadas.push({
      localId: `img-${Date.now()}-${indice}-${Math.random().toString(36).slice(2, 8)}`,
      fileName: archivo.name,
      sizeBytes: archivo.size,
      mimeType: archivo.type,
      previewUrl: crearPreview(archivo, indice),
    });
  });

  return { aceptadas, rechazadas };
}

/** Mueve una imagen. La primera es la portada, así que el orden importa. */
export function reordenar(imagenes: readonly MediaDraft[], desde: number, hasta: number): MediaDraft[] {
  if (desde === hasta) return [...imagenes];
  if (desde < 0 || hasta < 0 || desde >= imagenes.length || hasta >= imagenes.length) {
    return [...imagenes];
  }
  const copia = [...imagenes];
  const [movida] = copia.splice(desde, 1);
  copia.splice(hasta, 0, movida);
  return copia;
}

export function quitar(imagenes: readonly MediaDraft[], localId: string): MediaDraft[] {
  return imagenes.filter((i) => i.localId !== localId);
}

// --- contrato futuro -------------------------------------------------------

/**
 * Cómo se subirán las imágenes cuando haya dónde.
 *
 * Cuatro pasos, y la razón de que sean cuatro y no uno: el archivo NO pasa por
 * nuestro servidor. Se pide una URL firmada, el navegador sube directo al
 * proveedor, y recién después se confirma. Subir a través del servidor
 * significaría que cada foto de 5 MB ocupa memoria y tiempo de una función.
 *
 * `attach` va separado de `confirm` porque una imagen puede existir sin estar
 * asociada todavía a una publicación —se sube mientras se completa el
 * formulario— y porque asociar es lo único que tiene que ser transaccional con
 * el resto de la publicación.
 *
 * Sin proveedor elegido: no Supabase Storage, no Vercel Blob, no S3.
 */
export type MediaUploadContract = {
  /** Pide permiso para subir un archivo concreto. */
  presign(input: { fileName: string; mimeType: string; sizeBytes: number }): Promise<{
    uploadUrl: string;
    /** El id definitivo del archivo, asignado por el proveedor. */
    mediaId: string;
    expiresAt: string;
  }>;

  /** Avisa que la subida terminó, para que el proveedor la dé por válida. */
  confirm(mediaId: string): Promise<MediaUploadResult>;

  /** Asocia imágenes ya confirmadas a una publicación, en orden. */
  attach(publicationId: string, mediaIds: readonly string[]): Promise<void>;
};

export type MediaUploadResult = {
  mediaId: string;
  url: string;
  width: number | null;
  height: number | null;
  sizeBytes: number;
};
