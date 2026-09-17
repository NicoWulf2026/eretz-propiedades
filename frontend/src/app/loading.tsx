import { SiteShell } from "@/components/layout/SiteShell";

export default function Loading() {
  return (
    <SiteShell>
      <div className="container page-loading-shell" role="status" aria-label="Cargando página">
        <div className="skeleton h-4 w-32" />
        <div className="skeleton mt-4 h-10 w-80 max-w-full" />
        <div className="skeleton mt-3 h-5 w-[32rem] max-w-full" />
        <div className="mt-8 grid gap-5 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => <div key={index} className="skeleton h-72 rounded-2xl" />)}
        </div>
        <span className="sr-only">Cargando contenido…</span>
      </div>
    </SiteShell>
  );
}
