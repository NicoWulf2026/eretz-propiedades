"use client";

import { track } from "@/lib/analytics";

export function PublicSearchForm({ compact = false }: { compact?: boolean }) {
  return (
    <form
      action="/propiedades"
      className={`grid gap-3 ${compact ? "md:grid-cols-[1fr_170px_170px_auto]" : "md:grid-cols-[1fr_190px_190px_auto]"}`}
      onSubmit={() => track("search_submitted")}
    >
      <label className="field">
        <span>Título o palabra clave</span>
        <input name="q" type="search" placeholder="Ej. casa con jardín" maxLength={80} />
      </label>
      <label className="field">
        <span>Operación</span>
        <select name="operacion" defaultValue="">
          <option value="">Todas</option>
          <option value="venta">Comprar</option>
          <option value="alquiler">Alquilar</option>
          <option value="temporario">Temporario</option>
          <option value="venta_y_alquiler">Venta y alquiler</option>
          <option value="consultar">Consultar</option>
        </select>
      </label>
      <label className="field">
        <span>Tipo</span>
        <select name="tipo" defaultValue="">
          <option value="">Todos</option>
          <option value="departamento">Departamento</option>
          <option value="casa">Casa</option>
          <option value="terreno">Terreno</option>
          <option value="ph">PH</option>
          <option value="local">Local</option>
          <option value="oficina">Oficina</option>
          <option value="cochera">Cochera</option>
        </select>
      </label>
      <button className="primary-button self-end" type="submit">Buscar</button>
    </form>
  );
}
