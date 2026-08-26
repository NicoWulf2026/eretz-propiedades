"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Brand } from "@/components/layout/Brand";

type NavItem = { label: string; href: string };
type OpenMenu = "professionals" | "personal" | "more" | null;

const professionalItems: NavItem[] = [
  { label: "Inmobiliarias", href: "/inmobiliarias" },
  { label: "Agentes", href: "/agentes" },
];

const personalItems: NavItem[] = [
  { label: "Abrir Mi ERETZ", href: "/mi-eretz" },
  { label: "Guardadas", href: "/mi-eretz?seccion=guardadas" },
  { label: "Comparar", href: "/mi-eretz?seccion=comparar" },
];

const menuItems: NavItem[] = [
  { label: "Contacto", href: "/contacto" },
  { label: "Términos", href: "/terminos" },
  { label: "Privacidad", href: "/privacidad" },
  { label: "Baja o corrección", href: "/baja-o-correccion" },
];

function routeIsActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/" || pathname.startsWith("/propiedad");
  return pathname.startsWith(href);
}

function NavDropdown({ id, items, pathname, onNavigate }: { id: string; items: NavItem[]; pathname: string; onNavigate: () => void }) {
  return (
    <div id={id} className="nav-dropdown">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          prefetch={false}
          className={routeIsActive(pathname, item.href) ? "is-active" : undefined}
          aria-current={routeIsActive(pathname, item.href) ? "page" : undefined}
          onClick={onNavigate}
        >
          {item.label}
        </Link>
      ))}
    </div>
  );
}

export function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openMenu, setOpenMenu] = useState<OpenMenu>(null);
  const pathname = usePathname();
  const headerRef = useRef<HTMLElement>(null);
  const mobileButtonRef = useRef<HTMLButtonElement>(null);
  const professionalsRef = useRef<HTMLButtonElement>(null);
  const personalRef = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!mobileOpen && !openMenu) return;
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (mobileOpen) {
        setMobileOpen(false);
        mobileButtonRef.current?.focus();
        return;
      }
      const trigger = openMenu === "professionals" ? professionalsRef.current
        : openMenu === "personal" ? personalRef.current : moreRef.current;
      setOpenMenu(null);
      trigger?.focus();
    };
    const closeOutside = (event: PointerEvent) => {
      if (!headerRef.current?.contains(event.target as Node)) setOpenMenu(null);
    };
    window.addEventListener("keydown", close);
    window.addEventListener("pointerdown", closeOutside);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", closeOutside);
    };
  }, [mobileOpen, openMenu]);

  const isActive = (href: string) => routeIsActive(pathname, href);
  const professionalsActive = professionalItems.some((item) => isActive(item.href));
  const personalActive = personalItems.some((item) => isActive(item.href));
  const toggleMenu = (menu: Exclude<OpenMenu, null>) => {
    setOpenMenu((current) => current === menu ? null : menu);
  };

  return (
    <header ref={headerRef} className="site-header">
      <nav className="site-header-inner container" aria-label="Navegación principal">
        <div className="site-header-left">
          <Brand dark />
          <div className="site-nav site-nav-primary">
            <Link href="/" prefetch={false} className={`nav-link${isActive("/") ? " is-active" : ""}`} aria-current={isActive("/") ? "page" : undefined}>
              Explorar
            </Link>
            <div className="nav-menu">
              <button ref={professionalsRef} type="button" className={`nav-link nav-menu-trigger${professionalsActive ? " is-active" : ""}`} aria-expanded={openMenu === "professionals"} aria-controls="nav-professionals" onClick={() => toggleMenu("professionals")}>
                Profesionales <span aria-hidden="true">⌄</span>
              </button>
              {openMenu === "professionals" ? <NavDropdown id="nav-professionals" items={professionalItems} pathname={pathname} onNavigate={() => setOpenMenu(null)} /> : null}
            </div>
          </div>
        </div>

        <div className="site-nav site-nav-utility">
          <div className="nav-menu">
            <button ref={personalRef} type="button" className={`nav-link nav-menu-trigger${personalActive ? " is-active" : ""}`} aria-expanded={openMenu === "personal"} aria-controls="nav-personal" onClick={() => toggleMenu("personal")}>
              Mi ERETZ <span aria-hidden="true">⌄</span>
            </button>
            {openMenu === "personal" ? <NavDropdown id="nav-personal" items={personalItems} pathname={pathname} onNavigate={() => setOpenMenu(null)} /> : null}
          </div>
          <div className="nav-menu">
            <button ref={moreRef} type="button" className="nav-link nav-menu-trigger" aria-expanded={openMenu === "more"} aria-controls="nav-more" onClick={() => toggleMenu("more")}>
              Menú <span aria-hidden="true">⌄</span>
            </button>
            {openMenu === "more" ? <NavDropdown id="nav-more" items={menuItems} pathname={pathname} onNavigate={() => setOpenMenu(null)} /> : null}
          </div>
        </div>

        <button
          type="button"
          ref={mobileButtonRef}
          className="nav-toggle focus-ring"
          aria-label={mobileOpen ? "Cerrar menú" : "Abrir menú"}
          aria-expanded={mobileOpen}
          aria-controls="mobile-navigation"
          onClick={() => setMobileOpen((value) => !value)}
        >
          <span aria-hidden="true">{mobileOpen ? "×" : "☰"}</span>
        </button>
      </nav>

      {mobileOpen ? (
        <div id="mobile-navigation" className="nav-mobile">
          <div className="container nav-mobile-inner">
            <Link href="/" prefetch={false} onClick={() => setMobileOpen(false)} className={`nav-link${isActive("/") ? " is-active" : ""}`}>Explorar</Link>
            <p className="nav-mobile-group">Profesionales</p>
            {professionalItems.map((item) => <Link key={item.href} href={item.href} prefetch={false} onClick={() => setMobileOpen(false)} className={`nav-link${isActive(item.href) ? " is-active" : ""}`}>{item.label}</Link>)}
            <p className="nav-mobile-group">Mi ERETZ</p>
            {personalItems.map((item) => <Link key={item.href} href={item.href} prefetch={false} onClick={() => setMobileOpen(false)} className={`nav-link${isActive(item.href) ? " is-active" : ""}`}>{item.label}</Link>)}
            <p className="nav-mobile-group">Más</p>
            {menuItems.map((item) => <Link key={item.href} href={item.href} prefetch={false} onClick={() => setMobileOpen(false)} className={`nav-link${isActive(item.href) ? " is-active" : ""}`}>{item.label}</Link>)}
          </div>
        </div>
      ) : null}
    </header>
  );
}
