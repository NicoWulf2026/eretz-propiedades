// Sub-tiempos dentro de una request.
//
// `withObservability` ya registra `durationMs`, el total. Eso alcanza para
// saber que una request tardó 20 segundos y no alcanza para saber en qué: si
// fue la base, el filtrado del Quality Gate en Node, o la serialización.
//
// Sin infraestructura nueva: son marcas en memoria que terminan en la misma
// línea de log que ya se escribe. No hay proveedor, ni agregación, ni endpoint.
//
// ---------------------------------------------------------------------------
// TRES PROPIEDADES QUE NO SE NEGOCIAN
// ---------------------------------------------------------------------------
//
// 1. NUNCA LANZA. Un cronómetro que rompe una request para medirla es peor que
//    no medir. Todos los caminos de error terminan en un valor razonable.
//
// 2. TOPE DE MARCAS. Un bucle que abre una marca por fila crearía 257.073
//    entradas y una línea de log inmensa. A partir del tope se descartan y se
//    registra cuántas se perdieron, que es en sí una señal de mal uso.
//
// 3. NOMBRES, NO VALORES. Una marca se llama `db_query`, nunca
//    `db_query_rosario_250000`. Es la misma regla del logger: el nombre del
//    parámetro sí, su valor no.

/** Cuántas marcas distintas se aceptan por request. */
export const MAXIMO_DE_MARCAS = 24;

/** Nombres admitidos: minúsculas, números y guion bajo. */
const NOMBRE_VALIDO = /^[a-z][a-z0-9_]{0,39}$/;

export type Timings = Record<string, number>;

export type ResumenDeTiempos = {
  /** Milisegundos acumulados por marca, redondeados. */
  timings: Timings;
  /** Cuántas marcas se descartaron por exceder el tope o por nombre inválido. */
  descartadas: number;
};

/**
 * Acumula duraciones por nombre.
 *
 * Acumula en vez de reemplazar: si una request hace ocho consultas, lo que
 * interesa es el total en base, no la última. Para distinguirlas hay que
 * nombrarlas distinto.
 */
export class Cronometro {
  private readonly acumulado = new Map<string, number>();
  private descartadas = 0;

  /** Registra una duración ya medida. */
  registrar(nombre: string, ms: number): void {
    if (!NOMBRE_VALIDO.test(nombre) || !Number.isFinite(ms) || ms < 0) {
      this.descartadas += 1;
      return;
    }
    if (!this.acumulado.has(nombre) && this.acumulado.size >= MAXIMO_DE_MARCAS) {
      this.descartadas += 1;
      return;
    }
    this.acumulado.set(nombre, (this.acumulado.get(nombre) ?? 0) + ms);
  }

  /**
   * Mide una operación asíncrona.
   *
   * Registra el tiempo también cuando falla: una consulta que tarda cinco
   * segundos y después revienta es exactamente la que hay que ver, y medir
   * sólo los éxitos la haría invisible.
   */
  async medir<T>(nombre: string, fn: () => Promise<T>): Promise<T> {
    const inicio = Date.now();
    try {
      return await fn();
    } finally {
      this.registrar(nombre, Date.now() - inicio);
    }
  }

  /** Versión síncrona, con la misma garantía ante excepciones. */
  medirSync<T>(nombre: string, fn: () => T): T {
    const inicio = Date.now();
    try {
      return fn();
    } finally {
      this.registrar(nombre, Date.now() - inicio);
    }
  }

  /** Lo acumulado, listo para adjuntar a la línea de log. */
  resumen(): ResumenDeTiempos {
    const timings: Timings = {};
    for (const nombre of [...this.acumulado.keys()].sort()) {
      timings[`${nombre}_ms`] = Math.round(this.acumulado.get(nombre) as number);
    }
    return { timings, descartadas: this.descartadas };
  }

  /** ¿Hay algo que registrar? Evita ensuciar el log con un objeto vacío. */
  tieneDatos(): boolean {
    return this.acumulado.size > 0 || this.descartadas > 0;
  }
}
