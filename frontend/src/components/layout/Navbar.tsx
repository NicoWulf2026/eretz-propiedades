"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Brand } from "@/components/layout/Brand";

const items = [
  { label: "Explorar", href: "/" },
  { label: "Comprar", href: "/?operacion=venta" },
  { label: "Alquilar", href: "/?operacion=alquiler" },
  { label: "Contacto", href: "/contacto" },
];

export function Navbar() {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); buttonRef.current?.focus(); } };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);
  return (
    <header className="sticky top-0 z-[1500] border-b border-white/10 bg-[#06192f]/97 text-white backdrop-blur">
      <nav className="container flex h-16 items-center justify-between" aria-label="Navegación principal">
        <Brand dark />
        <div className="hidden items-center gap-1 lg:flex">
          {items.map((item) => (
            <Link key={item.href} href={item.href} prefetch={false} className="rounded-lg px-3 py-2 text-sm font-semibold text-white/75 hover:bg-white/10 hover:text-white">
              {item.label}
            </Link>
          ))}
          <Link href="/terminos" prefetch={false} className="rounded-lg px-3 py-2 text-sm font-semibold text-white/75 hover:bg-white/10 hover:text-white">
            Términos
          </Link>
          <Link href="/privacidad" prefetch={false} className="nav-contact ml-1 rounded-lg bg-white px-4 py-2.5 text-sm font-bold hover:bg-[#f4e8cc]">
            Privacidad
          </Link>
        </div>
        <button
          type="button"
          ref={buttonRef}
          className="focus-ring grid size-11 place-items-center rounded-lg border border-white/15 lg:hidden"
          aria-label={open ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={open}
          aria-controls="mobile-navigation"
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden="true" className="text-xl">{open ? "×" : "☰"}</span>
        </button>
      </nav>
      {open && (
        <div id="mobile-navigation" className="border-t border-white/10 bg-[#06192f] lg:hidden">
          <div className="container flex flex-col py-3">
            {items.map((item) => (
              <Link key={item.href} href={item.href} prefetch={false} onClick={() => setOpen(false)} className="rounded-lg px-3 py-3 text-base font-semibold text-white/85 hover:bg-white/10">
                {item.label}
              </Link>
            ))}
            <Link href="/terminos" prefetch={false} onClick={() => setOpen(false)} className="rounded-lg px-3 py-3 font-semibold text-white/85">Términos</Link>
            <Link href="/privacidad" prefetch={false} onClick={() => setOpen(false)} className="nav-contact mt-2 rounded-lg bg-white px-3 py-3 text-center font-bold">Privacidad</Link>
          </div>
        </div>
      )}
    </header>
  );
}
