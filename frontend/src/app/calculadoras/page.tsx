import type { Metadata } from "next";
import Link from "next/link";
import { CALCULADORAS, PENDIENTES } from "@/lib/calculators/catalog";

export const metadata: Metadata = {
  title: "Calculadoras",
  description: "Herramientas para estimar cuota, capacidad de compra, gastos y rentabilidad.",
};

export default function Page() {
  return (
    <main className="container calc-hub">
      <header className="calc-hub-header">
        <p className="eyebrow">Herramientas</p>
        <h1>Calculadoras</h1>
        <p className="calc-hub-lede">
          Cálculos sobre los valores que ingresás. No traemos tasas, cotizaciones ni
          comisiones de referencia: los números los ponés vos, y cada resultado te
          muestra con qué supuestos se hizo.
        </p>
      </header>

      <ul className="calc-hub-grid">
        {CALCULADORAS.map((c) => (
          <li key={c.id}>
            <Link href={`/calculadoras/${c.id}`} prefetch={false} className="calc-hub-card">
              <span className="calc-hub-card-question">{c.pregunta}</span>
              <span className="calc-hub-card-title">{c.titulo}</span>
              <span className="calc-hub-card-summary">{c.resumen}</span>
              {c.requiereSupuestos ? (
                <span className="calc-hub-card-note">Necesita que ingreses una tasa o alícuota</span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>

      {/* Se publican las ausencias en vez de omitirlas: quien busca una
          calculadora de UVA y no la encuentra merece saber que la decisión fue
          deliberada y no un olvido. */}
      <section className="calc-hub-pending">
        <h2>Todavía no están, y por qué</h2>
        <dl>
          {PENDIENTES.map((p) => (
            <div key={p.titulo}>
              <dt>{p.titulo}</dt>
              <dd>{p.motivo}</dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}
