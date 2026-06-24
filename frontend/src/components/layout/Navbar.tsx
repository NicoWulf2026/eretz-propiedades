"use client";

import Link from "next/link";
import { useState } from "react";

const navItems = [
  { label: "Propiedades", href: "#properties" },
  { label: "Mapa", href: "#map" },
];

/**
 * Logo de InmoCapital.
 *
 * INSTRUCCIONES PARA REEMPLAZAR CON EL LOGO REAL:
 * 1. Colocar los archivos en: frontend/public/brand/
 *    - logo-horizontal-white.svg  -> para fondo oscuro (navbar, hero)
 *    - logo-horizontal-dark.svg   -> para fondo claro
 *    - logo-icon-white.svg        -> icono solo, fondo oscuro
 *    - logo-icon-dark.svg         -> icono solo, fondo claro
 *
 * 2. Reemplazar el bloque <WordmarkFallback /> de abajo por:
 *    <img
 *      src="/brand/logo-horizontal-white.svg"
 *      alt="InmoCapital"
 *      className="h-8 w-auto"
 *    />
 */
function WordmarkFallback() {
  return (
    <span className="flex items-center gap-2.5">
      <span
        className="grid size-8 place-items-center rounded bg-white/95 text-[11px] font-black leading-none text-ink-950"
        aria-hidden="true"
      >
        IC
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-white">InmoCapital</span>
    </span>
  );
}

export function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-ink-950/96 text-white backdrop-blur-xl">
      <nav className="mx-auto flex h-16 w-full max-w-[1480px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" aria-label="InmoCapital inicio" className="shrink-0">
          <WordmarkFallback />
        </Link>

        <div className="hidden items-center rounded-lg border border-white/10 bg-white/[0.04] p-1 md:flex">
          {navItems.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-white/70 transition hover:bg-white/8 hover:text-white"
            >
              {item.label}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <a
            href="#search"
            className="hidden rounded-md bg-white px-4 py-2 text-sm font-semibold text-ink-950 shadow-sm transition hover:bg-gold-400 focus:outline-none focus:ring-4 focus:ring-gold-500/25 sm:inline-flex"
          >
            Ingresar
          </a>

          <button
            type="button"
            className="grid size-10 place-items-center rounded-md text-white/80 transition hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white/30 sm:hidden"
            aria-label={open ? "Cerrar menu" : "Abrir menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? (
              <svg
                className="size-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg
                className="size-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
                />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {open && (
        <div className="border-t border-white/10 bg-ink-950/98 pb-3 sm:hidden">
          <div className="flex flex-col px-4 pt-1">
            {navItems.map((item) => (
              <a
                key={item.label}
                href={item.href}
                className="rounded-md px-2 py-2.5 text-sm font-medium text-white/80 transition hover:bg-white/8 hover:text-white"
                onClick={() => setOpen(false)}
              >
                {item.label}
              </a>
            ))}
            <div className="mt-2 border-t border-white/8 pt-3">
              <a
                href="#search"
                className="flex w-full items-center justify-center rounded-md border border-white/16 py-2.5 text-sm font-semibold text-white/88 transition hover:bg-white/8"
                onClick={() => setOpen(false)}
              >
                Ingresar
              </a>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
