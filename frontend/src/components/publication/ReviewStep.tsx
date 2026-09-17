"use client";

// Revisión antes de publicar.
//
// Dos listas SEPARADAS, y la separación es lo importante:
//
//   BLOQUEANTES  impiden publicar. Se corrigen o no hay publicación.
//   SUGERENCIAS  conviene atenderlas y no impiden nada.
//
// Mezclarlas haría una de dos cosas, las dos malas: o la persona corrige
// sugerencias creyendo que son obligatorias, o ignora bloqueantes creyendo que
// son opcionales.
//
// No se muestra el puntaje de calidad. Un "82/100" invita a optimizar la
// métrica en vez de la publicación, y no dice qué hacer. Las sugerencias sí.

import type { BorradorDePublicacion } from "@/domain/publishing";
import type { RevisionPrevia } from "@/lib/publication/service";
import { montoDelPrecio, monedaDelPrecio } from "@/lib/publication/adapter";
import { formatearDinero } from "@/lib/calculators/input";
import { pasoDelCampo, type PasoId } from "./steps";

function precioLegible(draft: BorradorDePublicacion): string {
  if (draft.precio === null) return "Sin definir";
  if (draft.precio.kind === "CONSULTAR") return "A consultar";
  const monto = montoDelPrecio(draft.precio);
  const moneda = monedaDelPrecio(draft.precio);
  return monto !== null && moneda ? formatearDinero(monto, moneda as "USD" | "ARS") : "Sin definir";
}

function ubicacionLegible(draft: BorradorDePublicacion): string {
  const partes = [draft.address, draft.neighborhood, draft.city, draft.province].filter(Boolean);
  return partes.length ? partes.join(", ") : "Sin definir";
}

function caracteristicasLegibles(draft: BorradorDePublicacion): string {
  const partes = [
    draft.rooms !== null ? `${draft.rooms} amb.` : null,
    draft.bedrooms !== null ? `${draft.bedrooms} dorm.` : null,
    draft.bathrooms !== null ? `${draft.bathrooms} baños` : null,
    draft.totalArea !== null ? `${draft.totalArea} m²` : null,
  ].filter(Boolean);
  // Vacío significa que no se cargó, no que sea cero.
  return partes.length ? partes.join(" · ") : "Sin datos cargados";
}

export function RevisionFinal({
  draft,
  revision,
  irAlPaso,
}: {
  draft: BorradorDePublicacion;
  revision: RevisionPrevia;
  irAlPaso: (p: PasoId) => void;
}) {
  const filas: Array<[string, string, PasoId]> = [
    ["Operación", draft.operation ?? "Sin definir", "operacion"],
    ["Tipo", draft.propertyType ?? "Sin definir", "operacion"],
    ["Precio", precioLegible(draft), "precio"],
    ["Ubicación", ubicacionLegible(draft), "ubicacion"],
    ["Características", caracteristicasLegibles(draft), "caracteristicas"],
    ["Título", draft.title ?? "Sin definir", "descripcion"],
    ["Fotos", draft.images.length ? `${draft.images.length}` : "Ninguna", "imagenes"],
    ["Contacto", draft.contactPhone ?? draft.contactEmail ?? "Sin definir", "contacto"],
  ];

  return (
    <div className="pub-review">
      {revision.bloqueantes.length ? (
        <section className="pub-blockers" aria-labelledby="bloqueantes-titulo" role="alert">
          <h3 id="bloqueantes-titulo">Falta corregir esto</h3>
          <ul>
            {revision.bloqueantes.map((b) => {
              const destino = pasoDelCampo(b.field);
              return (
                <li key={`${b.field}-${b.code}`}>
                  {b.message}
                  {destino ? (
                    <button type="button" className="pub-link" onClick={() => irAlPaso(destino)}>
                      Ir a corregirlo
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {revision.sugerencias.length ? (
        <section className="pub-suggestions" aria-labelledby="sugerencias-titulo">
          <h3 id="sugerencias-titulo">Podés mejorarla</h3>
          <p className="pub-suggestions-note">No hace falta para publicar.</p>
          <ul>
            {revision.sugerencias.map((s) => {
              const destino = pasoDelCampo(s.field);
              return (
                <li key={s.field}>
                  {s.message}
                  {destino ? (
                    <button type="button" className="pub-link" onClick={() => irAlPaso(destino)}>
                      Ir
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <dl className="pub-summary">
        {filas.map(([etiqueta, valor, destino]) => (
          <div key={etiqueta} className="pub-summary-row">
            <dt>{etiqueta}</dt>
            <dd>
              {valor}
              <button type="button" className="pub-link" onClick={() => irAlPaso(destino)}>
                Editar
              </button>
            </dd>
          </div>
        ))}
      </dl>

      <div className="pub-submit-state" aria-live="polite">
        {revision.listoParaEnviar ? (
          <>
            <p className="pub-ready">
              <strong>Listo para publicar.</strong>
            </p>
            {/* No hay botón de publicar, y no es un olvido: no existe dónde
                guardar. Un botón acá aceptaría el trabajo de alguien para
                perderlo. */}
            <p className="pub-ready-note">
              Todavía no podemos recibirla: falta conectar el guardado. Cuando esté, este es el
              punto donde se publica. Tu borrador queda en este dispositivo.
            </p>
          </>
        ) : (
          <p className="pub-not-ready">Corregí lo de arriba para poder publicar.</p>
        )}
      </div>
    </div>
  );
}
