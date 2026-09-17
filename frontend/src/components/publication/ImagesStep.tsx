"use client";

// Paso de fotos.
//
// Nada se sube. Se elige, se previsualiza, se ordena y se quita, todo en este
// dispositivo. La previsualización usa `URL.createObjectURL`, que referencia el
// archivo ya en memoria del navegador en vez de copiarlo — y por eso hay que
// revocarla al quitar una imagen o al salir, o se acumulan hasta recargar.

import { useCallback, useEffect, useRef } from "react";
import {
  MAXIMO_IMAGENES,
  quitar,
  reordenar,
  validarSeleccion,
  type MediaDraft,
  type ProblemaDeImagen,
} from "@/lib/publication/media";
import { useState } from "react";

export function PasoImagenes({
  imagenes,
  onChange,
}: {
  imagenes: MediaDraft[];
  onChange: (m: MediaDraft[]) => void;
}) {
  const [rechazadas, setRechazadas] = useState<ProblemaDeImagen[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Se revocan las URLs al desmontar. Sin esto, cada foto elegida queda
  // retenida en memoria hasta que se recargue la página.
  const imagenesRef = useRef(imagenes);
  useEffect(() => {
    // El ref se sincroniza dentro de un efecto, no durante el render: React
    // puede renderizar sin llegar a montar, y escribir en el ref ahí deja el
    // valor desalineado con lo que efectivamente se mostró.
    imagenesRef.current = imagenes;
  }, [imagenes]);
  useEffect(() => () => {
    for (const i of imagenesRef.current) URL.revokeObjectURL(i.previewUrl);
  }, []);

  const elegir = useCallback(
    (archivos: FileList | null) => {
      if (!archivos?.length) return;
      const resultado = validarSeleccion(
        Array.from(archivos),
        imagenes.length,
        (archivo) => URL.createObjectURL(archivo as File),
      );
      onChange([...imagenes, ...resultado.aceptadas]);
      setRechazadas(resultado.rechazadas);
      // El input se limpia para poder volver a elegir el mismo archivo.
      if (inputRef.current) inputRef.current.value = "";
    },
    [imagenes, onChange],
  );

  const eliminar = (localId: string) => {
    const objetivo = imagenes.find((i) => i.localId === localId);
    if (objetivo) URL.revokeObjectURL(objetivo.previewUrl);
    onChange(quitar(imagenes, localId));
  };

  const mover = (desde: number, hasta: number) => onChange(reordenar(imagenes, desde, hasta));

  return (
    <div className="pub-grid-single">
      <label className="field" htmlFor="fotos">
        <span>Elegí las fotos</span>
        <input
          ref={inputRef}
          id="fotos"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/avif"
          multiple
          onChange={(e) => elegir(e.target.files)}
          aria-describedby="fotos-ayuda"
        />
        <span id="fotos-ayuda" className="pub-help">
          Hasta {MAXIMO_IMAGENES}. La primera es la portada. Quedan sólo en este dispositivo:
          todavía no hay dónde subirlas.
        </span>
      </label>

      {rechazadas.length ? (
        <ul className="pub-rejected" role="alert">
          {rechazadas.map((r) => (
            <li key={`${r.fileName}-${r.code}`}>
              <strong>{r.fileName}</strong>: {r.message}
            </li>
          ))}
        </ul>
      ) : null}

      {imagenes.length ? (
        <ol className="pub-images" aria-label="Fotos elegidas">
          {imagenes.map((imagen, i) => (
            <li key={imagen.localId} className="pub-image">
              {/* eslint-disable-next-line @next/next/no-img-element -- es un
                  blob local: next/image no aplica y no hay nada que optimizar. */}
              <img src={imagen.previewUrl} alt="" />
              <span className="pub-image-name">
                {i === 0 ? <strong>Portada · </strong> : null}
                {imagen.fileName}
              </span>
              <div className="pub-image-actions">
                <button type="button" className="icon-button" onClick={() => mover(i, i - 1)}
                  disabled={i === 0} aria-label={`Mover ${imagen.fileName} antes`}>↑</button>
                <button type="button" className="icon-button" onClick={() => mover(i, i + 1)}
                  disabled={i === imagenes.length - 1} aria-label={`Mover ${imagen.fileName} después`}>↓</button>
                <button type="button" className="icon-button" onClick={() => eliminar(imagen.localId)}
                  aria-label={`Quitar ${imagen.fileName}`}>×</button>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
