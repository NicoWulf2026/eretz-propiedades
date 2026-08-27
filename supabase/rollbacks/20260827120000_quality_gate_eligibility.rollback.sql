-- Rollback de 20260827120000_quality_gate_eligibility.sql.
--
-- Qué se revierte: el schema `eretz_gate` completo, con sus tablas, la vista y
-- los grants a `eretz_preview_ro`.
--
-- Qué se preserva: absolutamente todo lo demás. Esta migración no toca
-- `public`, no modifica ninguna publicación y no altera permisos previos, así
-- que el rollback tampoco.
--
-- Orden: `drop schema ... cascade` se lleva vista, tablas, dominio, índices y
-- grants juntos. Se usa cascade a propósito y no una lista de drops: una lista
-- que quede desactualizada deja objetos huérfanos, y acá el schema entero es
-- de esta migración y de ninguna otra.
--
-- QUÉ IMPLICA REVERTIR, y conviene saberlo antes:
--
--   Si la aplicación ya consulta `eretz_gate.visible_property_ids`, revertir
--   deja esas consultas fallando. El orden correcto es al revés que el de
--   aplicación: primero se vuelve la aplicación a filtrar en Node, y recién
--   después se revierte el schema. Al revés, queda el código nuevo apuntando a
--   algo que ya no existe.
--
--   No se pierde ningún dato propio: la elegibilidad se reconstruye
--   íntegramente desde el manifiesto, que es la fuente. Esta tabla es una
--   copia, no un original.

begin;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'eretz_preview_ro') then
    revoke all on all tables in schema eretz_gate from eretz_preview_ro;
    revoke all on schema eretz_gate from eretz_preview_ro;
  end if;
exception
  when invalid_schema_name then
    null;  -- ya no existe: nada que revocar
end
$$;

drop schema if exists eretz_gate cascade;

do $verificacion$
begin
  if exists (select 1 from pg_namespace where nspname = 'eretz_gate') then
    raise exception 'El rollback no eliminó el schema eretz_gate';
  end if;
end
$verificacion$;

commit;
