"use client";

import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import { getOriginalPublishedPriceLabel } from "@/lib/analysis-currency";
import type { LatLngBoundsExpression, LatLngExpression } from "leaflet";
import type { Property, PropertyOperation, PropertyType } from "@/types/property";

// ─── Types ───────────────────────────────────────────────────────────────────

export type FlyToTarget = { lat: number; lng: number; id: string } | null;

type PropertyLeafletMapProps = {
  properties: Property[];
  selectedPropertyId?: string | null;
  onSelectProperty?: (id: string) => void;
  flyToTarget?: FlyToTarget;
};

type GeolocatedProperty = Property & {
  latitude: number;
  longitude: number;
};

type ClusterMarker = {
  id: string;
  count: number;
  latitude: number;
  longitude: number;
};

// ─── Constants ────────────────────────────────────────────────────────────────

const defaultCenter: LatLngExpression = [-31.6333, -60.7];
const priceMarkerZoom = 15;
const simpleMarkerZoom = 13;
const denseResultLimit = 80;

// ─── Label maps ──────────────────────────────────────────────────────────────

const operationLabels: Record<PropertyOperation, string> = {
  venta: "Venta",
  alquiler: "Alquiler",
  inversion: "En pozo",
  temporario: "Temporario",
  consultar: "Consultar",
  venta_y_alquiler: "V+A",
};

