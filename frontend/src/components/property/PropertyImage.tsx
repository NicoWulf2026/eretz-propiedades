"use client";

import { useState } from "react";

export function PropertyImage({
  src,
  alt,
  fallbackLabel,
  priority = false,
}: {
  src: string | null;
  alt: string;
  fallbackLabel?: string;
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className="property-fallback" role="img" aria-label="Imagen no disponible">
        <svg viewBox="0 0 32 32" aria-hidden="true">
          <path d="M5 14.5 16 5l11 9.5V27H5V14.5Z" />
          <path d="M12 27v-8h8v8M9 13h14" />
        </svg>
        {fallbackLabel ? <strong>{fallbackLabel}</strong> : null}
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
