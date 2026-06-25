import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/layout/Footer";

const CONTACT_EMAIL = "eretzpropiedades@gmail.com";

export const metadata: Metadata = {
  title: "Términos y condiciones | ERETZ Propiedades",
  description: "Términos y condiciones de uso de ERETZ Propiedades.",
  robots: { index: false, follow: false },
};

export default function TerminosPage() {
  return (
    <div className="min-h-screen bg-[#f6f8fb]">
      <main className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
        <Link
          href="/"
          className="text-sm font-semibold text-ink-950/60 transition hover:text-ink-950"
        >
          ← Volver a ERETZ Propiedades
        </Link>

        <h1 className="mt-4 text-2xl font-bold text-ink-950">Términos y condiciones</h1>
        <p className="mt-2 text-sm text-ink-950/55">
          Versión mínima para beta. No constituye asesoramiento legal.
        </p>

        <div className="mt-6 space-y-4 text-sm leading-6 text-ink-950/75">
          <p>
            ERETZ Propiedades es una plataforma que recopila y muestra información de propiedades
            publicada por inmobiliarias y terceros.
          </p>
          <p>
            Los precios, disponibilidad, características, imágenes y condiciones de las publicaciones
            pueden cambiar sin previo aviso.
          </p>
          <p>
            La información debe ser confirmada siempre con la inmobiliaria o anunciante
            correspondiente antes de tomar cualquier decisión.
          </p>
          <p>
            ERETZ Propiedades no garantiza la disponibilidad, exactitud absoluta ni vigencia
            permanente de cada publicación.
          </p>
          <p>
            Si una inmobiliaria, propietario o usuario desea corregir, actualizar o solicitar la
            baja de una publicación, puede escribir a{" "}
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
