import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";
export default function NotFound() { return <SiteShell><div className="container grid min-h-[60vh] place-items-center py-16 text-center"><div><p className="eyebrow">Error 404</p><h1 className="mt-3 text-4xl font-black text-[color:var(--ink)]">No encontramos esta propiedad</h1><p className="mx-auto mt-4 max-w-lg text-slate-600">Puede haberse despublicado, cambiado o la dirección no es válida.</p><Link className="primary-button mt-7" href="/propiedades">Ver propiedades activas</Link></div></div></SiteShell>; }

