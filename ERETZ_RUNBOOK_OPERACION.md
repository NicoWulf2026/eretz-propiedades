# ERETZ — Runbook de operación

Para operar el sistema sin auditarlo entero cada mañana. Todo lo de acá es
local y de sólo lectura salvo donde diga lo contrario.

---

## 1. ¿Cómo está todo? (30 segundos)

```bash
python scripts/operacion_reporte.py
```

Devuelve el estado de la cola, el de los datos, y **alertas**. Sólo se enciende
lo que pide una acción humana: que una inmobiliaria esté bloqueada no es una
alerta, es un hecho conocido del mundo.

| Alerta | Qué hacer |
|---|---|
| la cola está parada por un defecto transversal | §3 |
| N líneas ilegibles en los resultados | §6 — dos procesos escribieron el mismo artefacto |
| N propiedades reales quedaron fuera por incompletitud | es la regla que no se negocia: revisar el quality gate |
| cerrojo sin proceso vivo | §5 |
| no hay ningún runner en curso | §2 |
| `<campo>` falla en N propiedades que la fuente sí publica | §7 |

---

## 2. Abrir la cola

**Siempre** preflight primero. Si no da 7/7, no se abre: cada chequeo existe
porque su ausencia ya costó algo.

```bash
python scripts/agency_rollout_preflight.py
```

Con un worker:

```bash
schtasks /run /tn ERETZ_cola_certificacion
```

Con dos (reparto por host, ver §4):

```bash
schtasks /run /tn ERETZ_cola_w0
```

```bash
schtasks /run /tn ERETZ_cola_w1
```

Task Scheduler y no una consola: una consola compartida con otro proceso muere
cuando ese proceso muere, y ya pasó tres veces.

---

## 3. La cola paró sola

Paró porque el triage encontró un defecto de radio transversal. **No se reabre
sin arreglarlo**: reabrir camina hacia la misma parada, y las agencias que
certifique en el camino habrá que rehacerlas igual.

1. Leer el último renglón de `cola_task.log` o `cola_w*.log`: dice qué
   inmobiliaria, qué componente se sospecha y con qué evidencia.
2. Diagnosticar **contra la fuente real**, no contra los tests. Un test que
   pasa no prueba nada sobre un sitio que cambió.
3. Arreglar, correr la suite, y recertificar esa inmobiliaria a mano:
   ```bash
   python scripts/agency_certifier.py --canonical-id "<id>"
   ```
4. Preflight y reabrir.

Si el defecto toca `connectors/base.py`, `geografia.py`, `texto.py`,
`coherencia.py` o `generico.py`, invalida **todas** las huellas: conviene
juntarlo con otros cambios pendientes del mismo radio y pagar una sola
recertificación. Ver §8.

---

## 4. Dos workers

El reparto es **por host**, no por posición: la cortesía se le debe al sitio y
el limitador vive dentro de cada proceso, así que dos workers sobre el mismo
host pedirían al doble del ritmo acordado sin que ninguno se entere.

- Cada worker tiene su cerrojo (`...RUNNER.w0.lock`) y su progreso.
- Un STOP transversal escribe `AGENCY_CERTIFICATION_STOP.json` y **corta a los
  dos**. Esa bandera se borra sola al abrir.
- Nunca más de dos. Más procesos contra sitios de inmobiliarias chicas deja de
  ser paralelismo y pasa a ser una molestia para ellas.

---

## 5. Cerrojo huérfano

Un cerrojo sin proceso vivo bloquea la apertura. **Antes de borrarlo hay que
probar que el PID murió**, no suponerlo:

```bash
powershell -c "Get-Process -Id <pid> -ErrorAction SilentlyContinue"
```

Si no devuelve nada, recién ahí se borra el `.lock`. Borrarlo con el proceso
vivo pone dos runners sobre el mismo checkpoint.

---

## 6. Líneas ilegibles en un artefacto

Señal de que dos procesos escribieron el mismo archivo sin append atómico.
`append_jsonl` usa `O_APPEND` con un solo `os.write`, así que no debería pasar;
si pasa, hay un escritor que no lo usa. Buscarlo antes de seguir: ese archivo
es la fuente de verdad de las certificaciones.

---

## 7. Un campo que falla mucho

```bash
python scripts/extraction_failures.py
```

Agrupa por familia y campo, no por campo suelto: un campo que falla en ocho
lugares distintos no es un problema, y ocho campos que fallan en el mismo lugar
son uno solo. `familias_con_falla_ancha` marca las familias donde la lectura
estructurada directamente no está ocurriendo.

El arreglo se valida en cuatro pasos, no en uno: test, fuente real, RUN1/RUN2,
y before/after sobre las candidatas.

---

## 8. Ventana semántica

Cuando hay varios cambios pendientes que tocan componentes compartidos:

1. Esperar a que **no haya certificación en vuelo**. Editar un archivo
   fingerprintado con la cola corriendo hace que se estampen huellas de código
   que no es el que se ejecutó.
2. Calcular el radio antes de aplicar:
   ```bash
   python -c "from scripts.agency_fingerprints import fingerprint_components; print(sorted(fingerprint_components('generico','generic/html_catalog')))"
   ```
   `shared/*` está en toda estrategia: transversal. `connector/<x>` sólo en esa
   familia.
3. Si comparten radio, van juntos: se paga una recertificación en vez de tres.
4. Aplicar, suite completa, medir before/after, preflight, reabrir.

**Nunca** reducir artificialmente una invalidación. Un módulo semántico fuera
de la huella produce certificaciones falsamente vigentes, y ya pasó tres veces.

---

## 9. Regenerar los artefactos de datos

En este orden, porque cada uno consume al anterior:

```bash
python scripts/geo_coverage_audit.py && python scripts/property_quality_gate.py && python scripts/api_contract.py && python scripts/api_snapshot.py
```

La snapshot de la API es **derivada y desechable**: se reconstruye entera y no
es fuente de verdad de nada.

---

## 10. Lo que NO se hace sin autorización

Escrituras productivas, migraciones, RLS, borrado de datos productivos, `git
push`, merge remoto, deploy, borrar repos o proyectos remotos, DNS, servicios
pagos, exponer o rotar secretos.

Ante cualquiera de esos: preparar diff, backup, rollback, números exactos y
riesgos, marcarlo `WAITING_USER_AUTHORIZATION`, y **seguir con otra cosa**.
