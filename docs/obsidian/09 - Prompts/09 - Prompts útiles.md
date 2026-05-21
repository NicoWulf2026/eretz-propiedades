# Prompts útiles

Esta nota sirve para guardar prompts importantes de InmoCapital.

La idea es tener textos listos para copiar y pegar en ChatGPT, Codex, Claude Code u otra herramienta de IA cuando necesite pedir ayuda técnica, estratégica, comercial o de documentación.

---

## Regla principal

Antes de usar un prompt técnico, conviene pegar primero el contexto general del proyecto desde la nota:

[[13 - Estado actual para ChatGPT o Codex]]

Después agregar el problema puntual.

---

## Prompt base para ChatGPT, Codex o Claude

Estoy trabajando en InmoCapital, una plataforma proptech para centralizar, estandarizar y analizar información inmobiliaria de distintas inmobiliarias.

El proyecto está ubicado localmente en:

D:\INMO CAPITAL\Inmo-Capital-main

Uso Next.js, Tailwind, Leaflet, Python, Playwright, Supabase y GitHub.

Reglas importantes:

- No borrar tablas sin revisar.
- No modificar la base de datos de forma destructiva.
- No corregir errores manualmente en Supabase si pueden corregirse desde el código.
- Los errores de scraping deben corregirse en el scraper para que no vuelvan a repetirse.
- Necesito instrucciones paso a paso porque no soy experto programando.
- Antes de cambiar algo importante, explicame qué se va a modificar y por qué.
- No quiero soluciones improvisadas.
- Quiero priorizar estabilidad, calidad de datos y escalabilidad.

Prioridad actual:

Mejorar el scraping, corregir errores desde código, aumentar propiedades correctamente guardadas y mantener la calidad de datos.

---

## Prompt para corregir errores de scraping

Estoy trabajando en el scraper de InmoCapital.

Necesito que analices el error que te voy a pasar y me ayudes a corregirlo desde el código, no desde Supabase manualmente.

Reglas importantes:

- No borrar tablas.
- No modificar datos de forma destructiva.
- No hacer cambios grandes sin explicar.
- No corregir datos a mano si el problema viene del scraper.
- La solución debe evitar que el error vuelva a repetirse en futuros scrapeos.
- Quiero instrucciones paso a paso.
- Indicame qué archivo tocar, qué cambiar y cómo probarlo.

Objetivo:

Detectar la causa del error, corregirlo desde el código, mejorar logs si hace falta y confirmar que el scraper pueda seguir funcionando sin trabarse.

Te paso el error o salida de consola:

[Pegar acá el error]

---

## Prompt para revisar una corrida de scraping

Estoy trabajando en InmoCapital y acabo de ejecutar una corrida de scraping.

Necesito que me ayudes a interpretar el resultado.

Quiero saber:

- Qué salió bien.
- Qué salió mal.
- Qué errores son importantes.
- Qué errores se repiten.
- Qué debería corregirse primero.
- Si hay problemas con propiedades detectadas pero no guardadas.
- Si quedaron items trabados en running.
- Si hay problemas de coordenadas, imágenes, precios o duplicados.
- Qué debería pedirle a Codex que corrija.

Reglas:

- No quiero corregir manualmente en Supabase si se puede corregir desde código.
- Quiero priorizar errores que afecten el guardado de propiedades.
- Quiero una explicación clara y paso a paso.

Resultado de la corrida:

[Pegar acá la salida de consola o tabla]

---

## Prompt para pedir mejora de logs del scraper

Estoy trabajando en el scraper de InmoCapital.

Necesito mejorar los logs para entender mejor qué pasa en cada inmobiliaria procesada.

Quiero que el scraper muestre claramente:

- ID de inmobiliaria.
- Nombre de inmobiliaria.
- URL procesada.
- Estrategia usada.
- Estado final.
- Propiedades detectadas.
- Propiedades nuevas.
- Propiedades actualizadas.
- Propiedades descartadas.
- Propiedades con error.
- Motivo de descarte.
- Error type.
- Error message.
- Duración del proceso.

