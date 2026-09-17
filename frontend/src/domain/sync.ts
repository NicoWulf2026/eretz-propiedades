// Fusión de "Mi ERETZ" local con una cuenta en la nube.
//
// Hoy favoritos, ocultas, comparar, historial, búsquedas y colecciones viven en
// `localStorage` (ver `lib/local-store.ts`) y funcionan sin cuenta. Cuando
// existan cuentas habrá que fusionar lo que la persona ya tiene en el navegador
// con lo que tenga la cuenta, sin perder nada de ninguno de los dos lados.
//
// Módulo puro: no toca `localStorage` ni la red. Produce un PLAN que alguien
// más ejecuta. Ver "La regla del borrado" más abajo para entender por qué está
// partido así y no es una complicación gratuita.
//
// ---------------------------------------------------------------------------
// EL PROBLEMA DE FONDO: LOS FAVORITOS NO TIENEN FECHA
// ---------------------------------------------------------------------------
//
// `getFavorites()` devuelve `string[]`. Sólo ids, sin cuándo. Y eso hace
// literalmente indecidible el caso más importante de una fusión:
//
//   La propiedad 123 está en la nube y NO está en el navegador.
//   ¿Es que nunca la marqué en este dispositivo, o que la desmarqué acá?
//
// En el primer caso hay que bajarla. En el segundo, bajarla RESUCITA algo que
// la persona borró a propósito. Sin fecha de borrado, no hay forma de saber
// cuál de los dos es.
//
// Ante esa indecidibilidad se elige unión —conservar— por asimetría de daño:
// un favorito que reaparece es visible y se vuelve a quitar en un click; un
// favorito que desaparece no se nota hasta que alguien lo busca y ya no está.
//
// La unión NO es la respuesta correcta, es la menos mala mientras no haya
// fechas. La respuesta correcta son las lápidas (`Tombstone`): registrar el
// borrado con su fecha. El modelo ya las soporta; falta que `local-store.ts`
// las emita. Hasta entonces, `resurrecciones` deja por escrito exactamente qué
// entró por unión, para que el costo de la decisión sea medible y no invisible.

/** Un borrado registrado. Es lo que permite que un borrado se propague. */
export type Tombstone = { id: string; deletedAt: number };

/** Un conjunto de ids sincronizable. `tombstones` puede faltar (estado actual). */
export type ConjuntoSync = {
  ids: readonly string[];
  tombstones?: readonly Tombstone[];
};

/** Elemento con marca de tiempo propia: historial, búsquedas, colecciones. */
export type ElementoFechado = { id: string; at: number };

export type PlanDeConjunto = {
  /** Lo que queda tras fusionar. */
  resultado: string[];
  /** Lo que hay que mandar a la nube porque sólo estaba local. */
  subir: string[];
  /** Lo que hay que traer porque sólo estaba en la nube. */
  bajar: string[];
  /**
   * Ids que entraron por unión sin poder verificar que no fueran un borrado.
   * Es el costo, explícito, de no tener lápidas.
   */
  resurrecciones: string[];
  /** Borrados que sí pudieron propagarse porque había lápida. */
  borrados: string[];
};

const ultimaLapida = (ts: readonly Tombstone[] | undefined, id: string): number | null => {
  let max: number | null = null;
  for (const t of ts ?? []) {
    if (t.id === id && (max === null || t.deletedAt > max)) max = t.deletedAt;
  }
  return max;
};

/**
 * Fusiona dos conjuntos de ids.
 *
 * Con lápidas de un lado, un borrado gana sobre una presencia del otro salvo
 * que la presencia sea posterior. Sin lápidas, unión.
 *
 * No se pasa "ahora" ni se lee el reloj: la función es determinista y los
 * mismos datos dan siempre el mismo plan, que es lo que la hace testeable.
 */
