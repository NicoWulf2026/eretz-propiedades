import type { Metadata } from "next";
import { LegalPage } from "@/components/layout/LegalPage";

export const metadata: Metadata = { title: "Baja o corrección", robots: { index: false, follow: true } };
export default function Page() {
  const subject = encodeURIComponent("Solicitud de baja o corrección de publicación");
  return <LegalPage title="Baja o corrección" updated="Canal público de revisión"><h2>Cómo solicitarla</h2><p>Enviá un email a <a href={`mailto:eretzpropiedades@gmail.com?subject=${subject}`}>eretzpropiedades@gmail.com</a> con la URL pública de ERETZ o de la publicación original, el cambio solicitado y una forma razonable de verificar tu relación con el aviso.</p><h2>Privacidad</h2><p>No incluyas DNI, datos bancarios, contraseñas ni documentación innecesaria. Podremos pedir información adicional mínima para evitar bajas fraudulentas.</p><h2>Alcance</h2><p>Revisaremos la presentación en ERETZ. Si el contenido sigue publicado en el sitio de origen, la corrección definitiva también debe gestionarse con ese responsable.</p></LegalPage>;
}

