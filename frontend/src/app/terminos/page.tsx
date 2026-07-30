import type { Metadata } from "next";
import { LegalPage } from "@/components/layout/LegalPage";

export const metadata: Metadata = { title: "Términos y condiciones", robots: { index: false, follow: true } };

export default function Page() {
  return <LegalPage title="Términos y condiciones" updated="Borrador para revisión legal · julio de 2026">
    <h2>Naturaleza del servicio</h2><p>ERETZ Propiedades recopila, organiza y enlaza información inmobiliaria publicada por terceros. No es parte de las operaciones, no reserva inmuebles, no cobra pagos y no representa a quienes publican salvo indicación expresa.</p>
    <h2>Información de los avisos</h2><p>Precios, moneda, disponibilidad, medidas, ubicación, imágenes y características provienen de la publicación original y pueden estar incompletos o cambiar sin aviso. Deben confirmarse con la inmobiliaria, desarrolladora o responsable.</p>
    <h2>Contacto y contratación</h2><p>Las consultas se realizan directamente por los canales públicos del aviso. Toda negociación, visita, reserva o contrato ocurre fuera de ERETZ y es responsabilidad de sus participantes.</p>
    <h2>Disponibilidad</h2><p>Procuramos una experiencia confiable, pero no garantizamos continuidad ininterrumpida ni exactitud absoluta. Los enlaces externos pueden dejar de funcionar.</p>
    <h2>Correcciones y bajas</h2><p>Podés solicitar una revisión desde <a href="/baja-o-correccion">baja o corrección</a> o escribir a <a href="mailto:eretzpropiedades@gmail.com">eretzpropiedades@gmail.com</a>.</p>
  </LegalPage>;
}

