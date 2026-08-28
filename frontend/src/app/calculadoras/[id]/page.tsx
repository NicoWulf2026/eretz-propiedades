import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CALCULADORAS, calculadoraPorId, type CalculadoraId } from "@/lib/calculators/catalog";
import { MortgageCalculator } from "@/components/calculators/MortgageCalculator";
import { OperationCostsCalculator } from "@/components/calculators/OperationCostsCalculator";
import { PricePerM2Calculator } from "@/components/calculators/PricePerM2Calculator";
import { YieldCalculator } from "@/components/calculators/YieldCalculator";

// Una ruta por calculadora, generada desde el catálogo. Si alguien agrega una
// entrada al catálogo sin su componente, el `switch` de abajo no compila: es
// preferible a una ruta que exista y no muestre nada.

export function generateStaticParams() {
  return CALCULADORAS.map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const calculadora = calculadoraPorId(id);
  if (!calculadora) return { title: "Calculadora" };
  return { title: calculadora.titulo, description: calculadora.resumen };
}

function Cuerpo({ id }: { id: CalculadoraId }) {
  switch (id) {
    // Cuota y capacidad son la misma pantalla en los dos sentidos: una es la
    // inversa exacta de la otra, así que comparten formulario.
    case "cuota-hipotecaria":
    case "capacidad-de-compra":
      return <MortgageCalculator />;
    case "precio-por-m2":
      return <PricePerM2Calculator />;
    case "gastos-de-operacion":
      return <OperationCostsCalculator />;
    case "rentabilidad":
      return <YieldCalculator />;
  }
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const calculadora = calculadoraPorId(id);
  if (!calculadora) notFound();

  return (
    <main className="container calc-page">
      <nav aria-label="Miga de pan" className="calc-breadcrumb">
        <Link href="/calculadoras" prefetch={false}>Calculadoras</Link>
        <span aria-hidden="true"> / </span>
        <span>{calculadora.titulo}</span>
      </nav>

      <header className="calc-page-header">
        <h1>{calculadora.titulo}</h1>
        <p className="calc-page-lede">{calculadora.resumen}</p>
      </header>

      <Cuerpo id={calculadora.id} />
    </main>
  );
}
