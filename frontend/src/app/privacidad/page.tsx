import type { Metadata } from "next";
import { LegalPage } from "@/components/layout/LegalPage";

export const metadata: Metadata = { title: "Política de privacidad", robots: { index: false, follow: true } };

export default function Page() {
  return <LegalPage title="Política de privacidad" updated="Borrador para revisión legal · julio de 2026">
    <h2>Alcance</h2><p>ERETZ Propiedades es un agregador de avisos de terceros. No exige registro público, no procesa pagos y no almacena consultas sobre propiedades.</p>
    <h2>Datos que podemos recibir</h2><p>Si escribís a nuestro correo para contacto, corrección o baja, recibimos la información que incluís voluntariamente. La usamos solo para responder y gestionar el pedido.</p>
    <h2>Navegación y analítica</h2><p>La beta no configura un proveedor externo de analítica ni cookies publicitarias. Existe una capa técnica deshabilitada que no incluye nombre, teléfono, email, mensajes ni otros datos sensibles. Si esto cambia, actualizaremos esta política y los avisos correspondientes.</p>
    <h2>Enlaces de terceros</h2><p>WhatsApp, llamadas, email y publicaciones originales abren servicios externos sujetos a sus propias políticas. ERETZ no recibe el contenido de esas comunicaciones.</p>
    <h2>Consultas</h2><p>Para ejercer derechos o realizar una consulta, escribí a <a href="mailto:eretzpropiedades@gmail.com">eretzpropiedades@gmail.com</a>.</p>
  </LegalPage>;
}

