import { getPropertiesFromSupabase } from "@/lib/property-supabase-service";
import type { Property } from "@/types/property";

export const dynamic = "force-dynamic";

function formatPrice(property: Property) {
  return `${property.currency} ${property.price.toLocaleString("es-AR")}`;
}

async function loadProperties() {
  try {
    const properties = await getPropertiesFromSupabase({
      limit: 10,
      throwOnError: true,
    });

    return { properties, error: null };
  } catch (error) {
    return {
      properties: [],
      error: error instanceof Error ? error.message : "Error desconocido al consultar Supabase.",
    };
  }
}

export default async function DebugSupabasePage() {
  const { properties, error } = await loadProperties();

  return (
    <main className="min-h-screen bg-[#f6f8fb] px-4 py-8 text-ink-950 sm:px-6 lg:px-8">
      <section className="mx-auto max-w-5xl">
        <div className="rounded-lg border border-ink-950/10 bg-white p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gold-500">
            Debug Supabase
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Propiedades desde Supabase</h1>
          <p className="mt-3 text-sm text-ink-950/62">
            Prueba tecnica aislada usando la misma carga de datos que la home.
          </p>

          <div className="mt-5 rounded-md bg-ink-950 px-4 py-3 text-sm font-semibold text-white">
            Propiedades recibidas: {properties.length}
          </div>

          {error ? (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              Error al consultar Supabase: {error}
            </div>
          ) : null}

          {!error && properties.length === 0 ? (
            <div className="mt-4 rounded-md border border-ink-950/10 bg-ink-950/[0.03] px-4 py-3 text-sm text-ink-950/70">
              No se recibieron propiedades activas desde Supabase.
            </div>
          ) : null}
        </div>

        <div className="mt-5 grid gap-4">
          {properties.map((property) => (
            <article
              key={property.id}
              className="rounded-lg border border-ink-950/10 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-lg font-semibold">{property.title}</h2>
                  <p className="mt-1 text-sm text-ink-950/58">
                    {property.neighborhood}, {property.city}
                  </p>
                </div>
                <span className="rounded-md bg-ink-950 px-3 py-1 text-sm font-semibold text-white">
                  {property.status}
                </span>
              </div>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-ink-950/48">Precio</dt>
                  <dd className="font-semibold">{formatPrice(property)}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Moneda</dt>
                  <dd className="font-semibold">{property.currency}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Ciudad</dt>
                  <dd className="font-semibold">{property.city || "Sin dato"}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Barrio</dt>
                  <dd className="font-semibold">{property.neighborhood || "Sin dato"}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Latitud</dt>
                  <dd className="font-semibold">{property.latitude ?? "Sin dato"}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Longitud</dt>
                  <dd className="font-semibold">{property.longitude ?? "Sin dato"}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Operación</dt>
                  <dd className="font-semibold">{property.operation}</dd>
                </div>
                <div>
                  <dt className="text-ink-950/48">Tipo</dt>
                  <dd className="font-semibold">{property.propertyType}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
