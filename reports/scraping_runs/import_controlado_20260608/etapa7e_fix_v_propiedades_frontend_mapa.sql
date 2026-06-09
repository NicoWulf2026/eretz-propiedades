-- ETAPA 7E - Fix v_propiedades_frontend_mapa agency source
-- Fecha: 2026-06-09
--
-- Definicion anterior resumida:
--   public.v_propiedades_frontend_mapa resolvia los datos visibles de inmobiliaria con:
--   LEFT JOIN inmobiliarias_scraping i ON i.id = p.inmobiliaria_id
--
-- Cambio unico permitido:
--   LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
--
-- No cambia columnas, orden, filtros ni logica de imagen_principal_real/tiene_imagen_real.

create or replace view public.v_propiedades_frontend_mapa as
SELECT p.id,
    p.inmobiliaria_id,
    p.url,
    p.titulo,
    p.descripcion,
    p.precio,
    p.moneda,
    p.precio_usd,
    p.precio_ars,
    p.expensas,
    p.expensas_moneda,
    p.tipo_propiedad,
    p.operacion,
    p.ambientes,
    p.dormitorios,
    p.banos,
    p.toilettes,
    p.cocheras,
    p.antiguedad,
    p.piso,
    p.superficie_total,
    p.superficie_cubierta,
    p.superficie_terreno,
    p.direccion,
    p.barrio,
    p.ciudad AS ciudad_original,
    p.provincia AS provincia_original,
    plr.ciudad_final,
    plr.provincia_final,
    p.pais,
    p.latitud,
    p.longitud,
    p.imagenes,
    p.video_url,
    p.plano_url,
    p.amenities,
    p.agente_nombre,
    p.agente_telefono,
    p.fuente_extraccion,
    p.cms_origen,
    p.fecha_publicacion,
    p.estado,
    p.created_at,
    p.updated_at,
    p.apto_credito,
    i.nombre AS inmobiliaria_nombre,
    i.web AS inmobiliaria_web,
    i.telefono_principal AS inmobiliaria_telefono,
    i.email_principal AS inmobiliaria_email,
        CASE
            WHEN p.imagenes IS NOT NULL AND array_length(p.imagenes, 1) > 0 AND p.imagenes[1] !~~ '%static.tokkobroker.com/tfw/img/prop-icons%'::text AND p.imagenes[1] !~~* '%unsplash.com%'::text AND p.imagenes[1] !~~* '%placeholder%'::text AND p.imagenes[1] !~~* '%no-photo%'::text AND p.imagenes[1] !~~* '%sin-imagen%'::text AND p.imagenes[1] !~~* '%360%'::text AND p.imagenes[1] !~~* '%tour%'::text AND p.imagenes[1] !~~* '%virtual%'::text THEN p.imagenes[1]
            ELSE NULL::text
        END AS imagen_principal_real,
        CASE
            WHEN p.imagenes IS NOT NULL AND array_length(p.imagenes, 1) > 0 AND p.imagenes[1] !~~ '%static.tokkobroker.com/tfw/img/prop-icons%'::text AND p.imagenes[1] !~~* '%unsplash.com%'::text AND p.imagenes[1] !~~* '%placeholder%'::text AND p.imagenes[1] !~~* '%no-photo%'::text AND p.imagenes[1] !~~* '%sin-imagen%'::text AND p.imagenes[1] !~~* '%360%'::text AND p.imagenes[1] !~~* '%tour%'::text AND p.imagenes[1] !~~* '%virtual%'::text THEN true
            ELSE false
        END AS tiene_imagen_real
   FROM propiedades p
     JOIN v_propiedades_location_ready plr ON plr.id = p.id
     LEFT JOIN inmobiliarias_main i ON i.id = p.inmobiliaria_id
  WHERE p.latitud IS NOT NULL AND p.longitud IS NOT NULL AND COALESCE(p.estado, 'activo'::text) = 'activo'::text AND p.url !~~* '%inmocapital.test%'::text AND p.url !~~* '%localhost%'::text AND p.url !~~* '%example.com%'::text;
