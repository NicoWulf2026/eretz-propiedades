import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";
export default function NotFound() { return <SiteShell><div className="container grid min-h-[60vh] place-items-center py-16 text-center"><div><p className="eyebrow">Error 404</p><h1 className="mt-3 text-4xl font-black text-[color:var(--ink)]">No encontramos esta página</h1><p className="mx-auto mt-4 max-w-lg u-text-muted">Puede haber cambiado de dirección, haberse retirado o ya no estar disponible.</p><div className="mt-7 flex flex-wrap justify-center gap-3"><Link className="primary-button" href="/propiedades">Explorar propiedades</Link><Link className="secondary-button" href="/">Volver al inicio</Link></div></div></div></SiteShell>; }

