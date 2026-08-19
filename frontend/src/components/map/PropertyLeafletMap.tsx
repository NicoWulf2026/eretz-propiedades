"use client";

import L, { type LatLngBounds } from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Popup, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { propertyLocation } from "@/lib/property-presenter";
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
    return () => {
      layer.removeFrom(map);
    };
  }, [map]);
  return null;
}

function markerIcon(point: MapPoint, selected: boolean) {
  if (point.kind === "cluster") {
    return L.divIcon({
      className: "",
      html: `<span class="eretz-map-cluster" aria-label="${point.count} propiedades">${point.count > 999 ? "999+" : point.count}</span>`,
      iconSize: [44, 44], iconAnchor: [22, 22],
    });
  }
  const price = point.price && point.currency
    ? `${point.currency === "USD" ? "US$" : point.currency} ${Intl.NumberFormat("es-AR", { notation: "compact", maximumFractionDigits: 1 }).format(point.price)}`
    : "Ver";
  return L.divIcon({
    className: "",
    html: `<span class="eretz-price-marker${selected ? " is-selected" : ""}">${price}</span>`,
    iconAnchor: [36, 18], popupAnchor: [0, -20],
  });
}

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
    locationfound(event) { map.setView(event.latlng, Math.max(map.getZoom(), 14)); },
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

export function PropertyLeafletMap({
  properties,
  baseSearch,
  initialViewport,
  selectedId,
  onSelect,
  returnTo,
}: {
  properties: PropertySummary[];
  baseSearch: string;
  initialViewport: MapViewport | null;
  selectedId: string;
  onSelect?: (id: string) => void;
  returnTo: string;
}) {
  const initialPoints = useMemo<MapPoint[]>(() => properties
    .filter((property): property is PropertySummary & { latitude: number; longitude: number } => property.latitude !== null && property.longitude !== null)
    .map((property) => ({ kind: "property", id: property.id, latitude: property.latitude, longitude: property.longitude, price: property.price, currency: property.currency, title: property.title, location: propertyLocation(property) })), [properties]);
  const [points, setPoints] = useState(initialPoints);
  const [viewport, setViewport] = useState<MapViewport | null>(initialViewport);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [truncated, setTruncated] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [locationPrompt, setLocationPrompt] = useState(false);
  const [locateRequest, setLocateRequest] = useState(0);
  const [resetRequest, setResetRequest] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const initialMapRequestRef = useRef(false);

  useEffect(() => {
    // Once the map owns its viewport query, its complete/clustered response is
    // authoritative. A slower rail response must not replace it with the
    // coordinates from only the current 24-card page.
    if (initialMapRequestRef.current) return;
    const frame = requestAnimationFrame(() => setPoints(initialPoints));
    return () => cancelAnimationFrame(frame);
  }, [initialPoints]);

  function handleViewport(next: MapViewport, persist: boolean) {
    setViewport(next);
    if (!initialMapRequestRef.current) {
      initialMapRequestRef.current = true;
      setPending(true);
      void searchViewport(next);
      return;
    }
    // Mover el mapa sólo propone una zona pendiente: no cambia URL, listado ni
    // conteos ni reinicia el cursor. La aplicación ocurre en "Buscar en esta zona".
    if (persist) setPending(true);
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
      setPoints(result.points);
      setTruncated(result.truncated);
      setPending(false);
    } catch (requestError) {
      if ((requestError as Error).name !== "AbortError") setError("No pudimos actualizar esta zona. Podés seguir usando el listado.");
    } finally {
      setLoading(false);
    }
  }

  // "Buscar en esta zona": promueve la zona pendiente a viewport aplicado sobre
  // TODO el explorador -> navega con la zona + reinicio de cursor, de modo que el
  // servidor re-consulta listado, conteos y mapa. Conserva el resto de los filtros.
  function searchArea() {
    if (!viewport) return;
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

  return (
    <div className={`interactive-map ${fullScreen ? "is-fullscreen" : ""}`} aria-describedby="map-alternative">
      <MapContainer center={center} zoom={initialViewport?.zoom ?? (initialPoints.length ? 6 : 4)} className="h-full w-full" scrollWheelZoom>
        <CanvasTileLayer />
        <MapEvents onViewport={handleViewport} locateRequest={locateRequest} onLocationError={() => setError("No pudimos acceder a tu ubicación. Podés permitirla desde el navegador o seguir explorando el mapa.")} />
        <InitialView points={initialPoints} viewport={initialViewport} resetRequest={resetRequest} />
        {points.map((point) => (
          <Marker
            key={point.id}
            position={[point.latitude, point.longitude]}
            icon={markerIcon(point, point.kind === "property" && point.id === selectedId)}
            eventHandlers={{ click: (event) => {
              if (point.kind === "cluster") event.target._map.setView([point.latitude, point.longitude], event.target._map.getZoom() + 2);
              else onSelect?.(point.id);
            } }}
          >
            {point.kind === "property" ? <Popup><a href={`/propiedad/${point.id}?volver=${encodeURIComponent(returnTo)}`} className="map-popup"><strong>{point.price && point.currency ? `${point.currency} ${Intl.NumberFormat("es-AR").format(point.price)}` : "Precio a consultar"}</strong><span>{point.title}</span><small>{point.location}</small></a></Popup> : null}
          </Marker>
        ))}
      </MapContainer>
      <div className="map-top-controls">
        {pending ? <button type="button" className="map-search-area" disabled={loading} onClick={searchArea}>{loading ? "Buscando…" : "Buscar en esta zona"}</button> : <span className="map-result-indicator">{points.length.toLocaleString("es-AR")} puntos visibles</span>}
        <div className="map-icon-controls">
          <button type="button" aria-label="Volver a encuadrar resultados" title="Recentrar resultados" onClick={() => setResetRequest((value) => value + 1)}>◎</button>
          <button type="button" aria-label="Usar mi ubicación" title="Usar mi ubicación" onClick={() => setLocationPrompt(true)}>⌖</button>
          <button type="button" aria-label={fullScreen ? "Salir de pantalla completa" : "Ver mapa en pantalla completa"} onClick={() => setFullScreen((value) => !value)}>{fullScreen ? "×" : "⛶"}</button>
        </div>
      </div>
      {locationPrompt ? <div className="map-location-prompt" role="dialog" aria-label="Permiso de ubicación"><p>ERETZ usa tu ubicación solo para centrar este mapa. No la guarda ni la envía al publicador.</p><div><button type="button" className="secondary-button" onClick={() => setLocationPrompt(false)}>Cancelar</button><button type="button" className="primary-button" onClick={() => { setLocationPrompt(false); setLocateRequest((value) => value + 1); }}>Permitir y centrar</button></div></div> : null}
      {error ? <div className="map-error" role="alert">{error} <button type="button" onClick={searchArea}>Reintentar</button></div> : null}
      {truncated ? <p className="map-truncated">Acercá el mapa para ver esta zona con más detalle.</p> : null}
    </div>
  );
}
