# Plan de capacidad hacia el 12/10

**Medido el 2026-09-14. Nada contratado, nada ejecutado. `database_writes: 0`.**

---

## 1. El número que hay que mirar antes de comprar nada

Sobre **1.770 certificaciones reales** con duración medida:

```
mediana  203 s     media  491 s     p90  1.200 s     maxima  10.846 s
```

Con esa media, la máquina que ya tenemos da:

| | workers | agencias/día teóricas |
|---|---:|---:|
| **1 máquina (hoy)** | 2 | **352** |
| 2 máquinas | 4 | 703 |
| 3 máquinas | 6 | 1.055 |

Y el ritmo real es **21 agencias nuevas por día**.

> **Estamos usando el 6 % de la capacidad que ya está instalada.**

Comprar una segunda máquina hoy duplicaría un 6 %. Sería pagar por no resolver
el problema.

---

## 2. Dónde se va el 94 %

Tres causas, todas medidas:

**a) La cola reprocesa lo mismo en cada relanzamiento.** `ordenar_para_correr`
va canarios → bulk conocido → cola larga, y las nunca certificadas se agregan
*al final del bulk*. Como los paros llegan cada ~20 agencias y cada
relanzamiento arranca del principio de la partición, los workers casi nunca
alcanzan terreno nuevo. En 8 horas se escribieron 187 certificaciones sobre 55
agencias, **de las cuales 5 eran nuevas**.

**b) Cada paro cuesta un ciclo completo.** Diagnóstico contra la fuente,
anotación y relanzamiento. Hoy fueron 43 paros.

**c) La cola larga.** `federico negro` tiene 1.429 propiedades y agota el
presupuesto en las dos corridas; la p90 de 1.200 s y la máxima de 10.846 s
salen de ahí.

---

## 3. Lo que hay que hacer antes de agregar hardware

| # | acción | ganancia estimada | costo |
|---|---|---|---|
| 1 | **Poner las nunca certificadas después de los canarios** | de 21 a ~150/día | una línea + su test |
| 2 | Presupuesto por clase (§22) para la cola larga | evita que una agencia coma horas | media jornada |
| 3 | Cerrar por regla las 2.488 de staging automatables | **2.488 terminales sin certificar** | ya está el breakdown |

La tercera es la más grande y no necesita workers: son agencias que se cierran
con lo ya escrito —portal ajeno, dominio muerto, oficina de red, sin
inventario—, no con una corrida.

---

## 4. Con eso, ¿alcanza?

```
faltan            6.439 no terminales
dias al 12/10        28
requerido           230 por dia
```

- Cerrando por regla las **2.488** automatables: quedan 3.951 → **141/día**.
- Sumando las **784** que ya tienen web verificada y sólo esperan promoción:
  quedan 3.167 → **113/día**.
- Con la cola arreglada (~150/día medidos contra 352 teóricas, o sea 43 % de
  utilización), **113/día es alcanzable con la máquina actual.**

**Conclusión: no hace falta una segunda máquina si se arregla la utilización y
se cierran por regla las que se pueden cerrar.** Hace falta si alguna de esas
dos cosas no ocurre.

---

## 5. Si igual hace falta: la propuesta

No contratar todavía. Esto queda listo para ejecutar el día que los números lo
pidan.

### Máquina

| | mínimo | recomendado |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disco | 80 GB SSD | 160 GB SSD |
| SO | Ubuntu 24.04 LTS | idem |
| Red | 100 Mbps | idem |

El pico de RAM medido es **2,6 GB por worker**, así que 8 GB soportan 2 workers
con margen. El scraping es 99,65 % I/O, por eso la CPU importa poco y la RAM y
la red importan más.

### Costo

| proveedor | tipo | USD/mes | USD/día | hasta el 12/10 (28 d) |
|---|---|---:|---:|---:|
| Hetzner CPX31 | 4 vCPU / 8 GB | ~16 | 0,53 | **~15** |
| DigitalOcean | 4 vCPU / 8 GB | ~48 | 1,60 | ~45 |
| AWS t3.large | 2 vCPU / 8 GB | ~60 | 2,00 | ~56 |

**Hetzner por precio**, y porque el trabajo es I/O y no necesita nada de AWS.
Con dos máquinas hasta el 12/10 el costo total es **menos de USD 30**.

### Cómo se reparte sin pisarse

El mecanismo ya existe y está probado: `particion()` reparte **por host**, no
por posición, usando `sha256(host) % workers == worker`. Es determinístico, así
que la misma cola y el mismo número de workers dan siempre el mismo reparto.

Para dos máquinas:

- máquina A corre `--workers 4 --worker 0` y `--worker 1`
- máquina B corre `--workers 4 --worker 2` y `--worker 3`

Repartir por host importa por una razón concreta: **la cortesía se le debe al
sitio y el limitador vive dentro de cada proceso.** Si dos máquinas pudieran
tocar el mismo host, le estaríamos pidiendo al doble del ritmo acordado sin que
ninguna se entere.

### Cerrojos y resultados

- El cerrojo es por archivo y ya está sufijado por worker
  (`AGENCY_CERTIFICATION_RUNNER.w2.lock`), con latido cada 60 s.
- Los resultados son **JSONL de append**: dos máquinas escribiendo entradas
  distintas no se pisan, pero el archivo tiene que estar en almacenamiento
  compartido o sincronizarse. Lo más simple y sin infraestructura nueva:
  cada máquina escribe su propio `AGENCY_CERTIFICATION_RESULTS.w{N}.jsonl` y
  se concatenan al leer. **Eso hay que implementarlo: hoy el nombre es único.**
- Las diferidas (`AGENCY_DEFECTS_DIFERIDOS.jsonl`) se leen al arrancar, así
  que alcanza con copiarlas a la máquina B antes de lanzar.

### Secretos

`BRAVE_SEARCH_API_KEY` y las credenciales de Postgres van por variable de
entorno en la máquina B, nunca en el repo. La máquina B **no necesita** la
credencial de Postgres: sólo certifica, no escribe.

---

## 6. Proyección con más máquinas

Suponiendo la utilización arreglada (43 %, que es lo que da ~150/día por
máquina):

| capacidad | agencias/día | 3.167 restantes | ¿llega al 12/10? |
|---|---:|---:|---|
| 1 máquina (hoy) | ~150 | 21 días | **sí, con 7 de margen** |
| 2 máquinas | ~300 | 11 días | sí, con holgura |
| 3 máquinas | ~450 | 7 días | sí |

**Sin arreglar la utilización**, ninguna cantidad de máquinas llega: 21/día × 3
son 63/día contra 230 requeridas.

---

## 7. Recomendación

1. **Arreglar el orden de la cola** — es lo que multiplica todo lo demás.
2. **Cerrar por regla las 2.488** automatables del breakdown de staging.
3. **No contratar todavía.** Volver a medir con 1 y 2 aplicados.
4. Si a los 3 días de eso el ritmo real sigue debajo de 113/día, contratar
   Hetzner: son USD 15 hasta el 12/10 y el reparto por host ya está resuelto.
