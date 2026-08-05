import Link from "next/link";
import { Brand } from "@/components/layout/Brand";

const email = "eretzpropiedades@gmail.com";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-white">
      <div className="container grid gap-10 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <Brand />
          <p className="mt-5 max-w-md text-sm leading-6 text-slate-600">
            Exploramos y ordenamos avisos inmobiliarios de toda Argentina. ERETZ no cobra por alterar
            el orden orgánico: el contacto y la operación se realizan con quien publicó cada propiedad.
          </p>
        </div>
        <nav aria-label="Explorar" className="flex flex-col gap-2 text-sm">
          <p className="mb-2 font-bold text-[#0b2748]">Explorar</p>
          <Link href="/propiedades" prefetch={false}>Todas las propiedades</Link>
          <Link href="/propiedades?operacion=venta" prefetch={false}>Propiedades en venta</Link>
          <Link href="/propiedades?operacion=alquiler" prefetch={false}>Propiedades en alquiler</Link>
          <Link href="/contacto" prefetch={false}>Contacto</Link>
        </nav>
        <nav aria-label="Información legal" className="flex flex-col gap-2 text-sm">
          <p className="mb-2 font-bold text-[#0b2748]">Información</p>
          <Link href="/terminos" prefetch={false}>Términos y condiciones</Link>
          <Link href="/privacidad" prefetch={false}>Privacidad</Link>
          <Link href="/baja-o-correccion" prefetch={false}>Baja o corrección</Link>
          <a href={`mailto:${email}`}>{email}</a>
        </nav>
      </div>
      <div className="border-t border-slate-100">
        <div className="container py-5 text-xs leading-5 text-slate-500">
          © {new Date().getFullYear()} ERETZ Propiedades · Preview privado. Información de terceros sujeta a cambios. Sin aprobación legal declarada.
        </div>
      </div>
    </footer>
  );
}
