# Brave a 250 inmobiliarias: qué salió, qué costó, y si esto escala

**2026-09-14. `database_writes: 0`. Ninguna web se promovió a nada.**

---

## 1. La selección, y por qué no es "las 250 más fáciles"

250 agencias sin web resuelta, ordenadas por avisos —que es lo que se recupera
si la web aparece— con dos topes:

| | |
|---|---:|
| seleccionadas | 250 |
| avisos en juego | 54.739 |
| zonas distintas | 115 |
| tope por zona | 18 |
| tope de oficinas de red | 40 |
| nombre débil (entran marcadas) | 28 |

**El tope de red se agregó después de una selección mala.** La primera, sólo por
volumen, metía **137 oficinas de red en 250** cuando en la pileta son el 3 %.
Habría gastado media corrida reconfirmando el caso que ya entendemos —una
página de oficina no es una web propia— sin decir nada de las 8.600 restantes.
Se cortó con 9 agencias gastadas.

## 2. Lo que costó

```
resueltas          250
queries usadas     475      (el techo eran 750)
costo             USD 2,38
sin gastar query    52      se resolvieron con evidencia local
```

## 3. Lo que devolvió

| clase | n |
|---|---:|
| `OFFICIAL_WEB` | 109 |
| `EXTERNAL_PORTAL_PROFILE` | 71 |
| `OFFICIAL_OFFICE_PAGE` | 36 |
| `REVIEW_REQUIRED` | 28 |
| `IDENTITY_AMBIGUOUS` | 5 |
| `NO_OFFICIAL_WEB_FOUND` | 1 |

145 afirman una web propia o una página de oficina.

## 4. La auditoría, y las dos veces que me equivoqué midiéndola

Se auditaron **95** —las 65 marcadas por riesgo, enteras, más 30 ALTA al azar—
con una comprobación **independiente**: el verificador decidió mirando nombre,
dominio y título; volver a mirar lo mismo confirmaría su propio criterio en vez
de auditarlo.

**Primer intento: 63,9 %.** Falso. Mi regla decía "está bajo el dominio de la
red → falso positivo", y los 26 así marcados estaban clasificados
`OFFICIAL_OFFICE_PAGE` / `NETWORK_OFFICE_PAGE`, que es exactamente lo que son.
Estaba castigando al verificador por acertar.

**Segundo intento: 100 %.** También falso. Entre las 17 que la comprobación no
supo decidir había falsos positivos que no podía ver —una bolsa de trabajo, un
perfil de portal, una nota de diario— y además aciertos descartados por comparar
el nombre entero: `estudioelhelou.com.ar` es de "Emir Elhelou Estudio
Inmobiliario", pero la comparación borraba "estudio" y no coincidía.

### El número, con las reglas corregidas

| | marcadas (65) | muestra ALTA (30) | total |
|---|---:|---:|---:|
| confirmada | 28 | 27 | 55 |
| correcta como oficina | 26 | — | 26 |
| **falso positivo** | **4** | **1** | **5** |
| parcial | 1 | — | 1 |
| sin decidir | 1 | — | 1 |
| no se pudo descargar | 5 | 2 | 7 |

**Precisión: 93,1 %** — 81 bien de 87 donde la comprobación pudo decidir.

En la muestra aleatoria de ALTA, que es el caso ordinario: **27 de 28
decididas**.

Dos límites que el número tiene y hay que decir:

- se auditaron las 95 más difíciles, no las 145. Las 50 sin auditar son las
  ALTA sin marca, y el muestreo de esas dio 96,4 %;
- las 7 "no se pudo descargar" son fallas **nuestras** de red, no hallazgos
  sobre esas agencias. No cuentan ni a favor ni en contra.

## 5. Los 5 falsos positivos son todos la misma cosa

| agencia | lo que declaró como web propia |
|---|---|
| Colmena Uruguay | `realedo.com/uruguay/profile/agency/156` — perfil de portal |
| Inmobiliaria Leonardo Giar | `realedo.com/uruguay/profile/agency/257` — perfil de portal |
| FULLINMO SAS | `ar.computrabajo.com/trabajo-de-corredor-inmobiliario` — bolsa de trabajo |
| ORIGO | `misionesonline.net/2024/03/21/origen-p...` — nota de diario |
| Mudafy Lhouse | `mudafy.com.ar` — portal |

**Los cinco son `OFFICIAL_WEB` sobre el sitio de un tercero.** No hay cinco
problemas: hay uno, y es que la lista de portales del verificador no conoce
`realedo.com`, `computrabajo.com`, `mudafy.com.ar` ni los medios. Es dato, no
estructura.

Detalle aparte: dos de los cinco son de **Uruguay**. Hay agencias uruguayas en
el padrón y nadie las separó.

## 6. El gate: ¿se escala?

**Sí, con una condición previa.**

A favor:

- USD 2,38 por 250. Llevarlo a las ~8.600 sin web serían unas 16.300 queries,
  **USD 82**. El costo no es el problema;
- 52 de 250 se resolvieron sin gastar una sola query;
- 93,1 % de precisión sobre la rebanada difícil, y ningún error de la forma
  peligrosa —declarar propia la página de una red—.

La condición: **agregar los hosts de la tabla de arriba a la lista de portales
del verificador antes de la próxima corrida**. Son cinco líneas de datos, no
tocan ninguna huella —`verificador_identidad_v2.py` no es componente de
ninguna— y eliminan la única familia de error que apareció.

### Hecho el mismo día

- `realedo`, `mudafy` y `apuntavamos` entraron a `PORTALES`;
- `misionesonline` y tres medios regionales más, a `MEDIOS`;
- se agregó `BOLSAS_DE_TRABAJO` —`computrabajo`, `bumeran`, `zonajobs`,
  `indeed`— aparte de `PORTALES`, porque una bolsa de empleo no es un portal
  inmobiliario aunque el desenlace sea el mismo.

Con **siete tests nuevos**: uno por cada uno de los cinco casos medidos, para
que si alguien saca un host de la lista el test diga cuál; uno de que una bolsa
de trabajo se clasifica `EXTERNAL_PORTAL`; y uno que comprueba que la lista más
larga **no** alcanza a ningún sitio propio de verdad —brunetti, civeira,
elhelou, cocucci y la oficina `remax-premium.com.ar`, que tiene dominio propio—.

El gate de huellas se volvió a correr después del cambio: **cero huellas
cambian por esta modificación**. Las 5 que figuran distintas son las mismas
`BLOCKED_EXTERNAL` certificadas entre el 2 y el 8 de septiembre, deriva previa.

Lo que **no** se hace igual: escribir una sola de estas 145 webs en el
padrón. Un resultado de Brave no demuestra `OFFICIAL_WEB`, y nuestro verificador
solo tampoco.

## 7. Artefactos

- `BRAVE_250_SELECCION.jsonl` — las 250 elegidas, con su motivo.
- `BRAVE_250.jsonl` — el resultado, sin payload de Brave.
- `BRAVE_250_AUDITORIA.jsonl` — las 95 auditadas, cada una con su
  `veredicto_maquina` y por qué. `veredicto_humano` sigue en `null`: no es lo
  mismo y el archivo no los mezcla.
