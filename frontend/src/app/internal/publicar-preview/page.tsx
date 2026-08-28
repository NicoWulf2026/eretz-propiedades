import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PublicationWizard } from "@/components/publication/PublicationWizard";
import { wizardHabilitado } from "@/lib/publication/flag";

// Ruta interna de QA para el wizard de publicación.
//
// Con la flag apagada devuelve 404, que es lo mismo que vería alguien que
// adivina la URL. No hay enlace hacia acá desde ninguna navegación, ni CTA en
// la home, ni en los perfiles.
//
// `noindex, nofollow` explícito además del `robots.ts` global: si algún día
// Preview deja de bloquear todo, esta ruta tiene que seguir bloqueada por su
// cuenta.

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Publicar (vista previa interna)",
  robots: { index: false, follow: false, nocache: true },
};

export default function Page() {
  if (!wizardHabilitado()) notFound();

  return (
    <main className="container pub-page">
      <header className="pub-page-header">
        <p className="eyebrow">Vista previa interna</p>
        <h1>Publicar una propiedad</h1>
        <p className="pub-page-lede">
          Este flujo todavía no guarda nada. Llega hasta la revisión final y se detiene ahí,
          porque falta conectar el guardado. Está acá para poder probarlo, no para usarlo.
        </p>
      </header>

      <PublicationWizard />
    </main>
  );
}
