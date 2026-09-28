# ERETZ AUTOMATION — encender y apagar la cola de certificación

Dos archivos en la raíz de `D:\INMO CAPITAL\eretz-unified`:

| archivo | qué hace |
|---|---|
| `ERETZ_AUTOMATION_ON.cmd` | enciende todo y muestra el estado |
| `ERETZ_AUTOMATION_OFF.cmd` | apaga todo (los workers cierran la agencia en curso y salen) |

Por debajo: `python scripts\eretz_automatizacion.py on | off [--inmediato] [--esperar N] | estado`.
Bitácora de cada ON/OFF: `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_AUTOMATION.log`.

## ON
- Borra el interruptor `ERETZ_AUTOMATION_OFF.json` y la bandera de paro de radio `APAGADO`.
  Nunca borra la bandera de un defecto (esa se diagnostica y se firma).
- Crea o reemplaza —`schtasks /Create /F`, nunca duplica— dos tareas del usuario:
  - `ERETZ_relanzador`: cada 10 min y 2 min después de iniciar sesión. Lanza los workers que
    falten, **máximo 2**, respetando paros y familias detenidas (`relanzar_la_cola.py`).
  - `ERETZ_vigilante_paros`: cada 5 min y al iniciar sesión. Escribe
    `ERETZ_QUEUE_WATCH_STATUS.json`. Con `--sin-alerta`: **sin toast, sin `msg.exe`, sin pitidos**.
- Las dos corren con `pythonw.exe` (sin consola ni ventanas), `IgnoreNew` (una pasada a la vez),
  límite de 5 min por pasada, y siguen con batería. Logs: `relanzador.log`, `vigilante.log` y
  `cola_w0.log` / `cola_w1.log` en la carpeta de salida.
- Dispara el relanzador una vez (no espera 10 min).
- Recuperación: si un worker muere, la próxima pasada lo relanza; tras reiniciar la PC, al
  iniciar sesión. No se duplican workers: lo controlan el relanzador, `IgnoreNew` y el cerrojo
  por worker del runner.

## OFF
1. Escribe el interruptor `ERETZ_AUTOMATION_OFF.json`. Desde ahí `relanzar_la_cola.py` no lanza
   nada y `run_agency_certification_queue.py` no arranca (ni a mano, ni desde un `.bat` viejo;
   solo con `--ignorar-apagado`). Si el archivo es ilegible, cuenta como apagado.
2. Deshabilita las tareas (las nuestras y las viejas `ERETZ_cola_*` si existieran) y termina las
   pasadas en curso. Deshabilitar, no borrar: el ON las rehace.
3. Pide a los workers que paren (bandera de paro, radio `APAGADO`): cada uno termina la agencia
   en curso y sale. Puede tardar lo que dure esa agencia (hasta ~90 min en catálogos grandes).
   `--inmediato` los termina ya (se pierde la agencia en curso, que se recertifica después).

## Apagar a mano (sin los scripts)
1. Crear el archivo `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_AUTOMATION_OFF.json`
   con cualquier contenido (ilegible = apagado). Con eso ya nadie relanza.
2. Deshabilitar las tareas:
   `schtasks /Change /TN ERETZ_relanzador /DISABLE` y `schtasks /Change /TN ERETZ_vigilante_paros /DISABLE`
   (o en el Programador de tareas: clic derecho → Deshabilitar).
3. Workers: esperar a que terminen, o cortarlos en el Administrador de tareas (procesos
   `python.exe`/`pythonw.exe` con `run_agency_certification_queue.py` en la línea de comandos).

## Ver el estado
`python scripts\eretz_automatizacion.py estado` → interruptor, tareas (próxima ejecución,
último resultado) y workers vivos.

Nada de esto toca producción ni la huella de certificación: `database_writes: 0`.
