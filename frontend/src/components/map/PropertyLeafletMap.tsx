"use client";

import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { propertyLocation, propertyPrice } from "@/lib/property-presenter";
import type { Property } from "@/types/property";

const marker = L.divIcon({
  className: "",
  html: '<span class="eretz-map-marker" aria-hidden="true"></span>',
  iconAnchor: [10, 20],
  popupAnchor: [0, -18],
});

export function PropertyLeafletMap({ properties }: { properties: Property[] }) {
  const points = properties.filter(
    (property): property is Property & { latitude: number; longitude: number } =>
      property.latitude !== null && property.longitude !== null,
  );
  const center: [number, number] = points.length
    ? [points.reduce((sum, p) => sum + p.latitude, 0) / points.length, points.reduce((sum, p) => sum + p.longitude, 0) / points.length]
    : [-34.6037, -58.3816];

  return (
    <MapContainer center={center} zoom={points.length === 1 ? 14 : 5} className="h-full w-full" scrollWheelZoom={false}>
      <TileLayer attribution="© OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {points.map((property) => (
        <Marker key={property.id} position={[property.latitude, property.longitude]} icon={marker}>
          <Popup>
            <a href={`/propiedad/${property.id}`} className="block min-w-48 font-sans">
              <strong>{propertyPrice(property)}</strong>
              <span className="mt-1 block text-xs">{propertyLocation(property)}</span>
            </a>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

