"use client";
import { useEffect } from "react";
import { track } from "@/lib/analytics";
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => track("load_error", { route: window.location.pathname }), []);
  return <main className="grid min-h-screen place-items-center bg-[color:var(--canvas)] p-6 text-center"><div><p className="eyebrow">Algo salió mal</p><h1 className="mt-3 text-3xl font-black text-[color:var(--ink)]">No pudimos cargar esta página</h1><p className="mt-3 text-slate-600">Tu información está segura. Podés volver a intentar.</p><button type="button" className="primary-button mt-6" onClick={reset}>Reintentar</button></div></main>;
}

