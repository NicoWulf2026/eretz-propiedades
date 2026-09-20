# Decision Ledger

Decisiones tomadas con evidencia. No se vuelven a discutir sin evidencia
**nueva**; cada una dice qué la reabriría.

Formato: qué problema había, qué se midió, qué se decidió, qué se descartó, y
bajo qué condición volver a mirarla.

---

## D-001 · El TTL de una diferida cuenta desde la última mirada, no desde la firma

**2026-09-14 · aplicado**

**Problema.** Las agencias ya diagnosticadas volvían a certificarse en cada
pasada de la cola.

**Evidencia.** Replay sobre 24 h de historial real: 350 certificaciones, 19 de
trabajo nuevo, 331 repeticiones. Anclado en la fecha de la firma, una diferida
de hace 200 h queda vencida para siempre: 112 corridas sobre 20 agencias, 14,6 h
de worker, y **108 de esas 112 terminaron idénticas** —mismo estado, misma
huella, mismo enumerado—.

**Decisión.** El TTL se mide contra `previous.checked_at`, que es la última
observación real. 72 h normales, 24 h para firmas críticas.

**Descartado.** Anclar en la firma (repite para siempre); no tener TTL (una
diferida valdría eternamente y `baron` pasó de enumerar 0 a 182 sin que
tocáramos nada).

**Impacto medido.** 41,6 h → 22,8 h de worker por día. `NEW_WORK_RATIO` de
5,4 % a 15,7 %.

**Reabrir si.** Aparece una agencia cuya fuente cambia más rápido que su TTL y
eso publica algo falso.

---

## D-002 · Un test que no ejecuta la rama real no cuenta

**2026-09-16 · aplicado**

**Problema.** El vigilante quedó dos horas fallando en producción con quince
tests en verde.

**Evidencia.** `from scripts.alerta_de_cola import avisar` vivía **adentro** de
la rama que notifica, y todos los tests pasaban `--sin-alerta`, que la saltea.
El `.bat` corre `python scripts\vigilante.py`, así que `sys.path[0]` es
`scripts/` y el import reventaba. Se comprobó: con el bug reintroducido, el
test escrito para atraparlo **seguía pasando**.

**Decisión.** Tres reglas: el import va al tope del módulo; toda herramienta
operativa tiene un test que la corre **como subproceso desde la raíz**; y todo
test crítico se valida reintroduciendo el bug para ver que falla.

**Descartado.** Confiar en que un test "cubre" una línea por estar en el mismo
archivo.

**Reabrir si.** Nunca. Es una regla de método, no una decisión técnica.

---

## D-003 · Persistir el estado es obligatorio; notificar es best effort

**2026-09-16 · aplicado**

**Problema.** Un `ModuleNotFoundError` al notificar dejó el archivo de estado
congelado dos horas, con la cola parada.

**Decisión.** Orden fijo: detectar → escribir estado → registrar evento →
intentar notificar. La notificación va envuelta; si falla, se anota el error en
el estado y **`last_alert_at` NO se toca**, para que el próximo chequeo
reintente en vez de creer que ya avisó.

**Reabrir si.** Nunca.

---

## D-004 · Host compartido no es portal

**2026-09-16 · aplicado**

**Problema.** Siete agencias pararon la cola porque su "web" declarada era un
perfil de portal. La tentación era clasificar por host compartido.

**Evidencia.** Ese atajo es falso en las dos direcciones:

- `century21.com.ar/agencias/x` comparte host con decenas y **es** la página
  de su oficina;
- `aimaropropiedades.tuinmobiliaria.com.ar` comparte dominio registrable con
  otras tres y **es el sitio de AIMARO** —su título dice "AIMARO PROPIEDADES"
  y no nombra a ninguna otra—. `tuinmobiliaria.com.ar` es un proveedor
  white-label, no un marketplace. Escribiendo el clasificador caí en esto y las
  cuatro quedaron marcadas como portales.

**Decisión.** Se clasifica por **ruta** primero —`/inmobiliarias/<slug>` en un
host ajeno es un perfil de terceros—, y la comparación del nombre va contra el
**host entero, subdominio incluido**. Host compartido manda a `IDENTITY_REVIEW`,
no condena.

**Impacto medido.** 7 fuentes corregidas, **4.007 propiedades ajenas** que
dejan de enumerarse. Cero huellas cambiadas.

**Reabrir si.** Aparece un proveedor white-label que NO pone el nombre de la
agencia en el subdominio.

---

## D-005 · Una señal en el 100 % de las fichas suele ser del sitio, no de la propiedad

**2026-09-15 · aplicado al ranking, el arreglo del patrón sigue pendiente**

**Problema.** El ranking de campos decía 3.992 recuperables.

**Evidencia.** El patrón de `ambientes` del certificador no exige límite de
palabra y encuentra `ambiente 1` **adentro de MONOambiente**, que es una opción
de menú presente en todas las fichas del sitio. Verificado descargando una
ficha de cada agencia: blanco 1.089, bartolelli 28, cuini 16.

**Decisión.** Esas tres se descuentan y se dice. El arreglo del patrón —un
`\b`— toca `shared/certifier` y espera ventana.

**Descartado.** Descontar por la proporción sola: `espina propiedades` también
da 100 % y su `Ambientes 2` **es** un atributo real. La proporción es indicio,
no prueba.

**Impacto.** 3.992 → 2.860 recuperables.

**Reabrir si.** Se audita el resto de los campos con el mismo criterio y
aparecen más.

---

## D-006 · Un STOP nuevo se alerta, no se reinicia

**2026-09-16 · aplicado**

**Evidencia.** `fenix`, `building` y `benjamin ferreyra` demostraron que el
paro estaba protegiendo de un defecto real: `building` publicaba **220 archivos
JPG como propiedades**.

**Decisión.** El vigilante nunca relanza. Alerta y espera diagnóstico. Hay un
test que falla si el script llega a lanzar o matar un proceso.

**Reabrir si.** Nunca sin evidencia de que una clase de STOP es siempre
transitoria.

---

## D-007 · Dos vías a la misma agencia no se suman

**2026-09-15 · aplicado**

**Problema.** `cristina pozzobon` aparecía con 9 propiedades recuperables por
forma de URL y 80 por sitemap de taxonomías.

**Decisión.** Son rutas alternativas al mismo inventario, no arreglos
aditivos. El ranking descuenta el solapamiento y lo dice.

**Reabrir si.** Se demuestra que las dos vías alcanzan conjuntos distintos.

---

## D-008 · La forma `/<slug>` a secas no sirve como patrón de ficha

**2026-09-15 · aplicado**

**Evidencia.** Probada en `crestale`, devolvía 62 urls que son **páginas de
categoría** —`/venta-propiedades-rosario`, título "Propiedades en venta en
Rosario", ocho precios distintos en la misma página—.

**Decisión.** Sólo `/<slug-con-id>`, que exige un id numérico. `bottai` da 328
fichas reales con esa forma; `crestale` queda afuera.

**Reabrir si.** Aparece un sitio cuyas fichas no tienen id en la url y cuyo
catálogo se puede separar por otra evidencia.
