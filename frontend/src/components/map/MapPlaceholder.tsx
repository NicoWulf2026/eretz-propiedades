import type { Property } from "@/types/property";

type MapPlaceholderProps = {
  properties: Property[];
};

type PropertyWithCoordinates = Property & {
  latitude: number;
  longitude: number;
};

type Bounds = {
  minLatitude: number;
  maxLatitude: number;
  minLongitude: number;
  maxLongitude: number;
};

function hasCoordinates(property: Property): property is PropertyWithCoordinates {
  return (
    typeof property.latitude === "number" &&
    Number.isFinite(property.latitude) &&
    typeof property.longitude === "number" &&
    Number.isFinite(property.longitude)
  );
}

function getBounds(properties: PropertyWithCoordinates[]): Bounds {
  return properties.reduce(
    (bounds, property) => ({
      minLatitude: Math.min(bounds.minLatitude, property.latitude),
      maxLatitude: Math.max(bounds.maxLatitude, property.latitude),
      minLongitude: Math.min(bounds.minLongitude, property.longitude),
      maxLongitude: Math.max(bounds.maxLongitude, property.longitude),
    }),
    {
      minLatitude: properties[0]?.latitude ?? -34.6,
      maxLatitude: properties[0]?.latitude ?? -34.6,
      minLongitude: properties[0]?.longitude ?? -58.45,
      maxLongitude: properties[0]?.longitude ?? -58.45,
    },
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function getPinPosition(property: PropertyWithCoordinates, bounds: Bounds, index: number) {
  const latitudeRange = bounds.maxLatitude - bounds.minLatitude;
  const longitudeRange = bounds.maxLongitude - bounds.minLongitude;
  const fallbackOffset = (index % 5) * 7;
  const jitterX = ((index % 3) - 1) * 3.5;
  const jitterY = (Math.floor((index % 6) / 3) - 0.5) * 5;

  const x =
    longitudeRange === 0
      ? 50 + fallbackOffset - 14
      : ((property.longitude - bounds.minLongitude) / longitudeRange) * 76 + 12;
  const y =
    latitudeRange === 0
      ? 50 - fallbackOffset + 10
      : (1 - (property.latitude - bounds.minLatitude) / latitudeRange) * 68 + 16;

  return {
    left: `${clamp(x + jitterX, 10, 88)}%`,
    top: `${clamp(y + jitterY, 16, 84)}%`,
  };
}

function formatPrice(currency: Property["currency"], price: number) {
  if (!Number.isFinite(price) || price <= 0) {
    return "Consultar";
  }

  if (price >= 1000000) {
    const compact = new Intl.NumberFormat("es-AR", {
      maximumFractionDigits: price >= 10000000 ? 0 : 1,
    }).format(price / 1000000);

    return `${currency} ${compact}M`;
  }

  if (price >= 100000) {
    return `${currency} ${Math.round(price / 1000)}k`;
  }

  return `${currency} ${new Intl.NumberFormat("es-AR").format(price)}`;
}

function formatFullPrice(currency: Property["currency"], price: number) {
  if (!Number.isFinite(price) || price <= 0) {
    return "Precio a consultar";
  }

  return `${currency} ${new Intl.NumberFormat("es-AR").format(price)}`;
}

function getLocation(property: Property) {
  return property.neighborhood || property.city || "Ubicaci\u00f3n";
}

function getHighlightedZone(properties: PropertyWithCoordinates[]) {
  const firstProperty = properties[0];

  if (!firstProperty) {
    return {
      name: "Zona destacada",
      pricePerSquareMeter: null,
      currency: "USD" as Property["currency"],
    };
  }

  const currency = firstProperty.currency;
  const propertiesWithArea = properties.filter(
    (property) =>
      property.currency === currency && property.totalArea > 0 && property.price > 0,
  );
  const averagePricePerSquareMeter =
    propertiesWithArea.length > 0
      ? Math.round(
          propertiesWithArea.reduce(
            (total, property) => total + property.price / property.totalArea,
            0,
          ) / propertiesWithArea.length,
        )
      : null;

  return {
    name: getLocation(firstProperty),
    pricePerSquareMeter: averagePricePerSquareMeter,
    currency,
  };
}

function getClusters(properties: PropertyWithCoordinates[]) {
  const groupedProperties = new Map<string, PropertyWithCoordinates[]>();

  properties.forEach((property) => {
    const key = property.city || property.neighborhood || "Zona";
    const group = groupedProperties.get(key) ?? [];
    group.push(property);
    groupedProperties.set(key, group);
  });

  return Array.from(groupedProperties.entries())
    .filter(([, group]) => group.length > 1)
    .slice(0, 3)
    .map(([label, group], index) => ({
      label,
      count: group.length,
      className:
        index === 0
          ? "left-[43%] top-[32%]"
          : index === 1
            ? "right-[24%] bottom-[30%]"
            : "left-[18%] bottom-[35%]",
    }));
}

export function MapPlaceholder({ properties }: MapPlaceholderProps) {
  const propertiesWithCoordinates = properties.filter(hasCoordinates);
  const bounds = getBounds(propertiesWithCoordinates);
  const highlightedZone = getHighlightedZone(propertiesWithCoordinates);
  const clusters = getClusters(propertiesWithCoordinates);
  const visiblePins = propertiesWithCoordinates.slice(0, 12);

  return (
    <section
      id="map"
      className="min-h-[430px] overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-lift lg:sticky lg:top-20 lg:h-[calc(100vh-5.5rem)] lg:min-h-[720px]"
    >
      <div className="relative flex h-full min-h-[430px] flex-col bg-[#eef3f8] lg:min-h-[720px]">
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(6,21,40,0.07)_1px,transparent_1px),linear-gradient(0deg,rgba(6,21,40,0.07)_1px,transparent_1px)] bg-[size:54px_54px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_24%_24%,rgba(200,164,93,0.18),transparent_17rem),radial-gradient(circle_at_72%_66%,rgba(24,58,99,0.16),transparent_22rem)]" />
        <div className="absolute left-[8%] top-[18%] h-40 w-[62%] rotate-[-8deg] rounded-full border border-gold-500/45 bg-gold-500/10" />
        <div className="absolute bottom-[18%] right-[10%] h-36 w-[46%] rotate-[12deg] rounded-full border border-ink-700/18 bg-white/24" />

        <div className="relative z-10 flex items-center justify-between gap-3 border-b border-ink-950/10 bg-white/88 px-4 py-3 backdrop-blur">
          <div>
            <h2 className="text-sm font-semibold text-ink-950">Mapa interactivo</h2>
            <p className="text-xs text-ink-950/54">
              Pins simulados desde coordenadas reales de Supabase
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="rounded-md bg-ink-950 px-3 py-1 text-xs font-semibold text-white">
              {propertiesWithCoordinates.length}
              {" con ubicaci\u00f3n"}
            </span>
            <span className="hidden rounded-md border border-ink-950/10 bg-white px-3 py-1 text-xs font-semibold text-ink-950/70 sm:inline-flex">
              Precio/m2
            </span>
          </div>
        </div>

        <div className="relative z-10 flex flex-1 items-center justify-center p-5">
          <div className="absolute left-5 top-20 hidden w-60 rounded-lg border border-ink-950/10 bg-white/92 p-4 shadow-soft backdrop-blur md:block">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gold-500">
              Zona destacada
            </p>
            <p className="mt-2 text-lg font-semibold text-ink-950">{highlightedZone.name}</p>
            {highlightedZone.pricePerSquareMeter ? (
              <p className="mt-1 text-sm font-semibold text-ink-950">
                {formatFullPrice(
                  highlightedZone.currency,
                  highlightedZone.pricePerSquareMeter,
                )}{" "}
                / m2
              </p>
            ) : (
              <p className="mt-1 text-sm font-semibold text-ink-950">
                {propertiesWithCoordinates.length} propiedades activas
              </p>
            )}
            <p className="mt-2 text-xs leading-5 text-ink-950/58">
              Vista preparada para mapas reales, clusters y zonas desde Supabase.
            </p>
          </div>

          {visiblePins.map((property, index) => {
            const position = getPinPosition(property, bounds, index);
            const isPrimary = index === 0;

            return (
              <div
                key={property.id}
                className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full px-3 py-2 text-left text-xs font-bold shadow-lift ring-1 ring-ink-950/10 transition hover:z-20 hover:-translate-y-[55%] ${
                  isPrimary ? "bg-ink-950 text-white" : "bg-white text-ink-950"
                }`}
                style={position}
              >
                <span className="block whitespace-nowrap">
                  {formatPrice(property.currency, property.price)}
                </span>
                <span
                  className={`block max-w-[8rem] truncate text-[10px] font-semibold ${
                    isPrimary ? "text-white/70" : "text-ink-950/56"
                  }`}
                >
                  {getLocation(property)}
                </span>
              </div>
            );
          })}

          {clusters.map((cluster) => (
            <div
              key={cluster.label}
              className={`absolute grid size-12 place-items-center rounded-full bg-gold-500 text-sm font-black text-ink-950 shadow-[0_0_0_10px_rgba(200,164,93,0.18)] ${cluster.className}`}
              title={cluster.label}
            >
              {cluster.count}
            </div>
          ))}

          <div className="absolute bottom-5 left-5 hidden gap-2 md:flex">
            {["Zonas", "Tr\u00e1nsito", "Amenities"].map((layer) => (
              <button
                key={layer}
                className="rounded-md border border-ink-950/10 bg-white/92 px-3 py-2 text-xs font-semibold text-ink-950/72 shadow-sm backdrop-blur"
                type="button"
              >
                {layer}
              </button>
            ))}
          </div>

          <div className="max-w-sm rounded-lg border border-ink-950/10 bg-white/92 p-5 text-center shadow-soft backdrop-blur">
            <p className="text-sm font-semibold text-ink-950">
              {propertiesWithCoordinates.length > 0
                ? `${propertiesWithCoordinates.length} propiedades geolocalizadas`
                : "Sin coordenadas disponibles"}
            </p>
            <p className="mt-2 text-sm leading-6 text-ink-950/62">
              Placeholder visual con pins generados desde las propiedades reales.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
