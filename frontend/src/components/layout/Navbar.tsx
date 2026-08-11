"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Brand } from "@/components/layout/Brand";

const items = [
  { label: "Explorar", href: "/" },
  { label: "Inmobiliarias", href: "/inmobiliarias" },
  { label: "Agentes", href: "/agentes" },
];

// Accesos personales (sin cuenta): viven en su propio grupo para no competir
// con la navegación principal.
const personal = [
  { label: "Favoritos", href: "/favoritos" },
  { label: "Colecciones", href: "/colecciones" },
  { label: "Comparar", href: "/comparar" },
];

export function Navbar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); buttonRef.current?.focus(); } };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <header className="site-header">
      <nav className="site-header-inner container" aria-label="Navegación principal">
        <Brand />
        <div className="site-nav">
          {items.map((item) => (
            <Link key={item.href} href={item.href} prefetch={false}
              className={`nav-link${isActive(item.href) ? " is-active" : ""}`}
              aria-current={isActive(item.href) ? "page" : undefined}>
              {item.label}
            </Link>
          ))}
          <span className="nav-divider" aria-hidden="true" />
          {personal.map((item) => (
            <Link key={item.href} href={item.href} prefetch={false}
              className={`nav-link is-personal${isActive(item.href) ? " is-active" : ""}`}
              aria-current={isActive(item.href) ? "page" : undefined}>
              {item.label}
            </Link>
          ))}
        </div>
        <button
          type="button"
          ref={buttonRef}
          className="nav-toggle focus-ring"
          aria-label={open ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={open}
          aria-controls="mobile-navigation"
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden="true">{open ? "×" : "☰"}</span>
        </button>
      </nav>
      {open && (
        <div id="mobile-navigation" className="nav-mobile">
          <div className="container nav-mobile-inner">
            {[...items, ...personal].map((item) => (
              <Link key={item.href} href={item.href} prefetch={false} onClick={() => setOpen(false)}
                className={`nav-link${isActive(item.href) ? " is-active" : ""}`}>
                {item.label}
              </Link>
            ))}
            <Link href="/privacidad" prefetch={false} onClick={() => setOpen(false)} className="nav-link">Privacidad</Link>
          </div>
        </div>
      )}
    </header>
  );
}
