/** Rol escritor de minimo privilegio (P18): lo que puede y lo que NO, ejecutado.
 *
 * PostgreSQL/WASM desechable y en memoria (PGlite). No tiene url de conexion y
 * no puede llegar a Supabase. `production_connections: 0`.
 *
 * No se conforma con `has_table_privilege`: ejecuta cada escritura, permitida
 * o no, con los privilegios del rol (SET ROLE). Quien puede asumir a quien se
 * prueba con pg_has_role: PGlite es mono-usuario y no deja cambiar el usuario
 * de sesion y volver.
 *
 * Escenarios:
 *   A. base "como produccion hoy": el escritor ya existe NOLOGIN con
 *      SELECT, INSERT en raw, y `eretz_preview_ro` es miembro (lo que el
 *      canario viejo necesitaba). Se aplica la migracion dos veces.
 *   B. base limpia: la migracion crea los dos roles; el rollback los borra.
 *   C. fail-closed: un escritor con privilegios de mas aborta la migracion.
 *
 * Uso (PGlite en _scratch, fuera del repo):
 *   cd _scratch/unification/postgres-check && npm install @electric-sql/pglite
 *   node scripts/verify_writer_role.mjs
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(resolve(root, '_scratch/unification/postgres-check/package.json'));
const { PGlite } = require('@electric-sql/pglite');
const sql = async name => readFile(resolve(root, 'migrations', name), 'utf8');
const passed = [];
async function check(name, action) { await action(); passed.push(name); }

const MIGRACION = await sql('eretz_property_writer_role.sql');
const ROLLBACK = await sql('eretz_property_writer_role_rollback.sql');
const SAFE_MERGE = await sql('property_safe_merge_audit.sql');
const RAW_COLS = `(inmobiliaria_id, hash_dedup, datos_extra)`;

async function base({ comoProduccion }) {
  const db = new PGlite();
  await db.exec(`
    CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
    CREATE ROLE eretz_preview_ro LOGIN;
    CREATE SCHEMA internal_scraping;
    CREATE TABLE internal_scraping.propiedades_raw (
      id bigserial PRIMARY KEY, inmobiliaria_id bigint, hash_dedup text, datos_extra jsonb);
    CREATE TABLE internal_scraping.scraping_runs (id bigserial PRIMARY KEY);
    CREATE TABLE public.inmobiliarias_main (id bigint PRIMARY KEY);
    INSERT INTO public.inmobiliarias_main VALUES (7);
    CREATE TABLE public.propiedades (
      id bigserial PRIMARY KEY, inmobiliaria_id integer REFERENCES public.inmobiliarias_main(id), url text,
      url_normalizada text, hash_dedup text NOT NULL UNIQUE, id_externo text, titulo text, descripcion text,
      precio numeric, moneda text, tipo_propiedad text, operacion text,
      ambientes integer, dormitorios integer, banos integer, superficie_total numeric, superficie_cubierta numeric,
      direccion text, barrio text, ciudad text, provincia text, pais text, latitud double precision,
      longitud double precision, imagenes text[], fuente_extraccion text,
      estado text, updated_at timestamptz DEFAULT now());
  `);
  await db.exec(SAFE_MERGE);
  if (comoProduccion) {
    // Lo observado el 27-08 (MASTER_PROGRESS): NOLOGIN, SELECT+INSERT en raw.
    // Mas la membresia que el canario asumia para entrar como eretz_preview_ro.
    await db.exec(`
      CREATE ROLE eretz_direct_property_writer NOLOGIN;
      GRANT USAGE ON SCHEMA internal_scraping TO eretz_direct_property_writer;
      GRANT SELECT, INSERT ON internal_scraping.propiedades_raw TO eretz_direct_property_writer;
      GRANT USAGE ON SEQUENCE internal_scraping.propiedades_raw_id_seq TO eretz_direct_property_writer;
      GRANT eretz_direct_property_writer TO eretz_preview_ro;
    `);
  }
  return db;
}

// Ejecuta `cuerpo` con los privilegios de `rol` (current_user), siempre con
// ROLLBACK. Los privilegios se chequean contra current_user: esto SI prueba lo
// que el rol puede hacer. LIMITACION de PGlite (mono-usuario): no se puede
// cambiar el usuario de SESION y volver, asi que "quien puede asumir a quien"
// se prueba con pg_has_role(..., 'MEMBER'), que es lo que SET ROLE consulta.
async function como(db, rol, cuerpo) {
  await db.exec('BEGIN');
  try {
    await db.exec(`SET LOCAL ROLE ${rol}`);
    return await cuerpo();
  } finally {
    await db.exec('ROLLBACK');
  }
}
const puedeAsumir = async (db, quien, rol) =>
  (await db.query('SELECT pg_has_role($1, $2, \'MEMBER\') AS m', [quien, rol])).rows[0].m;
const denegado = /permission denied|must be member|must be able to SET ROLE/;
const insertRaw = db => db.query(`INSERT INTO internal_scraping.propiedades_raw ${RAW_COLS} VALUES (7,'h','{}') RETURNING id`);
const PAYLOAD = { url: 'https://agencia-siete.test/p/1', url_normalizada: 'agencia-siete.test/p/1',
  titulo: 'Casa', precio: 100, moneda: 'USD', inmobiliaria_id: 7, hash_dedup: 'h-siete',
  fuente_extraccion: 'test', operacion: 'venta', estado: 'activa' };
const insertRpc = db => db.query('SELECT public.insert_property_safe($1::jsonb,$2,$3,$4::jsonb) AS r',
  [JSON.stringify(PAYLOAD), '7', 'p18', JSON.stringify([{ field: 'precio', old_value: null, new_value: 100,
    decision: 'ACCEPTED_IMPROVEMENT', confidence: 1, reason: 'alta' }])]);

// ------------------------------------------------------------------ A
{
  const db = await base({ comoProduccion: true });
  await check('A_antes_la_credencial_del_preview_podia_asumir_el_escritor', async () =>
    assert.equal(await puedeAsumir(db, 'eretz_preview_ro', 'eretz_direct_property_writer'), true));
  await db.exec(MIGRACION);
  await db.exec(MIGRACION);   // idempotente

  await check('A_la_credencial_del_preview_ya_no_puede_asumir_el_escritor', async () => {
    assert.equal(await puedeAsumir(db, 'eretz_preview_ro', 'eretz_direct_property_writer'), false);
    await assert.rejects(() => como(db, 'eretz_preview_ro', () => insertRaw(db)), denegado);
  });
  await check('A_el_cargador_sin_SET_ROLE_no_escribe_nada', async () => {
    await assert.rejects(() => como(db, 'eretz_property_loader', () => insertRaw(db)), denegado);
    await assert.rejects(() => como(db, 'eretz_property_loader', () => insertRpc(db)), denegado);
  });
  await check('A_el_cargador_puede_asumir_el_escritor_y_el_escritor_inserta_en_raw', async () => {
    assert.equal(await puedeAsumir(db, 'eretz_property_loader', 'eretz_direct_property_writer'), true);
    const r = await como(db, 'eretz_direct_property_writer', () => insertRaw(db));
    assert.equal(r.rows.length, 1);
  });
  await check('A_el_escritor_no_modifica_ni_borra_raw', async () => {
    for (const s of ['UPDATE internal_scraping.propiedades_raw SET hash_dedup = hash_dedup',
                     'DELETE FROM internal_scraping.propiedades_raw',
                     'TRUNCATE internal_scraping.propiedades_raw']) {
      await assert.rejects(() => como(db, 'eretz_direct_property_writer', () => db.exec(s)), denegado, s);
    }
  });
  await check('A_el_escritor_no_toca_public_propiedades_de_forma_directa', async () => {
    for (const s of ["INSERT INTO public.propiedades (hash_dedup) VALUES ('x')",
                     'UPDATE public.propiedades SET titulo = titulo',
                     'DELETE FROM public.propiedades',
                     "INSERT INTO internal_scraping.scraping_runs DEFAULT VALUES"]) {
      await assert.rejects(() => como(db, 'eretz_direct_property_writer', () => db.exec(s)), denegado, s);
    }
  });
  await check('A_el_escritor_escribe_produccion_solo_por_el_RPC', async () => {
    const r = await como(db, 'eretz_direct_property_writer', () => insertRpc(db));
    assert.ok(r.rows[0].r.property_id);
  });
  await check('A_la_auditoria_no_se_escribe_a_mano', () =>
    assert.rejects(() => como(db, 'eretz_direct_property_writer', () => db.query(
      "SELECT public.record_property_merge_audit(1,'7','p18','[]'::jsonb)")), denegado));
  await check('A_los_roles_publicos_no_pueden_asumirlo', async () => {
    for (const rol of ['anon', 'authenticated', 'service_role']) {
      assert.equal(await puedeAsumir(db, rol, 'eretz_direct_property_writer'), false, rol);
    }
  });
  await check('A_rollback_vuelve_al_estado_previo_menos_la_membresia_del_preview', async () => {
    await db.exec(ROLLBACK);
    await db.exec(ROLLBACK);  // idempotente
    const roles = (await db.query(`SELECT rolname FROM pg_roles WHERE rolname LIKE 'eretz_%' ORDER BY 1`)).rows.map(r => r.rolname);
    assert.deepEqual(roles, ['eretz_direct_property_writer', 'eretz_preview_ro']);
    const priv = (await db.query(`SELECT
      has_table_privilege('eretz_direct_property_writer','internal_scraping.propiedades_raw','INSERT') AS ins,
      has_function_privilege('eretz_direct_property_writer',
        'public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)','EXECUTE') AS rpc,
      pg_has_role('eretz_preview_ro','eretz_direct_property_writer','MEMBER') AS preview`)).rows[0];
    assert.deepEqual(priv, { ins: true, rpc: false, preview: false });
  });
  await db.close();
}

// ------------------------------------------------------------------ B
{
  const db = await base({ comoProduccion: false });
  await db.exec(MIGRACION);
  await check('B_base_limpia_crea_los_dos_roles_con_sus_atributos', async () => {
    const r = (await db.query(`SELECT rolname, rolcanlogin, rolinherit, rolconnlimit FROM pg_roles
      WHERE rolname IN ('eretz_direct_property_writer','eretz_property_loader') ORDER BY 1`)).rows;
    assert.deepEqual(r, [
      { rolname: 'eretz_direct_property_writer', rolcanlogin: false, rolinherit: false, rolconnlimit: -1 },
      { rolname: 'eretz_property_loader', rolcanlogin: true, rolinherit: false, rolconnlimit: 2 }]);
  });
  await check('B_rollback_borra_lo_que_creo', async () => {
    await db.exec(ROLLBACK);
    const n = (await db.query(`SELECT count(*)::int AS n FROM pg_roles
      WHERE rolname IN ('eretz_direct_property_writer','eretz_property_loader')`)).rows[0].n;
    assert.equal(n, 0);
  });
  await db.close();
}

// ------------------------------------------------------------------ C
{
  const db = await base({ comoProduccion: true });
  await db.exec('GRANT UPDATE ON public.propiedades TO eretz_direct_property_writer');
  await check('C_un_escritor_con_privilegios_de_mas_aborta_sin_cambios', async () => {
    await assert.rejects(() => db.exec(MIGRACION), /escribir fuera de raw|public.propiedades/);
    await db.exec('ROLLBACK').catch(() => {});
    const n = (await db.query(`SELECT count(*)::int AS n FROM pg_roles WHERE rolname = 'eretz_property_loader'`)).rows[0].n;
    assert.equal(n, 0);
    const miembro = (await db.query(`SELECT pg_has_role('eretz_preview_ro','eretz_direct_property_writer','MEMBER') AS m`)).rows[0].m;
    assert.equal(miembro, true, 'la transaccion abortada no deja cambios a medias');
  });
  await db.close();
  const db2 = await base({ comoProduccion: false });
  await db2.exec(`CREATE ROLE eretz_property_loader LOGIN INHERIT`);
  await check('C_un_cargador_preexistente_con_INHERIT_aborta', () =>
    assert.rejects(() => db2.exec(MIGRACION), /atributos inesperados/));
  await db2.close();
}

console.log(JSON.stringify({ passed, total: passed.length, production_connections: 0,
  limitation: 'PostgreSQL/WASM (PGlite) con filas sinteticas; no es Supabase alojado ni su pooler.' }, null, 2));