const typeLabels: Record<PropertyType, string> = {
  departamento: "Departamento",
  casa: "Casa",
  ph: "PH",
  terreno: "Terreno",
  oficina: "Oficina",
  local: "Local",
  otro: "Propiedad",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function hasCoordinates(property: Property): property is GeolocatedProperty {
  return (
    typeof property.latitude === "number" &&
    Number.isFinite(property.latitude) &&
    typeof property.longitude === "number" &&
    Number.isFinite(property.longitude)
  );
}

function getLocation(property: Property) {
  const parts = [property.neighborhood, property.city].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : property.province || "Argentina";
}

// ─── Icon creators ────────────────────────────────────────────────────────────

function createPriceIcon(property: Property) {
  return L.divIcon({
    className: "inmocapital-leaflet-marker",
    html: `<span>${getOriginalPublishedPriceLabel(property)}</span>`,
    iconAnchor: [52, 18],
    iconSize: [104, 36],
    popupAnchor: [0, -18],
  });
}

function createSelectedPriceIcon(property: Property) {
  return L.divIcon({
    className: "inmocapital-leaflet-marker inmocapital-leaflet-marker--selected",
    html: `<span>${getOriginalPublishedPriceLabel(property)}</span>`,
    iconAnchor: [52, 18],
    iconSize: [104, 36],
    popupAnchor: [0, -18],
  });
}

function createSimpleIcon(property: Property) {
  if (property.operation === "venta_y_alquiler") {
    return L.divIcon({
      className:
        "inmocapital-leaflet-marker inmocapital-leaflet-marker--dot inmocapital-leaflet-marker--venta-alquiler",
      html: `<span>V+A</span>`,
      iconAnchor: [14, 9],
      iconSize: [28, 18],
      popupAnchor: [0, -10],
    });
  }
  return L.divIcon({
    className: "inmocapital-leaflet-marker inmocapital-leaflet-marker--dot",
    html: `<span>${operationLabels[property.operation].slice(0, 1)}</span>`,
    iconAnchor: [9, 9],
    iconSize: [18, 18],
    popupAnchor: [0, -10],
  });
}

function createSelectedDotIcon() {
  return L.divIcon({
    className:
      "inmocapital-leaflet-marker inmocapital-leaflet-marker--dot inmocapital-leaflet-marker--selected",
    html: "",
    iconAnchor: [11, 11],
    iconSize: [22, 22],
    popupAnchor: [0, -12],
  });
}

function createClusterIcon(cluster: ClusterMarker) {
  return L.divIcon({
    className: "inmocapital-leaflet-marker inmocapital-leaflet-marker--cluster",
    html: `<span>${cluster.count}</span>`,
    iconAnchor: [19, 19],
    iconSize: [38, 38],
    popupAnchor: [0, -18],
  });
}

// ─── Clustering ───────────────────────────────────────────────────────────────

function getClusterPrecision(zoom: number) {
  if (zoom <= 9) return 0.18;
  if (zoom <= 10) return 0.1;
  if (zoom <= 11) return 0.06;
  return 0.035;
}

function buildClusters(properties: GeolocatedProperty[], zoom: number): ClusterMarker[] {
  const precision = getClusterPrecision(zoom);
  const clusters = new Map<string, { count: number; latitudeSum: number; longitudeSum: number }>();

  properties.forEach((property) => {
    const latBucket = Math.round(property.latitude / precision);
    const lonBucket = Math.round(property.longitude / precision);
    const key = `${latBucket}:${lonBucket}`;
    const current = clusters.get(key);
    if (current) {
      current.count += 1;
      current.latitudeSum += property.latitude;
      current.longitudeSum += property.longitude;
      return;
    }
    clusters.set(key, { count: 1, latitudeSum: property.latitude, longitudeSum: property.longitude });
  });

  return Array.from(clusters.entries()).map(([id, c]) => ({
    id,
    count: c.count,
    latitude: c.latitudeSum / c.count,
    longitude: c.longitudeSum / c.count,
  }));
}

// ─── Map sub-components ───────────────────────────────────────────────────────

function MapZoomState({ onZoomChange }: { onZoomChange: (zoom: number) => void }) {
  const map = useMapEvents({
    zoomend() {
      onZoomChange(map.getZoom());
    },
  });

  useEffect(() => {
    onZoomChange(map.getZoom());
  }, [map, onZoomChange]);

  return null;
}

function FitMapToProperties({ properties }: { properties: GeolocatedProperty[] }) {
  const map = useMap();

  useEffect(() => {
    window.requestAnimationFrame(() => {
      map.invalidateSize();
    });

    if (properties.length === 0) {
      map.setView(defaultCenter, 12);
      return;
    }

    if (properties.length === 1) {
      map.setView([properties[0].latitude, properties[0].longitude], 14);
      return;
    }

    const bounds: LatLngBoundsExpression = properties.map((p) => [p.latitude, p.longitude]);
    map.fitBounds(bounds, { maxZoom: 13, padding: [48, 48] });
  }, [map, properties]);

  return null;
}

// Flies to a selected property without touching fitBounds.
function MapFlyTo({ target }: { target: FlyToTarget }) {
  const map = useMap();
  const prevId = useRef<string | null>(null);

  useEffect(() => {
    if (!target) {
      prevId.current = null; // reset so re-selecting the same property flies again
      return;
    }
    if (target.id === prevId.current) return;
    prevId.current = target.id;
    map.flyTo([target.lat, target.lng], Math.max(map.getZoom(), 14), {
      animate: true,
      duration: 0.8,
    });
  }, [map, target]);

  return null;
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PropertyLeafletMap({
  properties,
  selectedPropertyId,
  onSelectProperty,
  flyToTarget,
}: PropertyLeafletMapProps) {
  const geolocatedProperties = useMemo(() => properties.filter(hasCoordinates), [properties]);
  const [zoom, setZoom] = useState(12);

  const shouldCluster =
    geolocatedProperties.length > denseResultLimit && zoom < simpleMarkerZoom;
  const shouldShowPriceMarkers =
    zoom >= priceMarkerZoom || geolocatedProperties.length <= denseResultLimit;

  const clusters = useMemo(
    () => (shouldCluster ? buildClusters(geolocatedProperties, zoom) : []),
    [geolocatedProperties, shouldCluster, zoom],
  );

  return (
    <MapContainer
      attributionControl={false}
      center={defaultCenter}
      className="h-full min-h-[360px] w-full"
      scrollWheelZoom
      zoom={12}
      zoomControl
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitMapToProperties properties={geolocatedProperties} />
      <MapZoomState onZoomChange={setZoom} />
      <MapFlyTo target={flyToTarget ?? null} />

      {shouldCluster
        ? clusters.map((cluster) => (
            <Marker
              icon={createClusterIcon(cluster)}
              key={cluster.id}
              position={[cluster.latitude, cluster.longitude]}
            >
              <Popup>
                <div className="min-w-[180px] font-sans text-ink-950">
                  <p className="text-sm font-semibold">{cluster.count} propiedades</p>
                  <p className="mt-1 text-xs leading-5 text-ink-950/62">
                    Acercá el mapa para ver precios y detalles.
                  </p>
                </div>
              </Popup>
            </Marker>
          ))
        : geolocatedProperties.map((property) => {
            const isSelected = property.id === selectedPropertyId;
            const icon = isSelected
              ? shouldShowPriceMarkers
                ? createSelectedPriceIcon(property)
                : createSelectedDotIcon()
              : shouldShowPriceMarkers
              ? createPriceIcon(property)
              : createSimpleIcon(property);

            return (
              <Marker
                eventHandlers={
                  onSelectProperty
                    ? { click: () => onSelectProperty(property.id) }
                    : undefined
                }
                icon={icon}
                key={property.id}
                position={[property.latitude, property.longitude]}
                zIndexOffset={isSelected ? 1000 : 0}
              >
                <Popup>
                  <div className="min-w-[210px] font-sans text-ink-950">
                    <p className="text-sm font-semibold leading-snug">
                      {property.title || "Propiedad"}
                    </p>
                    <p className="mt-1 text-lg font-semibold">
                      {getOriginalPublishedPriceLabel(property)}
                    </p>
                    <p className="mt-1 text-xs text-ink-950/60">{getLocation(property)}</p>
                    <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-semibold">
                      <span className="rounded-md bg-ink-950 px-2 py-1 text-white">
                        {operationLabels[property.operation]}
                      </span>
                      <span className="rounded-md bg-ink-950/[0.06] px-2 py-1 text-ink-950/70">
                        {typeLabels[property.propertyType]}
                      </span>
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}
    </MapContainer>
  );
}
