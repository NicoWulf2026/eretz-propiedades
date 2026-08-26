import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";

export default function PropertyNotFound() {
  return (
    <SiteShell>
      <div className="container grid min-h-[60vh] place-items-center py-16 text-center">
        <div>
          <p className="eyebrow">Propiedad no disponible</p>
          <h1 className="mt-3 text-4xl font-black text-[color:var(--ink)]">No encontramos esta propiedad</h1>
          <p className="mx-auto mt-4 max-w-lg u-text-muted">Puede haberse retirado, cambiado o no estar habilitada para mostrarse.</p>
          <Link className="primary-button mt-7" href="/propiedades">Explorar propiedades</Link>
        </div>
      </div>
    </SiteShell>
  );
}
