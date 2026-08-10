"use client";

import { useEffect } from "react";
import { addRecentView, markVisited } from "@/lib/local-store";

// Registra la ficha visitada en "vistas recientes" y en "visitadas" (localStorage).
// Sin efecto en el servidor ni impacto en el render; sólo guarda señal local.
export function RecentViewTracker({ id, title, price }: { id: string; title: string; price: string | null }) {
  useEffect(() => {
    addRecentView({ id, title, price });
    markVisited(id);
  }, [id, title, price]);
  return null;
}