Reglas:

- No romper el funcionamiento actual.
- No borrar datos.
- No modificar Supabase de forma destructiva.
- Hacer cambios chicos y claros.
- Explicarme qué archivos se van a tocar.
- Darme comandos para probar.

Objetivo:

Que después de cada corrida pueda entender exactamente qué pasó y qué hay que corregir.

---

## Prompt para revisar Supabase

Estoy trabajando en Supabase para InmoCapital.

Necesito que me ayudes a revisar el estado de la base de datos sin hacer cambios destructivos.

Quiero consultas SQL para revisar:

- Total de propiedades.
- Propiedades con coordenadas.
- Propiedades sin coordenadas.
- Propiedades con imágenes.
- Propiedades sin imágenes.
- Propiedades con precio.
- Propiedades sin precio.
- Propiedades por ciudad.
- Propiedades por provincia.
- Posibles duplicados.
- Últimas corridas de scraping.
- Items trabados en running.
- Errores de scraping más frecuentes.

Reglas:

- Solo consultas SELECT.
- No DELETE.
- No DROP.
- No TRUNCATE.
- No UPDATE masivo.
- Explicame qué hace cada consulta.
- Quiero resultados fáciles de interpretar.

---

## Prompt para pedir una consulta SQL

Necesito una consulta SQL para Supabase/PostgreSQL dentro del proyecto InmoCapital.

Objetivo de la consulta:

[Explicar qué quiero ver]

Tablas relacionadas:

[Indicar tabla o tablas si las sé]

Reglas:

- Solo SELECT salvo que yo pida explícitamente otra cosa.
- No borrar datos.
- No modificar datos.
- Que la consulta sea clara.
- Que tenga alias entendibles.
- Que ordene los resultados de forma útil.
- Explicame brevemente qué hace.

---

## Prompt para revisar datos de propiedades

Estoy trabajando con la tabla de propiedades de InmoCapital.

Necesito revisar la calidad de los datos.

Quiero detectar:

- Propiedades sin coordenadas.
- Propiedades sin imágenes.
- Propiedades sin precio.
- Propiedades sin ciudad.
- Propiedades sin provincia.
- Propiedades con moneda incorrecta.
- Propiedades con operación faltante.
- Propiedades con tipo de propiedad faltante.
- Posibles duplicados.
- Coordenadas fuera de rango.
- Ciudades o provincias mal normalizadas.

Reglas:

- No modificar datos.
- Solo consultas de diagnóstico.
- Priorizar problemas que afecten el frontend y la experiencia del usuario.
- Darme consultas SQL listas para pegar.

---

## Prompt para pedir corrección automática de normalización

Estoy trabajando en InmoCapital y necesito mejorar la normalización de datos desde el código.

El problema es:

[Explicar problema: ciudad, provincia, barrio, precio, moneda, operación, tipo de propiedad, etc.]

Reglas:

- No quiero corregir estos datos manualmente en Supabase.
- Quiero que el scraper o el proceso de normalización lo resuelva automáticamente.
- No borrar datos.
- No hacer cambios destructivos.
- Mantener valor original si puede ser útil.
- Explicarme qué archivo tocar.
- Darme una forma de probar la corrección.

Objetivo:

Que los próximos scrapeos guarden los datos correctamente y que el problema no vuelva a repetirse.

---

## Prompt para frontend

Estoy trabajando en el frontend de InmoCapital.

Uso Next.js, Tailwind, App Router y Leaflet.

Necesito ayuda con:

[Explicar problema o mejora]

Reglas:

- No romper la conexión con Supabase.
- No borrar componentes importantes.
- Mantener diseño responsive.
- Priorizar mobile.
- Evitar cambios innecesarios.
- Explicarme paso a paso qué archivo modificar.
- Darme el código listo para pegar si corresponde.
- Indicar cómo probar el cambio.

