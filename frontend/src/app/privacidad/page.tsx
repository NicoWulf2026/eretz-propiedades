import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";

const CONTACT_EMAIL = "eretzpropiedades@gmail.com";

export const metadata: Metadata = {
  title: "Política de privacidad | ERETZ Propiedades",
  description: "Política de privacidad de ERETZ Propiedades.",
  robots: { index: false, follow: false },
};

export default function PrivacidadPage() {
  return (
    <div className="min-h-screen bg-[#f6f8fb]">
      <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
        <Link
          href="/"
          className="text-sm font-semibold text-ink-950/60 transition hover:text-ink-950"
        >
          ← Volver a ERETZ Propiedades
        </Link>

        <h1 className="mt-4 text-2xl font-bold text-ink-950">Política de privacidad</h1>
        <p className="mt-2 text-sm text-ink-950/55">
          Versión mínima para beta. No constituye asesoramiento legal.
        </p>

        <div className="mt-6 space-y-4 text-sm leading-6 text-ink-950/75">
          <p>
            ERETZ Propiedades trata los datos personales de forma responsable y limitada a lo
            necesario para operar la plataforma.
          </p>
          <ul className="list-disc space-y-2 pl-5">
            <li>
              Datos de contacto: solo recibimos los datos que nos enviás voluntariamente por email
              (por ejemplo, al solicitar una corrección o baja de publicación).
            </li>
            <li>
              Datos técnicos de navegación: en el futuro podríamos incorporar métricas mínimas de
              uso del sitio. Si lo hacemos, lo aclararemos en esta política.
            </li>
            <li>No vendemos ni comercializamos datos personales.</li>
            <li>
              La información de las propiedades pertenece a las inmobiliarias y terceros que la
              publican; ERETZ Propiedades solo la recopila y muestra.
            </li>
          </ul>
          <p>
            Para consultas, correcciones o solicitudes de baja, escribí a{" "}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="font-semibold text-ink-950 hover:underline"
            >
              {CONTACT_EMAIL}
            </a>
            .
          </p>
        </div>
      </main>
      <Footer />
    </div>
  );
}
