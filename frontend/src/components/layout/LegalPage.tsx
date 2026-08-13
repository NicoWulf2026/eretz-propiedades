import type { ReactNode } from "react";
import Link from "next/link";
import { SiteShell } from "@/components/layout/SiteShell";

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return <SiteShell><article className="container max-w-3xl py-12 sm:py-16"><Link href="/" className="text-sm font-bold text-[color:var(--accent-soft)]">← Volver al inicio</Link><h1 className="mt-6 text-4xl font-black tracking-tight text-[color:var(--ink)]">{title}</h1><p className="mt-3 text-sm u-text-muted">{updated}</p><div className="legal-copy mt-10">{children}</div></article></SiteShell>;
}
