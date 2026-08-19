"use client";

import L, { type LatLngBounds } from "leaflet";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { locationConfidenceDescription, locationConfidenceLabel } from "@/lib/geo-confidence";
import {
  clusterSize,
  formatMapPriceAccessible,
  formatMapPriceCompact,
  viewportMovedMeaningfully,
} from "@/lib/map-presentation";
import { mergeDetailedPagePoints } from "@/lib/map-points";
import { propertyLocation, typeLabels } from "@/lib/property-presenter";
import type { MapSearchResponse, MapViewport, PropertySummary } from "@/types/property";

type MapPoint = MapSearchResponse["points"][number];

class OpenStreetMapCanvasLayer extends L.GridLayer {
  constructor() {
    super({
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      tileSize: 256,
      updateWhenIdle: true,
      keepBuffer: 1,
    });
  }

  override createTile(coords: L.Coords, done: L.DoneCallback) {
    const canvas = document.createElement("canvas");
    canvas.className = "eretz-map-tile";
    const density = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = 256 * density;
    canvas.height = 256 * density;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.referrerPolicy = "no-referrer";
    image.decoding = "async";
    image.onload = () => {
      const context = canvas.getContext("2d");
      if (context) context.drawImage(image, 0, 0, canvas.width, canvas.height);
      done(undefined, canvas);
    };
    image.onerror = () => done(new Error("Map tile could not be loaded"), canvas);
    const subdomain = ["a", "b", "c"][Math.abs(coords.x + coords.y) % 3];
    image.src = `https://${subdomain}.tile.openstreetmap.org/${coords.z}/${coords.x}/${coords.y}.png`;
    return canvas;
  }
}

function CanvasTileLayer() {
  const map = useMap();
  useEffect(() => {
    const layer = new OpenStreetMapCanvasLayer();
    layer.addTo(map);
    return () => { layer.removeFrom(map); };
  }, [map]);
  return null;
}

function MapResizeSync() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    let frame = 0;
    const resize = () => {
      if (container.clientWidth > 0 && container.clientHeight > 0) map.invalidateSize({ animate: false });
    };
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(resize);
    });
    observer.observe(container);
    frame = requestAnimationFrame(resize);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [map]);
  return null;
}

function markerIcon(point: MapPoint) {
  if (point.kind === "cluster") {
    const size = clusterSize(point.count);
    return L.divIcon({
      className: "eretz-map-marker-host",
      html: `<span class="eretz-map-cluster is-${size}" aria-hidden="true">${point.count > 999 ? "999+" : point.count}</span>`,
      iconSize: size === "large" ? [52, 52] : size === "medium" ? [46, 46] : [40, 40],
      iconAnchor: size === "large" ? [26, 26] : size === "medium" ? [23, 23] : [20, 20],
    });
  }
  const price = formatMapPriceCompact(point.price, point.currency);
  return L.divIcon({
    className: "eretz-map-marker-host",
    html: `<span class="eretz-price-marker is-location-${point.locationConfidence}" aria-hidden="true">${price}</span>`,
    iconSize: [92, 36],
    iconAnchor: [46, 34],
    popupAnchor: [0, -34],
  });
}

function markerAccessibleName(point: MapPoint): string {
  if (point.kind === "cluster") return `${point.count.toLocaleString("es-AR")} propiedades agrupadas. Activar para acercar.`;
  const confidence = point.locationConfidence === "high"
    ? ""
    : `, ${locationConfidenceLabel(point.locationConfidence).toLocaleLowerCase("es-AR")}`;
  return `${typeLabels[point.propertyType]} en ${point.location}, ${formatMapPriceAccessible(point.price, point.currency)}${confidence}`;
}

