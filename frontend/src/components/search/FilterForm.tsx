import type { PropertyFilters } from "@/types/property";

export function FilterForm({ filters }: { filters: PropertyFilters }) {
  return (
    <form
      action="/propiedades"
      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="field sm:col-span-2">
          <span>Título o palabra clave</span>
          <input name="q" type="search" defaultValue={filters.q} placeholder="Ej. casa con jardín" />
        </label>
        <label className="field">
          <span>Operación</span>
          <select name="operacion" defaultValue={filters.operation}>
            <option value="">Todas</option>
            <option value="venta">Venta</option>
            <option value="alquiler">Alquiler</option>
            <option value="temporario">Temporario</option>
            <option value="venta_y_alquiler">Venta y alquiler</option>
            <option value="consultar">Consultar</option>
          </select>
        </label>
        <label className="field">
          <span>Tipo</span>
          <select name="tipo" defaultValue={filters.propertyType}>
            <option value="">Todos</option>
            <option value="departamento">Departamento</option>
            <option value="casa">Casa</option>
            <option value="ph">PH</option>
            <option value="terreno">Terreno</option>
            <option value="oficina">Oficina</option>
            <option value="local">Local</option>
            <option value="cochera">Cochera</option>
            <option value="galpon">Galpón</option>
            <option value="campo">Campo</option>
          </select>
        </label>
        <label className="field">
          <span>Provincia</span>
          <input name="provincia" defaultValue={filters.province} placeholder="Ej. Buenos Aires" />
        </label>
        <label className="field">
          <span>Ciudad</span>
          <input name="ciudad" defaultValue={filters.city} placeholder="Ej. Córdoba" />
        </label>
        <label className="field">
          <span>Barrio o localidad</span>
          <input name="barrio" defaultValue={filters.neighborhood} placeholder="Ej. Palermo" />
        </label>
        <label className="field">
          <span>Moneda</span>
          <select name="moneda" defaultValue={filters.currency}>
            <option value="">Cualquiera</option>
            <option value="USD">USD</option>
            <option value="ARS">ARS</option>
            <option value="EUR">EUR</option>
            <option value="UYU">UYU</option>
          </select>
        </label>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-bold text-[#2166a5]">Más filtros</summary>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="field"><span>Precio mínimo</span><input name="precio_min" inputMode="numeric" type="number" min="0" defaultValue={filters.minPrice ?? ""} /></label>
          <label className="field"><span>Precio máximo</span><input name="precio_max" inputMode="numeric" type="number" min="0" defaultValue={filters.maxPrice ?? ""} /></label>
          <label className="field"><span>Ambientes mín.</span><input name="ambientes" type="number" min="1" defaultValue={filters.minRooms ?? ""} /></label>
          <label className="field"><span>Dormitorios mín.</span><input name="dormitorios" type="number" min="1" defaultValue={filters.minBedrooms ?? ""} /></label>
          <label className="field"><span>Baños mín.</span><input name="banos" type="number" min="1" defaultValue={filters.minBathrooms ?? ""} /></label>
          <label className="field"><span>Cocheras mín.</span><input name="cocheras" type="number" min="1" defaultValue={filters.minGarages ?? ""} /></label>
          <label className="field"><span>Superficie total mín.</span><input name="superficie" type="number" min="1" defaultValue={filters.minArea ?? ""} /></label>
          <label className="field">
            <span>Orden</span>
            <select name="orden" defaultValue={filters.sort}>
              <option value="recent">Más recientes</option>
              <option value="price_asc" disabled={!filters.currency}>Menor precio (requiere moneda)</option>
              <option value="price_desc" disabled={!filters.currency}>Mayor precio (requiere moneda)</option>
              <option value="area_desc">Mayor superficie</option>
            </select>
          </label>
          <label className="check"><input name="imagenes" value="1" type="checkbox" defaultChecked={filters.hasImages} /> Solo con imágenes</label>
          <label className="check"><input name="precio" value="1" type="checkbox" defaultChecked={filters.hasPrice} /> Solo con precio</label>
        </div>
      </details>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button className="primary-button" type="submit">Aplicar filtros</button>
        <a href="/propiedades" className="secondary-button">Restablecer</a>
        {!filters.currency && (filters.sort === "price_asc" || filters.sort === "price_desc") ? (
          <p className="text-xs text-amber-800">Elegí una moneda para ordenar precios sin mezclarlas.</p>
        ) : null}
      </div>
    </form>
  );
}
