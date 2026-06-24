import type { ReactNode } from "react";

type HeroSectionProps = {
  children: ReactNode;
  totalProperties?: number;
  totalZones?: number;
};

export function HeroSection({
  children,
  totalProperties = 0,
  totalZones = 0,
}: HeroSectionProps) {
  const propertiesLabel =
    totalProperties > 0 ? totalProperties.toLocaleString("es-AR") : "0";
  const zonesLabel = totalZones > 0 ? totalZones.toLocaleString("es-AR") : "0";

  return (
    <section className="relative overflow-hidden bg-ink-950 text-white">
      <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(6,21,40,0.96)_0%,rgba(10,31,58,0.84)_100%),url('https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1800&q=80')] bg-cover bg-center" />
      <div className="absolute right-0 top-0 h-px w-2/3 bg-gradient-to-l from-gold-500/28 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-px bg-white/8" />

      <div className="relative mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-5 sm:py-8 lg:px-6 lg:py-10">
        <div className="mb-5 sm:mb-6">
          <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.22em] text-gold-400/90 sm:mb-3">
            ERETZ Propiedades
          </p>

          <h1 className="max-w-2xl text-2xl font-bold leading-tight tracking-tight sm:text-3xl lg:text-[2.75rem] lg:leading-[1.15]">
            Propiedades en Argentina{" "}
            <span className="text-white/78">con búsqueda y mapa.</span>
          </h1>

          <p className="mt-2 hidden max-w-xl text-sm leading-relaxed text-white/58 sm:mt-3 sm:block">
            Avisos, zonas y señales de mercado para comprar, alquilar o invertir con más claridad.
          </p>
        </div>

        <div
          id="search"
          className="overflow-visible rounded-lg border border-white/14 bg-white shadow-[0_16px_48px_rgba(6,21,40,0.38)]"
        >
          <div className="p-2.5 sm:p-3">{children}</div>
        </div>

        <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 sm:mt-4">
          {totalProperties > 0 ? (
            <>
              <p className="text-xs text-white/46">
                <span className="font-semibold text-white/82">{propertiesLabel}</span>{" "}
                avisos activos
              </p>
              <div className="h-3 w-px bg-white/16" aria-hidden="true" />
              <p className="text-xs text-white/46">
                <span className="font-semibold text-white/82">{zonesLabel}</span> zonas
              </p>
              <div className="h-3 w-px bg-white/16" aria-hidden="true" />
            </>
          ) : null}
          <p className="text-xs text-white/46">
            <span className="font-semibold text-white/82">IA</span> asistente activo
          </p>
        </div>
      </div>
    </section>
  );
}