const InteractiveMarker = memo(function InteractiveMarker({
  point,
  selected,
  onSelect,
  onPreview,
  returnTo,
}: {
  point: MapPoint;
  selected: boolean;
  onSelect?: (id: string) => void;
  onPreview?: (id: string | null) => void;
  returnTo: string;
}) {
  const map = useMap();
  const markerRef = useRef<L.Marker | null>(null);
  const accessibleName = markerAccessibleName(point);
  const icon = useMemo(() => markerIcon(point), [point]);

  useEffect(() => {
    const element = markerRef.current?.getElement();
    if (!element) return;
    element.setAttribute("role", "button");
    element.setAttribute("aria-label", accessibleName);
    element.setAttribute("data-map-point-kind", point.kind);
    element.tabIndex = 0;
    const activateWithKeyboard = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      markerRef.current?.fire("click");
    };
    element.addEventListener("keydown", activateWithKeyboard);
    if (point.kind === "property") {
      element.setAttribute("data-property-marker-id", point.id);
      element.setAttribute("aria-pressed", selected ? "true" : "false");
      element.querySelector(".eretz-price-marker")?.classList.toggle("is-selected", selected);
      const preview = () => onPreview?.(point.id);
      const clearPreview = () => onPreview?.(null);
      element.addEventListener("focus", preview);
      element.addEventListener("blur", clearPreview);
      return () => {
        element.removeEventListener("keydown", activateWithKeyboard);
        element.removeEventListener("focus", preview);
        element.removeEventListener("blur", clearPreview);
      };
    } else {
      element.removeAttribute("aria-pressed");
    }
    return () => element.removeEventListener("keydown", activateWithKeyboard);
  }, [accessibleName, onPreview, point, selected]);

  return (
    <Marker
      ref={markerRef}
      position={[point.latitude, point.longitude]}
      icon={icon}
      keyboard={false}
      riseOnHover
      riseOffset={350}
      alt={accessibleName}
      eventHandlers={{
        click: () => {
          if (point.kind === "cluster") map.setView([point.latitude, point.longitude], Math.min(map.getZoom() + 2, 18));
          else onSelect?.(point.id);
        },
        mouseover: () => { if (point.kind === "property") onPreview?.(point.id); },
        mouseout: () => { if (point.kind === "property") onPreview?.(null); },
      }}
    >
      {point.kind === "property" ? (
        <Popup closeButton minWidth={190} maxWidth={250}>
          <a href={`/propiedad/${point.id}?volver=${encodeURIComponent(returnTo)}`} className="map-popup">
            <strong>{formatMapPriceAccessible(point.price, point.currency)}</strong>
            <span>{typeLabels[point.propertyType]} · {point.location}</span>
            {point.locationConfidence !== "high" ? (
              <small className={`map-location-confidence is-${point.locationConfidence}`}>
                <strong>{locationConfidenceLabel(point.locationConfidence)}</strong>
                <span>{locationConfidenceDescription(point.locationConfidence)}</span>
              </small>
            ) : null}
          </a>
        </Popup>
      ) : null}
    </Marker>
  );
});

function viewportFromBounds(bounds: LatLngBounds, zoom: number): MapViewport {
  return {
    north: Number(bounds.getNorth().toFixed(5)),
    east: Number(bounds.getEast().toFixed(5)),
    south: Number(bounds.getSouth().toFixed(5)),
    west: Number(bounds.getWest().toFixed(5)),
    zoom,
  };
}

function MapEvents({ onViewport, locateRequest, onLocationError }: { onViewport: (viewport: MapViewport, persist: boolean) => void; locateRequest: number; onLocationError: () => void }) {
  const initialViewportReported = useRef(false);
  const userInteraction = useRef(false);
  const map = useMapEvents({
    moveend() {
      onViewport(viewportFromBounds(map.getBounds(), map.getZoom()), userInteraction.current);
      userInteraction.current = false;
    },
    locationfound(event) {
      userInteraction.current = true;
      map.setView(event.latlng, Math.max(map.getZoom(), 14));
    },
    locationerror() { onLocationError(); },
  });
  useEffect(() => {
    const container = map.getContainer();
    const markInteraction = () => { userInteraction.current = true; };
    container.addEventListener("pointerdown", markInteraction, { passive: true });
    container.addEventListener("wheel", markInteraction, { passive: true });
    container.addEventListener("keydown", markInteraction);
    return () => {
      container.removeEventListener("pointerdown", markInteraction);
      container.removeEventListener("wheel", markInteraction);
      container.removeEventListener("keydown", markInteraction);
    };
  }, [map]);
  useEffect(() => {
    if (initialViewportReported.current) return;
    initialViewportReported.current = true;
    onViewport(viewportFromBounds(map.getBounds(), map.getZoom()), false);
  }, [map, onViewport]);
  useEffect(() => {
    if (locateRequest > 0) map.locate({ enableHighAccuracy: false, timeout: 8_000, maximumAge: 120_000 });
  }, [locateRequest, map]);
  return null;
}

function InitialView({ points, viewport, resetRequest }: { points: MapPoint[]; viewport: MapViewport | null; resetRequest: number }) {
  const map = useMap();
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current && resetRequest === 0) return;
    initialized.current = true;
    if (viewport) {
      map.fitBounds([[viewport.south, viewport.west], [viewport.north, viewport.east]], { animate: false });
      return;
    }
    const positions = points.map((point) => [point.latitude, point.longitude] as [number, number]);
    if (positions.length === 1) map.setView(positions[0], 14, { animate: false });
    else if (positions.length > 1) map.fitBounds(positions, { padding: [36, 36], maxZoom: 13, animate: false });
  }, [map, points, resetRequest, viewport]);
  return null;
}

