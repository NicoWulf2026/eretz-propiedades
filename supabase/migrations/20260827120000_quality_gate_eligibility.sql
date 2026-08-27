-- ERETZ Propiedades — elegibilidad del Quality Gate, materializada.
--
-- Hoy el gate es un manifiesto precomputado que se descarga entero y se filtra
-- en Node. Por eso el conteo no puede ser un COUNT(*): la base no sabe qué es
-- elegible, así que hay que traerle las 257.073 filas a la aplicación para que
-- decida. De ahí los ~20 s fríos.
--
-- Esto no traduce reglas a SQL —no existen reglas que traducir— sino que pone
-- el RESULTADO del manifiesto al lado de los datos que filtra.
--
-- Tres decisiones que gobiernan el diseño:
--
--   1. Schema propio, fuera de `public`. La Data API expone `public` y nada
--      más (supabase/config.toml), así que un schema aparte mantiene la
--      elegibilidad fuera de la superficie pública por construcción, no por
--      recordarse de revocar algo.
--
--   2. La versión es parte de la clave primaria. Eso permite cargar el
--      manifiesto nuevo AL LADO del vigente y recién después cambiar el
--      puntero: en ningún momento hay una versión a medio cargar sirviendo
--      resultados.
--
--   3. `visible` no se cree: se verifica. La misma invariante que el parser
--      del CSV aplica —que la columna coincida con lo que dicta la
--      clasificación— vive acá como CHECK. Si alguien insertara una fila
--      marcada visible con una clasificación que la excluye, la base la
--      rechaza.

begin;

create schema if not exists eretz_gate;

comment on schema eretz_gate is
  'Elegibilidad del Quality Gate. Privado: fuera de los schemas expuestos por Data API.';

-- Las cinco clasificaciones del manifiesto, y cuáles hacen visible una
-- publicación. Se declara como dominio para que el conjunto viva en un solo
-- lugar y no en cada CHECK.
do $$
begin
  if not exists (select 1 from pg_type t
                 join pg_namespace n on n.oid = t.typnamespace
                 where n.nspname = 'eretz_gate' and t.typname = 'gate_classification') then
    create domain eretz_gate.gate_classification as text
      check (value in ('INVALID', 'REVIEW_REQUIRED', 'SOURCE_UNAVAILABLE',
                       'PUBLICABLE_INCOMPLETE', 'PUBLICABLE_COMPLETE'));
  end if;
end
$$;

create table if not exists eretz_gate.eligibility (
  manifest_version text   not null,
  property_id      bigint not null,
  classification   eretz_gate.gate_classification not null,
  visible          boolean not null,
  primary key (manifest_version, property_id),

  -- La invariante del parser, ahora también en la base.
  constraint visible_coincide_con_clasificacion check (
    visible = (classification in ('PUBLICABLE_COMPLETE', 'PUBLICABLE_INCOMPLETE'))
  )
);

comment on table eretz_gate.eligibility is
  'Una fila por (versión de manifiesto, propiedad). Se carga entera antes de activarse.';

-- Índice para el camino caliente: dada la versión activa, qué es visible.
-- Parcial a propósito: las filas no visibles nunca se consultan por este
-- camino, y son la mayoría.
create index if not exists eligibility_visibles
  on eretz_gate.eligibility (manifest_version, property_id)
  where visible;

-- Metadatos por versión: sirven para verificar que lo cargado es lo esperado
-- ANTES de activarlo.
create table if not exists eretz_gate.manifest (
  manifest_version text primary key,
  checksum_sha256  text   not null check (checksum_sha256 ~ '^[a-f0-9]{64}$'),
  row_count        integer not null check (row_count > 0),
  visible_count    integer not null check (visible_count >= 0),
  imported_at      timestamptz not null default now(),
  activated_at     timestamptz,
  source           text   not null default 'private_blob',
  constraint visibles_no_superan_el_total check (visible_count <= row_count)
);

-- Qué versión está sirviendo. Una sola fila: el CHECK sobre una columna
-- constante lo garantiza sin depender de que nadie inserte de más.
create table if not exists eretz_gate.active_manifest (
  unica            boolean primary key default true check (unica),
  manifest_version text not null references eretz_gate.manifest (manifest_version),
  activated_at     timestamptz not null default now()
);

comment on table eretz_gate.active_manifest is
  'Sin fila, ninguna propiedad es visible. Esa es la orientación correcta: fail-closed.';

-- Vista del camino caliente. Existe para que ninguna consulta tenga que
-- recordar unir contra `active_manifest`: olvidarse de esa unión mostraría
-- todas las versiones a la vez.
create or replace view eretz_gate.visible_property_ids as
  select e.property_id
  from eretz_gate.eligibility e
  join eretz_gate.active_manifest a
    on a.manifest_version = e.manifest_version
  where e.visible;

comment on view eretz_gate.visible_property_ids is
  'Ids visibles bajo la versión activa. Vacía si no hay versión activa.';

-- El rol de sólo lectura de la aplicación necesita leer esto, y nada más.
-- No se le da INSERT: la carga la hace el importador con su propio rol.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'eretz_preview_ro') then
    grant usage on schema eretz_gate to eretz_preview_ro;
    grant select on eretz_gate.eligibility,
                    eretz_gate.manifest,
                    eretz_gate.active_manifest,
                    eretz_gate.visible_property_ids
      to eretz_preview_ro;
  end if;
end
$$;

-- Nadie más. `anon` y `authenticated` no reciben nada: el schema no está
-- expuesto por Data API y tampoco debe estarlo por herencia.
revoke all on schema eretz_gate from public;
revoke all on all tables in schema eretz_gate from public;

commit;

-- Verificación posterior sugerida (sólo lectura):
--   select count(*) from eretz_gate.visible_property_ids;   -- 0 si no hay versión activa
--   select * from eretz_gate.manifest order by imported_at desc limit 5;
