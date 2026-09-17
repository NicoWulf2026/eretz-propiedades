"use client";

// El wizard de publicación.
//
// NO ESTÁ ENLAZADO desde ninguna navegación pública y no guarda en ninguna base.
// Llega hasta "listo para enviar" y ahí se detiene, porque no hay dónde enviar.
//
// Se apoya en `.field`, `.check`, `.primary-button` y `.secondary-button` del
// sistema existente; lo único nuevo en CSS es la disposición del wizard.
//
// Accesibilidad, que en un formulario largo es la diferencia entre usable e
// inusable: cada campo tiene etiqueta real —nunca un placeholder haciendo de
// etiqueta—, los errores se asocian con `aria-describedby`, el foco va al
// primer error al intentar avanzar, y el cambio de paso se anuncia.

import { useCallback, useEffect, useRef, useState } from "react";
import type { BorradorDePublicacion, PrecioDeclarado } from "@/domain/publishing";
import { userId } from "@/domain/ids";
import { revisarAntesDeEnviar, type RevisionPrevia } from "@/lib/publication/service";
import {
  crearAutosave,
  descartarBorrador,
  guardarBorrador,
  leerBorrador,
} from "@/lib/publication/draft-storage";
import { parsearNumero } from "@/lib/calculators/input";
import { PASOS, borradorVacio, indiceDePaso, pasoDelCampo, type PasoId } from "./steps";
import { RevisionFinal } from "./ReviewStep";
import { PasoImagenes } from "./ImagesStep";
import type { MediaDraft } from "@/lib/publication/media";

const AUTOR_LOCAL = userId("borrador-local");

type Props = {
  /** Inyectable para tests: evita depender del reloj real. */
  ahora?: () => number;
};