function MapIcon({ name }: { name: "frame" | "location" | "expand" | "close" }) {
  if (name === "frame") return <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="6" width="14" height="12" rx="2" /><path d="M9 10h6v4H9z" /></svg>;
  if (name === "location") return <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3" /></svg>;
  if (name === "close") return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg>;
  return <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5" /></svg>;
}

export function PropertyLeafletMap({
  properties,
  baseSearch,
  initialViewport,
  selectedId,
  onSelect,
  onPreview,
  resultCount,
  mapCount,
  returnTo,
}: {
  properties: PropertySummary[];
  baseSearch: string;
  initialViewport: MapViewport | null;
  selectedId: string;
  onSelect?: (id: string) => void;
  onPreview?: (id: string | null) => void;
  resultCount: number | null;
  mapCount: number | null;
  returnTo: string;
}) {
  const initialPoints = useMemo<MapPoint[]>(() => properties
    .filter((property): property is PropertySummary & { latitude: number; longitude: number; locationConfidence: "high" | "approximate" | "doubtful" } => property.latitude !== null && property.longitude !== null && property.locationConfidence !== "none")
    .map((property) => ({
      kind: "property",
      id: property.id,
      latitude: property.latitude,
      longitude: property.longitude,
      price: property.price,
      currency: property.currency,
      propertyType: property.propertyType,
      title: property.title,
      location: propertyLocation(property),
      locationConfidence: property.locationConfidence,
    })), [properties]);
  const [points, setPoints] = useState(initialPoints);
  const [viewport, setViewport] = useState<MapViewport | null>(initialViewport);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [applyingArea, setApplyingArea] = useState(false);
  const [error, setError] = useState("");
  const [truncated, setTruncated] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [locationPrompt, setLocationPrompt] = useState(false);
  const [locateRequest, setLocateRequest] = useState(0);
  const [resetRequest, setResetRequest] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const initialMapRequestRef = useRef(false);
  const lastQueriedViewportRef = useRef<MapViewport | null>(initialViewport);
  const fullScreenButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (initialMapRequestRef.current) return;
    const frame = requestAnimationFrame(() => setPoints(initialPoints));
    return () => cancelAnimationFrame(frame);
  }, [initialPoints]);

  useEffect(() => {
    if (!fullScreen && !locationPrompt) return;
    const previousOverflow = document.body.style.overflow;
    if (fullScreen) document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (locationPrompt) setLocationPrompt(false);
      else if (fullScreen) {
        setFullScreen(false);
        requestAnimationFrame(() => fullScreenButtonRef.current?.focus());
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [fullScreen, locationPrompt]);

  function handleViewport(next: MapViewport, persist: boolean) {
    setViewport(next);
    if (!initialMapRequestRef.current) {
      initialMapRequestRef.current = true;
      lastQueriedViewportRef.current = next;
      void searchViewport(next);
      return;
    }
    if (persist && viewportMovedMeaningfully(lastQueriedViewportRef.current, next)) setPending(true);
  }

  async function searchViewport(target: MapViewport) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError("");
    const params = new URLSearchParams(baseSearch);
    params.set("norte", String(target.north));
    params.set("este", String(target.east));
    params.set("sur", String(target.south));
    params.set("oeste", String(target.west));
    params.set("zoom", String(target.zoom));
    try {
      const response = await fetch(`/api/properties/map?${params.toString()}`, { signal: controller.signal });
      if (!response.ok) throw new Error("map request failed");
      const result = await response.json() as MapSearchResponse;
      setPoints(mergeDetailedPagePoints(result.points, initialPoints, target));
      setTruncated(result.truncated);
    } catch (requestError) {
      if ((requestError as Error).name !== "AbortError") setError("No pudimos actualizar esta zona. Podés seguir usando el listado.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  function searchArea() {
    if (!viewport) return;
    setApplyingArea(true);
    const params = new URLSearchParams(baseSearch);
    params.set("norte", String(viewport.north));
    params.set("este", String(viewport.east));
    params.set("sur", String(viewport.south));
    params.set("oeste", String(viewport.west));
    params.set("zoom", String(viewport.zoom));
    window.location.assign(`${window.location.pathname}?${params.toString()}`);
  }

  const center: [number, number] = initialViewport
    ? [(initialViewport.north + initialViewport.south) / 2, (initialViewport.east + initialViewport.west) / 2]
    : initialPoints[0] ? [initialPoints[0].latitude, initialPoints[0].longitude] : [-38.4161, -63.6167];
  const selectedPoint = initialPoints.find((point) => point.kind === "property" && point.id === selectedId);
  const displayPoints = selectedPoint && !points.some((point) => point.kind === "property" && point.id === selectedPoint.id)
    ? [...points, selectedPoint]
    : points;
  const representedCount = mapCount ?? points.reduce((total, point) => total + (point.kind === "cluster" ? point.count : 1), 0);
  const mapStatus = resultCount !== null && mapCount !== null
    ? `${resultCount.toLocaleString("es-AR")} propiedades · ${mapCount.toLocaleString("es-AR")} en el mapa`
    : `${representedCount.toLocaleString("es-AR")} ubicaciones representadas`;

  return (
    <div
      className={`interactive-map ${fullScreen ? "is-fullscreen" : ""}`}
      aria-describedby="map-alternative"
      data-rendered-map-points={displayPoints.length}
    >
      <MapContainer center={center} zoom={initialViewport?.zoom ?? (initialPoints.length ? 6 : 4)} className="h-full w-full" scrollWheelZoom>
        <CanvasTileLayer />
        <MapResizeSync />
        <MapEvents onViewport={handleViewport} locateRequest={locateRequest} onLocationError={() => setError("No pudimos acceder a tu ubicación. Podés permitirla desde el navegador o seguir explorando el mapa.")} />
        <InitialView points={initialPoints} viewport={initialViewport} resetRequest={resetRequest} />
        {displayPoints.map((point) => (
          <InteractiveMarker
            key={point.id}
            point={point}
            selected={point.kind === "property" && point.id === selectedId}
            onSelect={onSelect}
            onPreview={onPreview}
            returnTo={returnTo}
          />
        ))}
      </MapContainer>

      <div className="map-top-controls">
        <div className="map-primary-status" aria-live="polite">
          {pending ? (
            <button type="button" className="map-search-area" disabled={applyingArea} onClick={searchArea}>
              <strong>{applyingArea ? "Actualizando propiedades…" : "Buscar en esta zona"}</strong>
              {!applyingArea ? <small>Los resultados todavía son de la zona anterior</small> : null}
            </button>
          ) : loading ? (
            <span className="map-result-indicator is-updating"><span className="map-status-pulse" aria-hidden="true" />Actualizando mapa…</span>
          ) : (
            <span className="map-result-indicator" title="ERETZ comunica la confianza disponible para cada coordenada; no presume precisión exacta.">{mapStatus}</span>
          )}
        </div>
        <div className="map-icon-controls">
          <button type="button" aria-label="Volver a encuadrar resultados" title="Reencuadrar" onClick={() => { setPending(false); setResetRequest((value) => value + 1); }}><MapIcon name="frame" /></button>
          <button type="button" aria-label="Usar mi ubicación" title="Usar mi ubicación" onClick={() => setLocationPrompt(true)}><MapIcon name="location" /></button>
          <button ref={fullScreenButtonRef} type="button" aria-label={fullScreen ? "Salir de pantalla completa" : "Ver mapa en pantalla completa"} title={fullScreen ? "Salir de pantalla completa" : "Pantalla completa"} aria-pressed={fullScreen} onClick={() => setFullScreen((value) => !value)}><MapIcon name={fullScreen ? "close" : "expand"} /></button>
        </div>
      </div>

      <details className="map-confidence-legend">
        <summary>Ubicaciones</summary>
        <div>
          <p><span className="legend-marker is-high" aria-hidden="true" />Alta confianza</p>
          <p><span className="legend-marker is-approximate" aria-hidden="true" />Aproximada</p>
          <p><span className="legend-marker is-doubtful" aria-hidden="true" />Dudosa</p>
          <small>La precisión depende de la publicación original.</small>
        </div>
      </details>

      {locationPrompt ? (
        <div className="map-location-prompt" role="dialog" aria-label="Permiso de ubicación">
          <p>ERETZ usa tu ubicación solo para centrar este mapa. No la guarda ni la envía al publicador.</p>
          <div><button type="button" className="secondary-button" onClick={() => setLocationPrompt(false)}>Cancelar</button><button type="button" className="primary-button" onClick={() => { setLocationPrompt(false); setLocateRequest((value) => value + 1); }}>Permitir y centrar</button></div>
        </div>
      ) : null}
      {error ? <div className="map-error" role="alert">{error} <button type="button" onClick={() => { if (viewport) void searchViewport(viewport); }}>Reintentar</button></div> : null}
      {truncated ? <p className="map-truncated">Acercá el mapa para ver esta zona con más detalle.</p> : null}
    </div>
  );
}
