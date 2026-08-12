"use client";

import { useState } from "react";

export function PropertyImage({ src, alt, priority = false }: { src: string | null; alt: string; priority?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className="property-fallback" role="img" aria-label="Imagen no disponible">
        <span aria-hidden="true">⌂</span>
        <p>Imagen no disponible</p>
      </div>
    );
  }
  return (
    // Domains are heterogeneous third-party sources; the stable container prevents CLS.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      className="h-full w-full object-cover"
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : "auto"}
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
