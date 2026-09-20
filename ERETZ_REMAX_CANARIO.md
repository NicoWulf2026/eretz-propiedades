# Canario RE/MAX: la medición no concluyó, y por qué

**2026-09-14. `database_writes: 0`. Nada implementado.**

---

## 1. Qué se pedía medir

El §17 pide ocho métricas sobre 200–500 fichas del sitemap de RE/MAX
Argentina, para decidir si vale la pena escribir una estrategia nueva. El
sitemap publica **74.529 fichas**.

## 2. Lo que pasó

```
=== RUBRICA §17 — muestra de 200 fichas ===
  ERROR_DE_RED                           0    0,0 %
  ANTIBOT_CUERPO_VACIO                   0    0,0 %
  ANTIBOT_DESAFIO_WAF                  200  100,0 %
  HTTP_READABLE                          0    0,0 %
  ...todo lo demás                       0    0,0 %
```

Las 200 devuelven **HTTP 202 con un desafío de AWS WAF** de 1.971 bytes. No es
la ficha. **No lo resolvimos y no lo vamos a resolver**: saltar una detección de
bots no es algo que corresponda hacer acá.

## 3. La primera corrida mintió, y el defecto era mío

La corrida anterior, de 300 fichas, reportó:

```
  HTTP_READABLE                        300  100,0 %
  LISTING_VALID                          0    0,0 %
  OFFICE_ATTRIBUTION_PRESENT             0    0,0 %
```

Leído literal, eso dice "RE/MAX sirve 300 fichas perfectamente legibles y
ninguna tiene un solo dato". Es falso, y es el mismo error que ya cometimos seis
veces en este proyecto: **tomar "no pudimos leer" como un hallazgo sobre el
otro**.

`HTTP_READABLE` contaba "no tiró excepción". Y `remax.com.ar` responde:

| petición | respuesta |
|---|---|
| sin cabecera `Accept` | HTTP 202, **cero bytes** |
| con `Accept` de navegador | HTTP 202, desafío de AWS WAF |

Cero bytes sin excepción pasaba como "legible". La métrica ahora separa
`ANTIBOT_CUERPO_VACIO` y `ANTIBOT_DESAFIO_WAF` de `HTTP_READABLE`, que quedó
como "sirvió la ficha".

Esto contamina hacia atrás el sondeo previo: su "75 % de fichas sin objeto de
oficina" era, casi con seguridad, el mismo cuerpo vacío contado como ausencia
de datos. Ese número no se puede usar.

## 4. Por qué la medición NO demuestra que la ruta esté cerrada

Media hora antes, el sondeo previo **sí leyó fichas**: 34 oficinas distintas
sobre una muestra de 150, con las mismas urls `/listings/` y el mismo cliente.
Entre las dos corridas hicimos unas 500 peticiones.

Se probó lo obvio: **8 fichas, una cada 25 segundos**. Las 8 devolvieron el
desafío. Pero eso no separa las dos hipótesis, porque la reputación de nuestra
IP ya estaba comprometida por las 500 anteriores:

- el WAF está puesto de forma permanente sobre las fichas, **o**
- el WAF se disparó por nuestro propio volumen y nos tiene marcados.

**Las dos explican todo lo observado.** Una clasificación negativa masiva no se
da por demostrada con una lectura desfavorable, y acá tenemos dos, ambas
tomadas después de habernos marcado solos.

## 5. Lo único que sí quedó medido

Del sondeo previo, sobre las fichas que **sí** sirvieron contenido:

- **34 oficinas distintas** identificadas;
- de ellas, **31 están en nuestro padrón** (89 %).

O sea: cuando la ficha carga, la atribución de oficina está y coincide. Eso es
la mitad buena de la noticia, y es exactamente la mitad que no depende del WAF.

Lo que no sabemos es qué fracción de las 74.529 carga.

## 6. Qué hacer, y qué no

**No hacer ahora:**

- no escribir la estrategia de RE/MAX: se estaría construyendo sobre una
  cobertura que no medimos;
- no resolver el desafío de AWS WAF;
- no repetir la muestra hoy desde esta IP: sólo confirmaría que seguimos
  marcados.

**Hacer:**

1. reintentar en 24–48 h con **una ficha cada 30 s y un tope de 50**, que es un
   ritmo que no vuelve a disparar nada. Si pasan, la ruta existe y el número
   del §17 se puede completar;
2. si a ese ritmo tampoco pasan, la ruta está cerrada para un cliente HTTP y la
   decisión es otra: RE/MAX son 190 oficinas de nuestro padrón y el camino
   pasaría por el sitio de cada oficina, no por el de la red.

Hasta entonces, **RE/MAX no cuenta como inventario proyectado** en el tablero
del 12/10. No hay número que poner.

## 7. Artefactos

- `scripts/canario_remax.py` — la rúbrica del §17, con los bloqueos separados
  de lo legible.
- `ERETZ_REMAX_CANARIO.jsonl` — las 200 filas, cada una con sus bytes y su
  desenlace.
