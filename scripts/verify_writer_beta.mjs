/** Lo que la beta exige del escritor, demostrado en PostgreSQL/WASM desechable.
 *
 * Complementa `verify_writer_equivalence.mjs` (identidad, geografia,
 * auditoria) con los casos del criterio de beta del 2026-10-02: insert,
 * update, preservacion de lo que no se manda, NULL, cero, campos legados,
 * idempotencia y rollback de la migracion. Sin url de conexion: no puede
 * llegar a Supabase. `production_connections: 0`.
 *
 * Cada `check` afirma la semantica REAL de `property_safe_merge_audit.sql`.
 * Donde la semantica no es la que uno supondria, queda en `hallazgos` en vez
 * de esconderse en un test que pasa.
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
async function check(name, action) { await action(); passed.push(name); }
const sql = async name => readFile(resolve(root, 'migrations', name), 'utf8');

const URL = 'https://agencia-siete.test/p/1';
const HASH = 'hash-de-la-siete';
const BASE = {
  url: URL, url_normalizada: 'agencia-siete.test/p/1', hash_dedup: HASH,
  inmobiliaria_id: 7, fuente_extraccion: 'test', titulo: 'Casa', precio: 100,
  moneda: 'USD', operacion: 'venta', tipo_propiedad: 'casa', ambientes: 3,
  dormitorios: 2, banos: 1, superficie_total: 80, direccion: 'Calle 1',
  barrio: 'Centro', ciudad: 'Rosario', provincia: 'Santa Fe', pais: 'Argentina',
  latitud: -32.9, longitud: -60.6, imagenes: ['https://i.test/1.jpg'],
};
let auditoria = 0;
const evento = (field, old_value, new_value) => [{field, old_value, new_value,
  decision: 'ACCEPTED_SOURCE_CHANGE', confidence: 1, reason: `beta-${++auditoria}`}];
const fila = async id => (await db.query('SELECT * FROM public.propiedades WHERE id=$1', [id])).rows[0];
const auditorias = async () => Number((await db.query('SELECT count(*) AS n FROM public.property_merge_audit')).rows[0].n);

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

  const insertar = (payload, audit = evento('alta', null, 'nueva')) => db.query(
    'SELECT public.insert_property_safe($1::jsonb,$2,$3,$4::jsonb) AS result',
    [JSON.stringify(payload), '7', 'beta', JSON.stringify(audit)]);
  const merge = (id, patch, audit) => db.query(
    'SELECT public.apply_property_safe_merge($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb) AS result',
    [id, 7, URL, HASH, 'test', JSON.stringify(patch), '7', 'beta', JSON.stringify(audit)]);

  let id;
  await check('insert_con_identidad_completa_y_auditoria', async () => {
    const r = (await insertar(BASE)).rows[0].result;
    assert.equal(r.status, 'inserted');
    id = r.property_id;
    const f = await fila(id);
    assert.equal(f.inmobiliaria_id, 7); assert.equal(f.hash_dedup, HASH);
    assert.equal(f.estado, 'activa');
    assert.equal(await auditorias(), 1);
  });

  await check('MUERDE_insert_sin_identidad_completa_se_rechaza', async () => {
    const {hash_dedup, ...sinHash} = BASE;
    await assert.rejects(() => insertar({...sinHash, url: 'https://x.test/2', url_normalizada: 'x.test/2'}),
      /complete identity/);
  });

  await check('update_cambia_solo_lo_que_viene_en_el_patch', async () => {
    const antes = await fila(id);
    const r = (await merge(id, {precio: 120}, evento('precio', 100, 120))).rows[0].result;
    assert.equal(r.status, 'updated'); assert.equal(r.changed_fields, 1);
    const despues = await fila(id);
    assert.equal(Number(despues.precio), 120);
    for (const k of ['titulo', 'moneda', 'dormitorios', 'ciudad', 'provincia', 'latitud', 'imagenes'])
      assert.deepEqual(despues[k], antes[k], `${k} no se preserva`);
  });

  await check('MUERDE_un_null_no_borra_un_dato_existente', async () => {
    const antes = await fila(id);
    await assert.rejects(() => merge(id, {dormitorios: null}, evento('dormitorios', 2, null)),
      /cannot contain JSON null/);
    assert.equal((await fila(id)).dormitorios, antes.dormitorios);
  });

  await check('cero_es_un_valor_y_no_un_vacio', async () => {
    // Monoambiente: 0 dormitorios es un dato, no la ausencia del dato.
    await merge(id, {dormitorios: 0}, evento('dormitorios', 2, 0));
    assert.equal((await fila(id)).dormitorios, 0);
    // Precio 0: el escritor lo conserva como 0, por DISENO documentado
    // (ERETZ_EQUIVALENCIA_DE_ESCRITORES.md, "NULL y cero"): es un canal fiel.
    // La defensa contra precios simbolicos esta antes y despues: el pipeline
    // descarta precio <= 0 y la compuerta P2 exige 0 precios simbolicos.
    await merge(id, {precio: 0}, evento('precio', 120, 0));
    assert.equal(Number((await fila(id)).precio), 0);
    hallazgos.push({caso: 'precio 0', escritor: 'lo conserva (canal fiel, por diseno)',
      defensas: ['pipeline: precio <= 0 -> None', 'compuerta P2: 0 precios simbolicos'],
      decision_abierta: 'agregar rechazo en el RPC contradice insert_null_zero_and_audit; decide el usuario'});
    await merge(id, {precio: 120}, evento('precio', 0, 120));
  });

  await check('MUERDE_un_campo_legado_no_se_puede_escribir_y_se_preserva', async () => {
    await db.query("UPDATE public.propiedades SET id_externo='LEG-1' WHERE id=$1", [id]);
    await assert.rejects(() => merge(id, {id_externo: 'otro'}, evento('id_externo', 'LEG-1', 'otro')),
      /forbidden merge keys/);
    await merge(id, {titulo: 'Casa amplia'}, evento('titulo', 'Casa', 'Casa amplia'));
    assert.equal((await fila(id)).id_externo, 'LEG-1');
  });

  await check('idempotencia_el_mismo_evento_no_se_aplica_dos_veces', async () => {
    const audit = evento('banos', 1, 2);
    await merge(id, {banos: 2}, audit);
    const n = await auditorias();
    // Reaplicar el MISMO evento: la auditoria lo deduplica, y un cambio sin
    // auditoria nueva se rechaza entero (fail closed). Ni fila ni auditoria cambian.
    await assert.rejects(() => merge(id, {banos: 2}, audit), /without audit evidence/);
    assert.equal(await auditorias(), n);
    assert.equal((await fila(id)).banos, 2);
    hallazgos.push({caso: 'reintento del mismo merge', escritor: 'lo rechaza (fail closed)',
      consecuencia: 'el cliente debe mandar solo el diff real; un patch vacio devuelve unchanged'});
    const r = (await merge(id, {}, [])).rows[0].result;
    assert.equal(r.status, 'unchanged');
  });

  await check('rollback_de_la_migracion_corta_el_acceso_y_conserva_la_evidencia', async () => {
    // El rollback es NO destructivo a proposito: revoca EXECUTE y deja las
    // funciones y la auditoria como evidencia inmutable. Lo que se verifica es
    // eso, no que desaparezcan.
    const antes = await fila(id);
    const n = await auditorias();
    const puede = async () => (await db.query(`SELECT
      has_function_privilege('service_role',
        'public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)', 'EXECUTE') AS merge,
      has_function_privilege('service_role',
        'public.insert_property_safe(jsonb,text,text,jsonb)', 'EXECUTE') AS ins`)).rows[0];
    assert.deepEqual(await puede(), {merge: true, ins: true});
    await db.exec(await sql('property_safe_merge_audit_rollback.sql'));
    assert.deepEqual(await puede(), {merge: false, ins: false});
    assert.deepEqual(await fila(id), antes);
    assert.equal(await auditorias(), n);
    const comentario = (await db.query(
      "SELECT obj_description('public.property_merge_audit'::regclass) AS c")).rows[0].c;
    assert.match(comentario, /DISABLED/);
    // Y se vuelve a habilitar re-aplicando la migracion.
    await db.exec(await sql('property_safe_merge_audit.sql'));
    assert.deepEqual(await puede(), {merge: true, ins: true});
  });

  console.log(JSON.stringify({passed, total: passed.length, hallazgos,
    production_connections: 0,
    limitation: 'Filas sinteticas; no es Supabase alojado ni PostgREST real.'}, null, 2));
} catch (error) {
  console.error(JSON.stringify({passed, failed_after: passed.at(-1) || null,
    error: String(error && error.message || error), production_connections: 0}, null, 2));
  process.exitCode = 1;
} finally {
  await db.close();
}