export function fusionarConjunto(local: ConjuntoSync, nube: ConjuntoSync): PlanDeConjunto {
  const idsLocal = new Set(local.ids);
  const idsNube = new Set(nube.ids);
  const todos = new Set([...idsLocal, ...idsNube]);

  const plan: PlanDeConjunto = {
    resultado: [],
    subir: [],
    bajar: [],
    resurrecciones: [],
    borrados: [],
  };

  for (const id of todos) {
    const enLocal = idsLocal.has(id);
    const enNube = idsNube.has(id);

    // Presente en ambos: nada que hacer, salvo que alguno lo haya borrado
    // después. Un borrado sólo gana si es posterior a la última vez que el otro
    // lado lo tuvo, y sin fechas de alta no podemos afirmar eso: por eso
    // estando en ambos se conserva.
    if (enLocal && enNube) {
      plan.resultado.push(id);
      continue;
    }

    const lapidaLocal = ultimaLapida(local.tombstones, id);
    const lapidaNube = ultimaLapida(nube.tombstones, id);

    if (enNube && lapidaLocal !== null) {
      // Se borró acá y sigue en la nube: el borrado se propaga.
      plan.borrados.push(id);
      continue;
    }
    if (enLocal && lapidaNube !== null) {
      plan.borrados.push(id);
      continue;
    }

    plan.resultado.push(id);
    if (enLocal) {
      plan.subir.push(id);
    } else {
      plan.bajar.push(id);
      // Estaba sólo en la nube y este dispositivo no tiene lápidas: no podemos
      // descartar que se haya borrado acá antes de que existiera el registro.
      if (local.tombstones === undefined) plan.resurrecciones.push(id);
    }
  }

  // Orden estable para que el plan sea comparable entre corridas.
  for (const k of ["resultado", "subir", "bajar", "resurrecciones", "borrados"] as const) {
    plan[k].sort();
  }
  return plan;
}

// --- elementos fechados ----------------------------------------------------

export type PlanDeFechados<T extends ElementoFechado> = {
  resultado: T[];
  subir: T[];
  bajar: T[];
  /** Los que existían de los dos lados con fechas distintas. */
  conflictos: Array<{ id: string; ganador: "LOCAL" | "NUBE"; local: number; nube: number }>;
};

/**
 * Fusiona elementos que sí traen fecha: gana el más reciente.
 *
 * Acá sí hay con qué decidir, así que no hay unión ciega. Los empates los gana
 * la nube por una razón práctica: es el lado compartido entre dispositivos, y
 * que dos navegadores converjan al mismo valor importa más que cuál de los dos
 * gana un empate exacto.
 */
export function fusionarFechados<T extends ElementoFechado>(
  local: readonly T[],
  nube: readonly T[],
): PlanDeFechados<T> {
  const porIdLocal = new Map(local.map((x) => [x.id, x]));
  const porIdNube = new Map(nube.map((x) => [x.id, x]));
  const plan: PlanDeFechados<T> = { resultado: [], subir: [], bajar: [], conflictos: [] };

  for (const id of new Set([...porIdLocal.keys(), ...porIdNube.keys()])) {
    const l = porIdLocal.get(id);
    const n = porIdNube.get(id);

    if (l && !n) {
      plan.resultado.push(l);
      plan.subir.push(l);
    } else if (!l && n) {
      plan.resultado.push(n);
      plan.bajar.push(n);
    } else if (l && n) {
      const ganaLocal = l.at > n.at;
      plan.resultado.push(ganaLocal ? l : n);
      if (l.at !== n.at) {
        plan.conflictos.push({ id, ganador: ganaLocal ? "LOCAL" : "NUBE", local: l.at, nube: n.at });
        if (ganaLocal) plan.subir.push(l);
        else plan.bajar.push(n);
      }
    }
  }

  plan.resultado.sort((a, b) => b.at - a.at || a.id.localeCompare(b.id));
  return plan;
}

// --- la regla del borrado --------------------------------------------------

/**
 * Estado de una sincronización. Existe para hacer imposible el accidente que
 * el encargo prohíbe: limpiar lo local antes de confirmar que la nube guardó.
 *
 * Si `fusionar` borrara lo local de una, una caída de red entre "subí" y
 * "guardé" perdería datos de la persona sin dejar rastro. Partirlo en plan y
 * confirmación convierte esa ventana en un estado explícito y reintentable.
 */
export type EstadoSync = "PLANIFICADO" | "SUBIENDO" | "CONFIRMADO" | "FALLIDO";

/**
 * ¿Se puede limpiar la copia local?
 *
 * Sólo tras confirmación. Es una única función para que exista un solo lugar
 * donde se responda esa pregunta en todo el código.
 */
export function puedeLimpiarLocal(estado: EstadoSync): boolean {
  return estado === "CONFIRMADO";
}

/**
 * ¿El plan cambia algo?
 *
 * Sirve para no escribir ni pedir nada cuando ambos lados ya coinciden, que es
 * el caso más frecuente después de la primera sincronización.
 */
export function planVacio(plan: PlanDeConjunto): boolean {
  return plan.subir.length === 0 && plan.bajar.length === 0 && plan.borrados.length === 0;
}
