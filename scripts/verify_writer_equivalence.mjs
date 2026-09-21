/** Que puede escribir cada camino: el RPC seguro contra el PATCH por REST.
 *
 * PostgreSQL/WASM desechable y en memoria. No tiene url de conexion y no puede
 * llegar a Supabase. `production_connections: 0`.
 *
 * Por que existe
 * --------------
 * Codex dejo abierto "writer equivalence: el REST aun se usa; no retirarlo
 * antes de equivalencia real". La pregunta concreta es que puede tocar cada
 * camino, y la respuesta esta en el codigo:
 *
 *   RPC  `apply_property_safe_merge`  LISTA BLANCA de 17 columnas, rechaza el
 *        resto, verifica identidad -url, hash_dedup, fuente_extraccion,
 *        inmobiliaria_id- ANTES de tocar nada, y escribe auditoria en la misma
 *        transaccion.
 *
 *   REST `batch_save_only_changed`    LISTA NEGRA de TRES campos:
 *
 *            {k: v for k, v in payload.items()
 *             if k not in ("latitud", "longitud", "url")}
 *
 *        Todo lo demas pasa. Y `to_payload()` incluye `inmobiliaria_id`,
 *        `hash_dedup`, `fuente_extraccion` y `estado`.
 *
 * O sea que el PATCH por REST puede reasignar una propiedad a otra
 * inmobiliaria y reescribir su hash de deduplicacion, sin verificar contra que
 * fila esta escribiendo y sin dejar rastro. El RPC no puede.
 *
 * Este script lo demuestra en vez de afirmarlo: corre contra el RPC las mismas
 * escrituras que el REST permitiria, y comprueba que las rechaza.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(resolve(root, '_scratch/unification/postgres-check/package.json'));
const { PGlite } = require('@electric-sql/pglite');
const db = new PGlite();
const passed = [];
const hallazgos = [];
let currentCheck;
async function check(name, action) {
  currentCheck = name;
  await action();
  passed.push(name);
}
const sql = async name => readFile(resolve(root, 'migrations', name), 'utf8');

// Lo que `to_payload()` manda, tal cual. No es una muestra: es el payload.
const PAYLOAD_REAL = {
  url: 'https://agencia-siete.test/p/1', titulo: 'Casa', precio: 100,
  moneda: 'USD', direccion: 'Calle 1', barrio: 'Centro',
  tipo_propiedad: 'casa', descripcion: 'x', dormitorios: 2, banos: 1,
  ambientes: 3, superficie_total: 80, imagenes: ['https://i.test/1.jpg'],
  ciudad: 'Rosario', operacion: 'venta', latitud: -32.9, longitud: -60.6,
  fuente_extraccion: 'test', estado: 'activa',
  inmobiliaria_id: 7, hash_dedup: 'hash-de-la-siete',
};
// HALLAZGO, y por eso esta aparte: `to_payload()` NO produce
// `url_normalizada`, y `insert_property_safe` la EXIGE. Los dos caminos ni
// siquiera aceptan el mismo payload. Aca se agrega para poder comparar el
// resto; en el codigo real habria que producirla.
const PAYLOAD_RPC = {...PAYLOAD_REAL,
  url_normalizada: 'agencia-siete.test/p/1'};
// Lo que el PATCH por REST manda: el payload menos tres campos.
const PATCH_REST = Object.fromEntries(Object.entries(PAYLOAD_REAL)
  .filter(([k]) => !['latitud', 'longitud', 'url'].includes(k)));

try {
  await db.exec(`
    CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE SCHEMA internal_scraping;
    CREATE TABLE public.inmobiliarias_main (id bigint PRIMARY KEY);
    INSERT INTO public.inmobiliarias_main VALUES (7), (8);
    CREATE TABLE public.propiedades (
      id bigserial PRIMARY KEY, inmobiliaria_id integer REFERENCES public.inmobiliarias_main(id), url text,
      url_normalizada text, hash_dedup text NOT NULL UNIQUE, id_externo text, titulo text, descripcion text,
      precio numeric, moneda text, tipo_propiedad text, operacion text,
      ambientes integer, dormitorios integer, banos integer, superficie_total numeric, superficie_cubierta numeric,
      direccion text, barrio text, ciudad text, provincia text, pais text, latitud double precision,
      longitud double precision, imagenes text[], fuente_extraccion text,
      estado text, updated_at timestamptz DEFAULT now(),
      CHECK (operacion IS NULL OR operacion IN
        ('venta','alquiler','alquiler_temporario','consultar','venta_y_alquiler')),
      CHECK (moneda IS NULL OR moneda IN ('ARS','USD','EUR','UYU')),
      CHECK (estado IS NULL OR estado IN ('activa','inactiva','pausada','vendida','alquilada'))
    );
  `);
  await db.exec(await sql('property_safe_merge_audit.sql'));

  const insertado = await db.query(
    'SELECT public.insert_property_safe($1::jsonb,$2,$3,$4::jsonb) AS result',
    [JSON.stringify(PAYLOAD_RPC), '7', 'equivalencia',
     JSON.stringify([{field: 'precio', old_value: null, new_value: 100,
       decision: 'ACCEPTED_IMPROVEMENT', confidence: 1, reason: 'alta'}])]);
  const id = insertado.rows[0].result.property_id;

  const merge = (patch, source = '7') => db.query(
    'SELECT public.apply_property_safe_merge($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb) AS result',
    [id, 7, PAYLOAD_REAL.url, PAYLOAD_REAL.hash_dedup, 'test',
     JSON.stringify(patch), source, 'equivalencia',
     JSON.stringify([{field: 'precio', old_value: 100, new_value: 101,
       decision: 'ACCEPTED_SOURCE_CHANGE', confidence: 1, reason: 'cambio'}])]);

  await check('el_patch_entero_del_REST_es_rechazado_por_el_RPC', async () => {
    // El REST manda estas 17 claves. El RPC acepta solo las suyas.
    await assert.rejects(() => merge(PATCH_REST), /forbidden merge keys/);
    hallazgos.push({
      camino: 'REST batch_save_only_changed',
      permite: Object.keys(PATCH_REST).filter(k => ![
        'titulo','descripcion','precio','moneda','tipo_propiedad','operacion',
        'ambientes','dormitorios','banos','superficie_total',
        'superficie_cubierta','direccion','barrio','ciudad','latitud',
        'longitud','imagenes'].includes(k)),
      rpc: 'los rechaza',
    });
  });

  await check('MUERDE_el_RPC_no_deja_reasignar_la_inmobiliaria', async () => {
    // El REST si lo dejaria: `inmobiliaria_id` viaja en el payload.
    await assert.rejects(() => merge({inmobiliaria_id: 8}), /forbidden merge keys/);
  });

  await check('MUERDE_el_RPC_no_deja_reescribir_el_hash_de_dedup', async () => {
    await assert.rejects(() => merge({hash_dedup: 'otro'}), /forbidden merge keys/);
  });

  await check('MUERDE_el_RPC_no_deja_reescribir_la_fuente_ni_el_estado', async () => {
    await assert.rejects(() => merge({fuente_extraccion: 'otra'}), /forbidden merge keys/);
    await assert.rejects(() => merge({estado: 'inactiva'}), /forbidden merge keys/);
  });

  await check('el_RPC_exige_que_la_fila_siga_siendo_la_misma', async () => {
    // El REST matchea por `url=eq.` y no compara nada mas: si la fila cambio
    // entre la lectura y la escritura, la pisa igual.
    await assert.rejects(() => db.query(
      'SELECT public.apply_property_safe_merge($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb)',
      [id, 7, 'https://otra.test/p/1', PAYLOAD_REAL.hash_dedup, 'test',
       JSON.stringify({precio: 200}), '7', 'equivalencia',
       JSON.stringify([{field: 'precio', old_value: 100, new_value: 200,
         decision: 'ACCEPTED_SOURCE_CHANGE', confidence: 1, reason: 'x'}])]),
      /property identity changed before merge/);
  });

  await check('MUERDE_la_ciudad_no_se_puede_mover_sola', async () => {
    // Era el hueco abierto del informe de equivalencia: `ciudad` se
    // actualizaba y `provincia` no, asi que una fila podia quedar con la
    // ciudad de una provincia y la provincia de otra.
    //
    // La decision se tomo con datos y no a ojo: `ciudad` no cambio ni una vez
    // en 22.963 propiedades comparadas entre dos corridas, y la coherencia
    // ciudad/provincia contra GeoRef es del 98,9 % con UNA fila incoherente
    // en 8.221. O sea que el hueco era una capacidad, no un dano observado.
    //
    // Por eso no se saco `ciudad` del UPDATE -eso cerraria el camino por el
    // que la geografia MEJORA- sino que se acoplaron.
    await assert.rejects(() => merge({ciudad: 'Cordoba Capital'}),
                         /must move together/);
    await assert.rejects(() => merge({provincia: 'Cordoba'}),
                         /must move together/);
  });

  await check('MUERDE_el_pais_no_puede_moverse_sin_provincia', async () => {
    // Un pais sin provincia no ubica nada: seria otra vez media geografia
    // moviendose.
    await assert.rejects(() => merge({pais: 'Uruguay'}),
                         /pais cannot move without provincia/);
  });

  await check('la_geografia_se_mueve_entera_y_queda_coherente', async () => {
    const antes = (await db.query(
      'SELECT ciudad, provincia FROM public.propiedades WHERE id=$1', [id])).rows[0];
    await merge({ciudad: 'Cordoba Capital', provincia: 'Cordoba'});
    const despues = (await db.query(
      'SELECT ciudad, provincia FROM public.propiedades WHERE id=$1', [id])).rows[0];
    assert.equal(despues.ciudad, 'Cordoba Capital');
    assert.equal(despues.provincia, 'Cordoba');
    assert.notEqual(antes.provincia, despues.provincia);
  });

  await check('toda_actualizacion_del_RPC_deja_auditoria', async () => {
    const n = Number((await db.query(
      'SELECT count(*) AS n FROM public.property_merge_audit')).rows[0].n);
    assert.ok(n >= 2, `esperaba auditoria acumulada, hay ${n}`);
  });

  await check('MUERDE_una_actualizacion_sin_auditoria_no_se_aplica', async () => {
    // El REST no escribe ninguna auditoria, nunca.
    await assert.rejects(() => db.query(
      'SELECT public.apply_property_safe_merge($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb)',
      [id, 7, PAYLOAD_REAL.url, PAYLOAD_REAL.hash_dedup, 'test',
       JSON.stringify({precio: 300}), '7', 'equivalencia',
       JSON.stringify([])]));
  });

  console.log(JSON.stringify({engine: 'PGlite', storage: 'memory', passed,
    hallazgos, production_connections: 0,
    limitation: 'Filas sinteticas; no es Supabase alojado ni PostgREST real.'},
    null, 2));
} catch (error) {
  console.error(JSON.stringify({check: currentCheck, status: 'FAIL',
    sqlstate: error.code ?? null, error_type: error.constructor.name,
    message: String(error.message ?? '').slice(0, 300)}));
  process.exitCode = 1;
} finally {
  await db.close();
}
