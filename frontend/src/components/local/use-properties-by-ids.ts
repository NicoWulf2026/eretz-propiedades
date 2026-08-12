"use client";

import { useEffect, useState } from "react";
import type { PropertySummary } from "@/types/property";

type State = { properties: PropertySummary[]; loading: boolean; error: boolean };
type Fetched = { key: string; properties: PropertySummary[]; error: boolean };

// Trae resúmenes frescos para un conjunto de ids (favoritos, comparar) desde el
// endpoint server-side, que aplica el Quality Gate. Los ids inexistentes o no
// visibles simplemente no vuelven, así una lista local nunca muestra datos
// no autorizados ni inventados. El estado de carga se deriva en render (no con
// setState en el efecto) comparando la clave pedida con la ya resuelta.
export function usePropertiesByIds(ids: string[]): State {
  const key = ids.join(",");
  const [fetched, setFetched] = useState<Fetched>({ key: "", properties: [], error: false });

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    fetch(`/api/properties/by-ids?ids=${encodeURIComponent(key)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: { properties?: PropertySummary[] }) => {
        if (!cancelled) setFetched({ key, properties: data.properties ?? [], error: false });
      })
      .catch(() => {
        if (!cancelled) setFetched({ key, properties: [], error: true });
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  if (!key) return { properties: [], loading: false, error: false };
  if (fetched.key !== key) return { properties: [], loading: true, error: false };
  return { properties: fetched.properties, loading: false, error: fetched.error };
}
