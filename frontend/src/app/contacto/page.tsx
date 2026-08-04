import type { Metadata } from "next";
import { LegalPage } from "@/components/layout/LegalPage";

export const metadata: Metadata = { title: "Contacto" };
export default function Page() {
  return <LegalPage title="Contacto" updated="ERETZ Propiedades · Argentina"><h2>Consultas sobre una propiedad</h2><p>Usá los botones de contacto en el detalle del aviso. La consulta irá directamente al responsable o a la publicación original; ERETZ no almacena el mensaje.</p><h2>Consultas sobre ERETZ</h2><p>Escribinos a <a href="mailto:eretzpropiedades@gmail.com">eretzpropiedades@gmail.com</a>. No envíes documentación sensible ni datos de pago.</p><h2>Correcciones o bajas</h2><p>Para identificar correctamente el aviso, seguí el proceso de <a href="/baja-o-correccion">baja o corrección</a>.</p></LegalPage>;
}

