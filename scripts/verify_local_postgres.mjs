/** Execute repository SQL against disposable, in-memory PostgreSQL/WASM.
 * Install the optional test runtime under _scratch/unification/postgres-check.
 * This script has no connection URL and cannot connect to Supabase.
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
async function check(name, action) {
  await action();
  passed.push(name);
}
const sql = async name => readFile(resolve(root, 'migrations', name), 'utf8');
try {
  await db.exec(`
    CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE SCHEMA internal_scraping;
    CREATE TABLE public.propiedades (
      id bigserial PRIMARY KEY, inmobiliaria_id integer, url text,
      url_normalizada text, hash_dedup text UNIQUE, titulo text, descripcion text,
      precio numeric, moneda text, tipo_propiedad text, operacion text,
      ambientes integer, dormitorios integer, banos integer, superficie_total numeric,
      direccion text, barrio text, ciudad text, latitud double precision,
      longitud double precision, imagenes text[], fuente_extraccion text,
      estado text, updated_at timestamptz DEFAULT now()
    );
  `);
  await check('internal_schema_applies_twice', async () => {
    const migration = await sql('phase3_internal_scraping_schema.sql');
    await db.exec(migration);
    await db.exec(migration);
  });
  await check('safe_merge_migration_applies_twice', async () => {
    const migration = await sql('property_safe_merge_audit.sql');
    await db.exec(migration);
    await db.exec(migration);
  });
  await check('staging_recovers_counts_only_from_matching_raw_identity', async () => {
    await db.exec(`
      INSERT INTO internal_scraping.propiedades_raw(id,inmobiliaria_id,hash_dedup,datos_extra)
      VALUES (1,7,'a','{"ambientes":0,"banos":null}'), (2,8,'b','{"ambientes":99}');
      INSERT INTO internal_scraping.propiedades_staging(id,raw_id,inmobiliaria_id,hash_dedup)
      VALUES (1,1,7,'a'), (2,2,7,'b'), (3,null,7,'c');
      SET search_path TO internal_scraping, public;
    `);
    const source = await readFile(resolve(root, 'scripts/publish_to_supabase.py'), 'utf8');
    const query = source.match(/STAGING_SELECT_SQL = """([\s\S]*?)"""/)[1].replace('%s', '$1');
    const rows = (await db.query(query, [[1,2,3]])).rows.sort((a,b) => a.id-b.id);
    assert.equal(rows.length, 3);
    assert.equal(rows[0].raw_extra.ambientes, 0);
    assert.equal(rows[1].raw_extra, null);
    assert.equal(rows[2].raw_extra, null);
    await db.exec('SET search_path TO public');
  });
  const payload = {
    inmobiliaria_id: 7, url: 'https://official.test/propiedad/123',
    url_normalizada: 'official.test/propiedad/123', hash_dedup: 'local-fixture-123',
    titulo: 'Casa real de fixture', precio: 0, moneda: 'USD', ambientes: 0,
    dormitorios: null, banos: 1, superficie_total: null, operacion: 'desconocida',
    tipo_propiedad: 'casa', imagenes: [], fuente_extraccion: 'test', estado: 'activa',
  };
  const audit = [{ field: 'precio', old_value: null, new_value: 0,
    decision: 'ACCEPTED_INSERT', confidence: 1, reason: 'local fixture' }];
  let id;
  await check('insert_null_zero_and_audit', async () => {
    const result = await db.query('SELECT public.insert_property_safe($1::jsonb,$2,$3,$4::jsonb) AS result',
      [JSON.stringify(payload), '7', 'local-insert', JSON.stringify(audit)]);
    id = result.rows[0].result.property_id;
    const row = (await db.query('SELECT * FROM public.propiedades WHERE id=$1', [id])).rows[0];
    assert.equal(Number(row.precio), 0);
    assert.equal(row.ambientes, 0);
    assert.equal(row.dormitorios, null);
    assert.equal(Number((await db.query('SELECT count(*) AS n FROM public.property_merge_audit')).rows[0].n), 1);
  });
  const merge = (patch, entries, source = '7', run = 'local-update') => db.query(
    'SELECT public.apply_property_safe_merge($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9::jsonb) AS result',
    [id, 7, payload.url, payload.hash_dedup, 'test', JSON.stringify(patch), source, run, JSON.stringify(entries)]);
  const updateAudit = [{field: 'precio', old_value: 0, new_value: 100,
    decision: 'ACCEPTED_SOURCE_CHANGE', confidence: 1, reason: 'local source update'}];
  await check('cross_agency_update_rejected', async () => {
    await assert.rejects(() => merge({precio: 100}, updateAudit, '8'));
  });
  await check('null_patch_rejected', async () => {
    await assert.rejects(() => merge({precio: null}, updateAudit));
  });
  await check('mutation_and_audit_roll_back_together', async () => {
    await db.exec('BEGIN');
    await merge({precio: 100}, updateAudit);
    assert.equal(Number((await db.query('SELECT precio FROM public.propiedades WHERE id=$1', [id])).rows[0].precio), 100);
    await db.exec('ROLLBACK');
    assert.equal(Number((await db.query('SELECT precio FROM public.propiedades WHERE id=$1', [id])).rows[0].precio), 0);
    assert.equal(Number((await db.query('SELECT count(*) AS n FROM public.property_merge_audit')).rows[0].n), 1);
  });
  await check('invalid_audit_rolls_back_update', async () => {
    await assert.rejects(() => merge({precio: 100}, [{...updateAudit[0], confidence: 5}]));
    assert.equal(Number((await db.query('SELECT precio FROM public.propiedades WHERE id=$1', [id])).rows[0].precio), 0);
  });
  await check('public_roles_cannot_write_or_read_audit', async () => {
    await db.exec('SET ROLE anon');
    await assert.rejects(() => db.query('SELECT * FROM public.property_merge_audit'));
    await assert.rejects(() => merge({precio: 100}, updateAudit));
    await db.exec('RESET ROLE');
  });
  await check('rollback_migration_revokes_access_preserves_evidence', async () => {
    await db.exec(await sql('property_safe_merge_audit_rollback.sql'));
    await db.exec('SET ROLE service_role');
    await assert.rejects(() => merge({precio: 100}, updateAudit));
    await db.exec('RESET ROLE');
    assert.equal(Number((await db.query('SELECT count(*) AS n FROM public.propiedades')).rows[0].n), 1);
    assert.equal(Number((await db.query('SELECT count(*) AS n FROM public.property_merge_audit')).rows[0].n), 1);
  });
  console.log(JSON.stringify({engine: 'PGlite', storage: 'memory', passed,
    production_connections: 0, limitation: 'Synthetic rows; not hosted Supabase/PostgREST or concurrent production load.'}, null, 2));
} finally {
  await db.close();
}