export function PublicationWizard({ ahora = Date.now }: Props) {
  const [draft, setDraft] = useState<BorradorDePublicacion>(() => borradorVacio(AUTOR_LOCAL));
  const [imagenes, setImagenes] = useState<MediaDraft[]>([]);
  const [paso, setPaso] = useState<PasoId>("operacion");
  const [restauracion, setRestauracion] = useState<"BUSCANDO" | "OFRECIDA" | "RESUELTA">("BUSCANDO");
  const [errores, setErrores] = useState<Record<string, string>>({});
  const primerErrorRef = useRef<HTMLDivElement>(null);

  const actualizar = useCallback(<K extends keyof BorradorDePublicacion>(campo: K, valor: BorradorDePublicacion[K]) => {
    setDraft((previo) => ({ ...previo, [campo]: valor }));
    setErrores((previo) => {
      if (!(campo in previo)) return previo;
      const siguiente = { ...previo };
      delete siguiente[campo as string];
      return siguiente;
    });
  }, []);

  // Las imágenes viven en su propio estado —son objetos con URL de blob— y el
  // borrador las necesita como lista de URLs. Es estado DERIVADO: se calcula
  // acá y no se sincroniza con un efecto, que provocaría un render en cascada
  // por cada foto agregada.
  const draftCompleto: BorradorDePublicacion = {
    ...draft,
    images: imagenes.map((i) => i.previewUrl),
  };

  // --- restauración -------------------------------------------------------
  useEffect(() => {
    // `localStorage` no existe durante el render del servidor, así que leerlo
    // sin efecto no es posible. Es el caso que la propia regla describe como
    // legítimo: sincronizar con un sistema externo al montar. Corre una sola
    // vez, no en cada render.
    const encontrado = leerBorrador();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- ver arriba
    setRestauracion(encontrado.estado === "RESTAURABLE" ? "OFRECIDA" : "RESUELTA");
    // Un borrador de otra versión del formulario se descarta en vez de
    // restaurarse a medias.
    if (encontrado.estado === "INCOMPATIBLE" || encontrado.estado === "ILEGIBLE") descartarBorrador();
  }, []);

  const continuarBorrador = () => {
    const encontrado = leerBorrador();
    if (encontrado.estado === "RESTAURABLE") {
      // Las fotos no se guardan: hay que volver a elegirlas.
      setDraft({ ...encontrado.borrador.draft, images: [] });
    }
    setRestauracion("RESUELTA");
  };

  const descartarYEmpezar = () => {
    descartarBorrador();
    setDraft(borradorVacio(AUTOR_LOCAL));
    setRestauracion("RESUELTA");
  };

  // --- autosave -----------------------------------------------------------
  const autosaveRef = useRef<ReturnType<typeof crearAutosave> | null>(null);
  const datosRef = useRef({ draft, imagenes });
  // Se sincroniza en un efecto y no durante el render, por el mismo motivo que
  // en el paso de fotos.
  useEffect(() => {
    datosRef.current = { draft, imagenes };
  }, [draft, imagenes]);

  useEffect(() => {
    autosaveRef.current = crearAutosave(() => {
      const { draft: d, imagenes: i } = datosRef.current;
      guardarBorrador(d, i.map((x) => x.fileName), ahora());
    });
    // Al desmontar se guarda lo pendiente: sin esto se pierde el último tipeo.
    return () => autosaveRef.current?.cerrar();
  }, [ahora]);

  useEffect(() => {
    if (restauracion !== "RESUELTA") return;
    autosaveRef.current?.programar();
  }, [draft, restauracion]);

  // --- navegación ---------------------------------------------------------
  const indice = indiceDePaso(paso);
  const revision: RevisionPrevia = revisarAntesDeEnviar(draftCompleto);

  const avanzar = () => {
    const delPaso = PASOS[indice];
    const problemas = revision.bloqueantes.filter((b) => delPaso.campos.includes(b.field));

    if (problemas.length) {
      setErrores(Object.fromEntries(problemas.map((p) => [p.field, p.message])));
      // El foco al primer error: en un formulario largo, un error fuera de la
      // pantalla es un error invisible.
      requestAnimationFrame(() => primerErrorRef.current?.focus());
      return;
    }
    setErrores({});
    setPaso(PASOS[Math.min(indice + 1, PASOS.length - 1)].id);
  };

  const retroceder = () => {
    setErrores({});
    setPaso(PASOS[Math.max(indice - 1, 0)].id);
  };

  if (restauracion === "BUSCANDO") return <div className="pub-wizard" aria-busy="true" />;

  if (restauracion === "OFRECIDA") {
    return (
      <div className="pub-wizard">
        <div className="pub-restore" role="dialog" aria-labelledby="restore-title">
          <h2 id="restore-title">Encontramos un borrador en este dispositivo</h2>
          <p>
            Quedó guardado de la última vez. Las fotos no se guardan, así que vas a tener que
            volver a elegirlas.
          </p>
          <div className="pub-actions">
            <button type="button" className="primary-button" onClick={continuarBorrador}>
              Continuar el borrador
            </button>
            <button type="button" className="secondary-button" onClick={descartarYEmpezar}>
              Empezar de cero
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="pub-wizard">
      <ol className="pub-steps" aria-label="Pasos">
        {PASOS.map((p, i) => (
          <li
            key={p.id}
            className={p.id === paso ? "is-current" : i < indice ? "is-done" : undefined}
            aria-current={p.id === paso ? "step" : undefined}
          >
            <span className="pub-step-number">{i + 1}</span>
            <span className="pub-step-label">{p.titulo}</span>
          </li>
        ))}
      </ol>

      {/* El cambio de paso se anuncia: sin esto, quien usa lector de pantalla
          aprieta "Continuar" y no sabe qué pasó. */}
      <p className="sr-only" aria-live="polite">
        Paso {indice + 1} de {PASOS.length}: {PASOS[indice].titulo}
      </p>

      <section className="pub-panel" aria-labelledby="paso-titulo">
        <header className="pub-panel-header">
          <h2 id="paso-titulo">{PASOS[indice].titulo}</h2>
          <p>{PASOS[indice].ayuda}</p>
        </header>

        {/* `tabIndex={-1}` para poder llevarle el foco sin meterlo en el orden
            de tabulación normal. */}
        <div ref={primerErrorRef} tabIndex={-1} className="pub-panel-body">
          <CuerpoDelPaso
            paso={paso}
            draft={draftCompleto}
            actualizar={actualizar}
            errores={errores}
            imagenes={imagenes}
            setImagenes={setImagenes}
            revision={revision}
            irAlPaso={setPaso}
          />
        </div>

        <div className="pub-actions">
          {indice > 0 ? (
            <button type="button" className="secondary-button" onClick={retroceder}>
              Volver
            </button>
          ) : null}
          {paso !== "revision" ? (
            <button type="button" className="primary-button" onClick={avanzar}>
              Continuar
            </button>
          ) : null}
        </div>
      </section>

      <p className="pub-local-note">
        Se guarda como <strong>borrador en este dispositivo</strong>. Todavía no existe una cuenta
        donde sincronizarlo.
      </p>
    </div>
  );
}

// --- cuerpo de cada paso ---------------------------------------------------

type CuerpoProps = {
  paso: PasoId;
  draft: BorradorDePublicacion;
  actualizar: <K extends keyof BorradorDePublicacion>(campo: K, valor: BorradorDePublicacion[K]) => void;
  errores: Record<string, string>;
  imagenes: MediaDraft[];
  setImagenes: (m: MediaDraft[]) => void;
  revision: RevisionPrevia;
  irAlPaso: (p: PasoId) => void;
};

function CuerpoDelPaso(props: CuerpoProps) {
  switch (props.paso) {
    case "operacion":
      return <PasoOperacion {...props} />;
    case "ubicacion":
      return <PasoUbicacion {...props} />;
    case "precio":
      return <PasoPrecio {...props} />;
    case "caracteristicas":
      return <PasoCaracteristicas {...props} />;
    case "descripcion":
      return <PasoDescripcion {...props} />;
    case "imagenes":
      return <PasoImagenes imagenes={props.imagenes} onChange={props.setImagenes} />;
    case "contacto":
      return <PasoContacto {...props} />;
    case "revision":
      return <RevisionFinal draft={props.draft} revision={props.revision} irAlPaso={props.irAlPaso} />;
  }
}

/** Campo de texto con etiqueta real y error asociado. */
function Campo({
  id,
  etiqueta,
  valor,
  onChange,
  error,
  ayuda,
  tipo = "text",
  placeholder,
}: {
  id: string;
  etiqueta: string;
  valor: string;
  onChange: (v: string) => void;
  error?: string;
  ayuda?: string;
  tipo?: string;
  placeholder?: string;
}) {
  return (
    <label className="field" htmlFor={id}>
      <span>{etiqueta}</span>
      <input
        id={id}
        type={tipo}
        value={valor}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : ayuda ? `${id}-ayuda` : undefined}
      />
      {error ? (
        <span id={`${id}-error`} className="pub-error" role="alert">{error}</span>
      ) : ayuda ? (
        <span id={`${id}-ayuda`} className="pub-help">{ayuda}</span>
      ) : null}
    </label>
  );
}

