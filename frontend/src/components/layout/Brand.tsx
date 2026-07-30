import Link from "next/link";

export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <Link href="/" aria-label="ERETZ Propiedades, inicio" className="group inline-flex items-center gap-3">
      <span
        aria-hidden="true"
        className={`relative grid size-10 place-items-center rounded-xl border text-sm font-black tracking-tight ${
          dark
            ? "border-white/20 bg-white text-[#0b2748]"
            : "border-[#0b2748]/10 bg-[#0b2748] text-white"
        }`}
      >
        E
        <span className="absolute -bottom-1 size-2 rotate-45 bg-[#d6b66f]" />
      </span>
      <span className={dark ? "text-white" : "text-[#0b2748]"}>
        <span className="block text-lg font-black leading-none tracking-[0.12em]">ERETZ</span>
        <span className="mt-1 block text-[10px] font-semibold uppercase tracking-[0.22em] opacity-70">
          Propiedades
        </span>
      </span>
    </Link>
  );
}

