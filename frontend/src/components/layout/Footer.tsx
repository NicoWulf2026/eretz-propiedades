import Link from "next/link";

const CONTACT_EMAIL = "eretzpropiedades@gmail.com";

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-ink-950/10 bg-white">
      <div className="mx-auto w-full max-w-[1480px] px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-xl">
            <p className="text-sm font-semibold text-ink-950">ERETZ Propiedades</p>
            <p className="mt-2 text-xs leading-5 text-ink-950/55">
              ERETZ Propiedades recopila y muestra información publicada por inmobiliarias y
              terceros. Los precios, disponibilidad, características e imágenes pueden cambiar sin
              previo aviso. Confirmá siempre la información con la inmobiliaria o anunciante
              correspondiente.
            </p>
            <p className="mt-2 text-xs leading-5 text-ink-950/55">
              ¿Sos inmobiliaria, propietario o usuario y querés corregir, actualizar o solicitar la
              baja de una publicación? Escribinos a{" "}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                className="font-semibold text-ink-950 underline-offset-2 hover:underline"
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </div>

          <nav className="flex flex-col gap-2 text-sm" aria-label="Enlaces legales">
            <Link href="/terminos" className="text-ink-950/70 transition hover:text-ink-950">
              Términos y condiciones
            </Link>
            <Link href="/privacidad" className="text-ink-950/70 transition hover:text-ink-950">
              Política de privacidad
            </Link>
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="text-ink-950/70 transition hover:text-ink-950"
            >
              Contacto
            </a>
          </nav>
        </div>

        <div className="mt-6 border-t border-ink-950/8 pt-4">
          <p className="text-[11px] text-ink-950/45">
            © {year} ERETZ Propiedades · Beta. Información de terceros sujeta a cambios.
          </p>
        </div>
      </div>
    </footer>
  );
}
