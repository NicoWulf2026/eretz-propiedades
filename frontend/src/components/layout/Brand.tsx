import Link from "next/link";

// Marca ERETZ: monograma navy con acento dorado + wordmark en serif de display.
// `dark` invierte el monograma para fondos oscuros (footer/hero).
export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" prefetch={false} className="brand focus-ring" aria-label="ERETZ Propiedades — ir al inicio">
      <span aria-hidden="true" className={`brand-mark${dark ? " is-dark" : ""}`}>
        E
        <span className="brand-mark-accent" />
      </span>
      <span className={`brand-text${dark ? " is-dark" : ""}`}>
        <span className="brand-word">ERETZ</span>
        <span className="brand-sub">Propiedades</span>
      </span>
    </Link>
  );
}
