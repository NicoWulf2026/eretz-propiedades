"use client";

import Link from "next/link";
import { useState } from "react";
import { Brand } from "@/components/layout/Brand";

const items = [
  { label: "Comprar", href: "/propiedades?operacion=venta" },
  { label: "Alquilar", href: "/propiedades?operacion=alquiler" },
  { label: "Propiedades", href: "/propiedades" },
  { label: "Cómo funciona", href: "/#como-funciona" },
];

export function Navbar() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-[1000] border-b border-white/10 bg-[#071d35]/95 text-white backdrop-blur">
      <nav className="container flex h-[72px] items-center justify-between" aria-label="Navegación principal">
        <Brand dark />
        <div className="hidden items-center gap-1 lg:flex">
          {items.map((item) => (
            <Link key={item.href} href={item.href} className="rounded-lg px-3 py-2 text-sm font-semibold text-white/75 hover:bg-white/10 hover:text-white">
              {item.label}
            </Link>
          ))}
          <Link href="/contacto" className="nav-contact ml-2 rounded-lg bg-white px-4 py-2.5 text-sm font-bold hover:bg-[#f4e8cc]">
            Contacto
          </Link>
        </div>
        <button
          type="button"
          className="focus-ring grid size-11 place-items-center rounded-lg border border-white/15 lg:hidden"
          aria-label={open ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden="true" className="text-xl">{open ? "×" : "☰"}</span>
        </button>
      </nav>
      {open && (
        <div className="border-t border-white/10 bg-[#071d35] lg:hidden">
          <div className="container flex flex-col py-3">
            {items.map((item) => (
              <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className="rounded-lg px-3 py-3 text-base font-semibold text-white/85 hover:bg-white/10">
                {item.label}
              </Link>
            ))}
            <Link href="/contacto" onClick={() => setOpen(false)} className="nav-contact mt-2 rounded-lg bg-white px-3 py-3 text-center font-bold">Contacto</Link>
          </div>
        </div>
      )}
    </header>
  );
}