const OPERACIONES = [
  { valor: "venta", etiqueta: "Venta" },
  { valor: "alquiler", etiqueta: "Alquiler" },
  { valor: "temporario", etiqueta: "Alquiler temporario" },
];

const TIPOS = [
  "departamento", "casa", "ph", "terreno", "oficina", "local", "cochera", "galpon", "campo", "otro",
];

function PasoOperacion({ draft, actualizar, errores }: CuerpoProps) {
  return (
    <div className="pub-grid">
      <fieldset className="pub-fieldset">
        <legend>Qué querés hacer</legend>
        <div className="pub-options">
          {OPERACIONES.map((o) => (
            <label key={o.valor} className="check">
              <input
                type="radio"
                name="operacion"
                checked={draft.operation === o.valor}
                onChange={() => actualizar("operation", o.valor)}
              />
              {o.etiqueta}
            </label>
          ))}
        </div>
        {errores.operation ? <p className="pub-error" role="alert">{errores.operation}</p> : null}
      </fieldset>

      <label className="field" htmlFor="tipo">
        <span>Tipo de propiedad</span>
        <select
          id="tipo"
          value={draft.propertyType ?? ""}
          onChange={(e) => actualizar("propertyType", e.target.value || null)}
          aria-invalid={errores.propertyType ? true : undefined}
        >
          <option value="">Elegí una opción</option>
          {TIPOS.map((t) => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
        </select>
        {errores.propertyType ? <span className="pub-error" role="alert">{errores.propertyType}</span> : null}
      </label>
    </div>
  );
}

function PasoUbicacion({ draft, actualizar, errores }: CuerpoProps) {
  return (
    <div className="pub-grid">
      <Campo id="provincia" etiqueta="Provincia" valor={draft.province ?? ""} error={errores.province}
        onChange={(v) => actualizar("province", v || null)} />
      <Campo id="ciudad" etiqueta="Ciudad" valor={draft.city ?? ""} error={errores.city}
        onChange={(v) => actualizar("city", v || null)} />
      <Campo id="barrio" etiqueta="Barrio (opcional)" valor={draft.neighborhood ?? ""}
        onChange={(v) => actualizar("neighborhood", v || null)} />
      <Campo id="direccion" etiqueta="Dirección (opcional)" valor={draft.address ?? ""}
        onChange={(v) => actualizar("address", v || null)}
        ayuda="No la mostramos completa si no querés. Ayuda a ubicarla mejor." />
    </div>
  );
}

function PasoPrecio({ draft, actualizar, errores }: CuerpoProps) {
  const esConsultar = draft.precio?.kind === "CONSULTAR";
  const monto = draft.precio?.kind === "MONTO" ? String(draft.precio.amount) : "";
  const moneda = draft.precio?.kind === "MONTO" ? draft.precio.currency : "USD";

  const ponerMonto = (texto: string) => {
    const n = parsearNumero(texto);
    // `null` significa "todavía no decidiste", que es distinto de "a consultar".
    actualizar("precio", n === null ? null : ({ kind: "MONTO", amount: n, currency: moneda } as PrecioDeclarado));
  };

  return (
    <div className="pub-grid">
      <fieldset className="pub-fieldset">
        <legend>Cómo mostrás el precio</legend>
        <div className="pub-options">
          <label className="check">
            <input type="radio" name="modo-precio" checked={!esConsultar && draft.precio !== null}
              onChange={() => actualizar("precio", { kind: "MONTO", amount: 0, currency: "USD" })} />
            Con un monto
          </label>
          <label className="check">
            <input type="radio" name="modo-precio" checked={esConsultar}
              onChange={() => actualizar("precio", { kind: "CONSULTAR" })} />
            A consultar
          </label>
        </div>
        {errores.precio ? <p className="pub-error" role="alert">{errores.precio}</p> : null}
      </fieldset>

      {!esConsultar ? (
        <>
          <label className="field" htmlFor="moneda">
            <span>Moneda</span>
            <select id="moneda" value={moneda}
              onChange={(e) => {
                const n = parsearNumero(monto);
                actualizar("precio", n === null ? null : { kind: "MONTO", amount: n, currency: e.target.value as "USD" | "ARS" });
              }}>
              <option value="USD">Dólares (USD)</option>
              <option value="ARS">Pesos (ARS)</option>
            </select>
          </label>
          <Campo id="monto" etiqueta="Monto" valor={monto} onChange={ponerMonto} />
        </>
      ) : null}

      <Campo id="expensas" etiqueta="Expensas mensuales (opcional)" valor={draft.expenses === null ? "" : String(draft.expenses)}
        onChange={(v) => actualizar("expenses", parsearNumero(v))} />
    </div>
  );
}

function PasoCaracteristicas({ draft, actualizar, errores }: CuerpoProps) {
  const numerico = (campo: "rooms" | "bedrooms" | "bathrooms" | "totalArea" | "coveredArea") =>
    (v: string) => actualizar(campo, parsearNumero(v));

  return (
    <div className="pub-grid">
      <Campo id="ambientes" etiqueta="Ambientes" valor={draft.rooms === null ? "" : String(draft.rooms)}
        onChange={numerico("rooms")} />
      <Campo id="dormitorios" etiqueta="Dormitorios" valor={draft.bedrooms === null ? "" : String(draft.bedrooms)}
        onChange={numerico("bedrooms")} error={errores.bedrooms} />
      <Campo id="banos" etiqueta="Baños" valor={draft.bathrooms === null ? "" : String(draft.bathrooms)}
        onChange={numerico("bathrooms")} />
      <Campo id="superficie" etiqueta="Superficie total (m²)" valor={draft.totalArea === null ? "" : String(draft.totalArea)}
        onChange={numerico("totalArea")} />
      <Campo id="cubierta" etiqueta="Superficie cubierta (m²)" valor={draft.coveredArea === null ? "" : String(draft.coveredArea)}
        onChange={numerico("coveredArea")} error={errores.coveredArea}
        ayuda="Lo que no sepas, dejalo vacío. Vacío significa que no sabemos, no cero." />
    </div>
  );
}

function PasoDescripcion({ draft, actualizar, errores }: CuerpoProps) {
  return (
    <div className="pub-grid pub-grid-single">
      <Campo id="titulo" etiqueta="Título" valor={draft.title ?? ""} error={errores.title}
        onChange={(v) => actualizar("title", v || null)}
        placeholder="Departamento de 2 ambientes en Rosario centro" />
      <label className="field" htmlFor="descripcion">
        <span>Descripción</span>
        <textarea id="descripcion" rows={7} value={draft.description ?? ""}
          onChange={(e) => actualizar("description", e.target.value || null)}
          aria-invalid={errores.description ? true : undefined}
          aria-describedby={errores.description ? "descripcion-error" : undefined} />
        {errores.description ? <span id="descripcion-error" className="pub-error" role="alert">{errores.description}</span> : null}
      </label>
    </div>
  );
}

function PasoContacto({ draft, actualizar, errores }: CuerpoProps) {
  return (
    <div className="pub-grid">
      <Campo id="telefono" etiqueta="Teléfono" valor={draft.contactPhone ?? ""} error={errores.contactPhone}
        onChange={(v) => actualizar("contactPhone", v || null)} tipo="tel" />
      <Campo id="email" etiqueta="Email" valor={draft.contactEmail ?? ""}
        onChange={(v) => actualizar("contactEmail", v || null)} tipo="email"
        ayuda="Con uno de los dos alcanza." />

      <div className="pub-grid-single">
        <label className="check">
          <input type="checkbox" checked={draft.legitimacyAccepted}
            onChange={(e) => actualizar("legitimacyAccepted", e.target.checked)}
            aria-invalid={errores.legitimacyAccepted ? true : undefined} />
          Confirmo que estoy autorizado a publicar esta propiedad.
        </label>
        {errores.legitimacyAccepted ? <p className="pub-error" role="alert">{errores.legitimacyAccepted}</p> : null}
      </div>
    </div>
  );
}

export { pasoDelCampo };
