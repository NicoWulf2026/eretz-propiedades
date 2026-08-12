import Link from "next/link";

// Marca ERETZ (Identity V1): monograma en verde de marca + wordmark tipográfico
// en Inter. No existe un logotipo oficial todavía —`public/brand/` sigue
// pendiente en la documentación—, así que el wordmark se resuelve con la
// tipografía del sistema en vez de inventar un símbolo.
// `dark` invierte el monograma para fondos oscuros (footer/hero).
// Sin aria-label: el nombre accesible sale del texto visible ("ERETZ
// Propiedades"); un aria-label distinto disparaba label-content-name-mismatch.
export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" prefetch={false} className="brand focus-ring">
      <span aria-hidden="true" className={`brand-mark${dark ? " is-dark" : ""}`}>
        E
      </span>
      <span className={`brand-text${dark ? " is-dark" : ""}`}>
        <span className="brand-word">ERETZ</span>
        <span className="brand-sub">Propiedades</span>
      </span>
    </Link>
  );
}