Objetivo:

Mejorar la experiencia del usuario sin romper el proyecto.

---

## Prompt para mejorar cards de propiedades

Estoy trabajando en las cards de propiedades de InmoCapital.

Quiero que las cards sean más claras, modernas y útiles.

Deben mostrar:

- Imagen real o placeholder propio.
- Precio.
- Moneda.
- Título.
- Ubicación.
- Tipo de propiedad.
- Operación.
- Ambientes.
- Dormitorios.
- Superficie.
- Inmobiliaria.
- Botón o link de contacto.

Reglas:

- No mostrar campos vacíos de forma fea.
- No romper el diseño mobile.
- No mostrar imágenes rotas.
- No modificar Supabase.
- Mantener diseño limpio y profesional.

Objetivo:

Mejorar la experiencia visual y hacer que la card ayude al usuario a decidir rápido.

---

## Prompt para mapa

Estoy trabajando en el mapa de InmoCapital.

Uso Leaflet.

Necesito ayuda para:

[Explicar problema o mejora]

Reglas:

- No mostrar propiedades sin coordenadas válidas.
- No romper el listado lateral.
- Mantener buena experiencia mobile.
- Usar datos desde Supabase.
- Evitar que el mapa se vuelva lento.
- Explicarme qué archivos tocar.
- Darme pasos para probar.

Objetivo:

Que el mapa sea claro, rápido y útil para explorar propiedades.

---

## Prompt para GitHub

Estoy trabajando en el proyecto InmoCapital en mi computadora.

Ubicación local:

D:\INMO CAPITAL\Inmo-Capital-main

Necesito ayuda para usar Git/GitHub sin romper nada.

Quiero que me expliques paso a paso, como si no supiera usar Git.

Reglas:

- No usar comandos destructivos.
- No hacer force push salvo que sea absolutamente necesario y explicado.
- Antes de subir cambios, revisar estado.
- Explicarme qué hace cada comando.
- Darme los comandos en orden.
- No asumir que sé programar.

Objetivo:

Guardar correctamente los cambios del proyecto y subirlos a GitHub de forma segura.

---

## Prompt para actualizar Obsidian

Estoy trabajando en Obsidian como centro de control de InmoCapital.

Necesito actualizar la documentación del proyecto con esta información:

[Pegar información nueva]

Quiero que me ayudes a decidir:

- En qué nota debería guardarse.
- Cómo debería redactarse.
- Si corresponde agregarlo a decisiones importantes.
- Si corresponde agregarlo a errores y soluciones.
- Si corresponde agregarlo a pendientes.
- Si corresponde actualizar estado actual para ChatGPT o Codex.

Reglas:

- Mantener orden.
- No duplicar información innecesariamente.
- Redactar en formato claro, listo para copiar y pegar.

---

## Prompt para estrategia

Estoy trabajando en la estrategia de InmoCapital.

Necesito analizar:

[Explicar tema: modelo de negocio, lanzamiento, inmobiliarias, pricing, expansión, diferenciación, etc.]

Contexto:

InmoCapital busca centralizar, estandarizar y analizar información inmobiliaria. No quiere ser solo otro portal de propiedades, sino una herramienta para entender mejor el mercado.

Quiero una respuesta clara, estratégica y realista.

Tener en cuenta:

- Calidad de datos.
- Usuarios.
- Inmobiliarias.
- Modelo B2B.
- Riesgos legales.
- Costos.
- Diferenciación.
- Escalabilidad.

---

## Prompt para marketing

Estoy trabajando en el marketing de InmoCapital.

Necesito ayuda para:

[Explicar necesidad: landing, redes, propuesta de valor, textos, presentación para inmobiliarias, etc.]

Contexto:

InmoCapital no es simplemente otro portal de propiedades. La propuesta es centralizar datos inmobiliarios y ayudar a usuarios a entender mejor el mercado.

Tono deseado:

- Claro.
- Profesional.
- Moderno.
- Simple.
- Confiable.
- No exagerado.
- No demasiado técnico.

Quiero textos listos para copiar y pegar.

---

## Prompt para finanzas

Estoy trabajando en el modelo de negocio de InmoCapital.

Necesito analizar:

[Explicar tema: ingresos, costos, pricing, leads, planes para inmobiliarias, reportes, etc.]

Contexto:

El modelo pensado es principalmente B2B. La plataforma podría generar ingresos con inmobiliarias, leads, publicidad no invasiva, reportes de mercado y herramientas de analítica.

Quiero una respuesta realista, con ventajas, riesgos y recomendaciones.

---

## Prompt para legal

Estoy trabajando en los riesgos legales de InmoCapital.

Necesito analizar:

[Explicar tema: scraping, uso de datos, imágenes, términos y condiciones, privacidad, inmobiliarias, etc.]

Importante:

No necesito asesoramiento legal definitivo, sino ordenar riesgos, preguntas y criterios para consultar con un abogado.

Tener en cuenta:

- Scraping.
- Datos públicos.
- Imágenes.
- Datos personales.
- Links a fuentes originales.
- Reclamos de inmobiliarias.
- Términos y condiciones.
- Política de privacidad.
- Publicidad y leads.

---

## Prompt para crear documento formal

Necesito redactar un documento formal sobre InmoCapital.

Tema:

[Indicar tema]

Quiero que el documento esté listo para copiar y pegar en Word.

Tono:

- Formal.
- Claro.
- Profesional.
- Ordenado.
- Sin emojis.
- Con títulos y secciones.

Contexto:

InmoCapital es una plataforma proptech orientada a centralizar, estandarizar y analizar información inmobiliaria de distintas inmobiliarias para ayudar a usuarios, inmobiliarias e inversores a entender mejor el mercado.

---

## Prompt para hacer resumen ejecutivo

Necesito un resumen ejecutivo de InmoCapital.

Debe explicar:

- Qué es InmoCapital.
- Qué problema resuelve.
- Cuál es la solución.
- A quién está dirigido.
- Cómo se diferencia.
- Modelo de negocio posible.
- Estado actual del proyecto.
- Próximos pasos.

Tono:

- Claro.
- Profesional.
- Directo.
- Entendible para alguien que no conoce el proyecto.

---

## Prompt para pedir plan de trabajo

Estoy trabajando en InmoCapital y necesito un plan de trabajo.

Objetivo:

[Indicar objetivo]

Quiero que me armes un plan paso a paso, ordenado por prioridad.

Tener en cuenta:

- No soy experto programando.
- Necesito instrucciones claras.
- No quiero romper el proyecto.
- Quiero avanzar de forma segura.
- Priorizar lo urgente y lo que más impacto tiene.

Formato deseado:

- Fase 1.
- Fase 2.
- Fase 3.
- Tareas concretas.
- Orden recomendado.
- Qué revisar al terminar cada fase.

---

## Prompt para diagnóstico general del proyecto

Necesito hacer un diagnóstico general del estado actual de InmoCapital.

Quiero revisar:

- Desarrollo técnico.
- Scraping.
- Supabase.
- Calidad de datos.
- Frontend.
- Producto.
- Marketing.
- Finanzas.
- Legal.
- Pendientes.
- Riesgos principales.

Quiero que me indiques:

- Qué está bien.
- Qué está incompleto.
- Qué es urgente.
- Qué puede esperar.
- Qué harías primero.
- Qué decisiones habría que tomar.

---

## Prompts pendientes por crear

- Prompt para presentación comercial a inmobiliarias.
- Prompt para landing page completa.
- Prompt para análisis de competencia.
- Prompt para estrategia de lanzamiento.
- Prompt para dashboard de métricas.
- Prompt para IA asesora inmobiliaria.
- Prompt para política de privacidad.
- Prompt para términos y condiciones.
- Prompt para pitch de inversión.
- Prompt para roadmap técnico.