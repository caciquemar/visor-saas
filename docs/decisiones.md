# Decisiones

Una entrada por decisión, la más nueva arriba. Qué se decidió, por qué y qué se descartó.

## 2026-10-05 · Separación entre talleres: una sola capa que falla cerrada
Todo modelo con datos de un taller hereda de `DatoDeTaller` (`app/talleres/separacion.py`). Su manager filtra por el
taller del contexto (`ContextVar`, que pone el middleware en cada pedido a `/<taller>/…`, o `con_taller()` en tareas).
El filtro está en toda consulta y el taller se lee al armar el SQL: sin taller, la consulta falla (`SinTaller`) en vez
de traer todo, y un queryset armado al importar (los de los `ModelForm`) usa el taller del pedido. Al guardar se
revisa que el dato y sus FK sean del taller actual. La única salida sin filtro es `sin_filtro`, permitida solo en los
archivos de `ARCHIVOS_CON_SIN_FILTRO`. Los archivos van a `talleres/<id>/…` y se entregan solo por
`abrir_de_taller()`. Pruebas de guardia obligan a que los modelos nuevos hereden y a que ninguna dirección nueva
quede sin login. Un taller ajeno da 404, igual que uno inexistente.
Descartado: filtrar a mano en cada vista (regla 1); una base o un esquema por taller (demasiado para este tamaño);
row-level security de PostgreSQL (buena segunda barrera, queda para la ficha 07: en la PC se usa SQLite).

## 2026-10-05 · Ingreso: mail y contraseña; armadores sin mail, con PIN
Dueño y oficina entran con mail y contraseña (con "me olvidé la contraseña" por mail). La invitación llega por mail
y sirve 7 días, una sola vez. Descartado: link mágico (si el mail tarda o va a spam, no se puede entrar).
Armadores e instaladores pueden existir sin mail: los da de alta el dueño o la oficina con nombre y PIN (4 a 6
números). El PIN se usa desde **cualquier celular** en `/<taller>/pin/`, eligiendo el nombre de una lista (los
nombres de armadores e instaladores se ven sin sesión: lo asumimos). Por eso el bloqueo es duro: 15 minutos cada 5
fallos, bloqueo hasta que lo destrabe el dueño o la oficina a los 10, y 20 fallos por hora por IP y taller. La sesión
de PIN dura 12 horas, sirve solo en ese taller y no entra a Equipo. Descartado: habilitar solo celulares del taller.

## 2026-10-05 · Usuario propio con mail
`usuarios.Usuario` (`AUTH_USER_MODEL`) entra con mail; el mail es opcional para los que usan PIN. Un usuario puede
estar en varios talleres (`Membresia`, con rol dueño, oficina, armador o instalador). La administración de Django es
solo para el equipo del servicio; los dueños manejan su gente en *Equipo*.

## 2026-10-04 · Muestras con nombres reales en el repo privado
Martín decidió subir las muestras de `muestras/` tal como salen de Polyboard, con los nombres de los clientes,
porque el repo es privado. Descartado por ahora: re-exportarlas con nombres inventados (lleva tiempo) o dejarlas
fuera de git (las pruebas no correrían en otra PC). Si el repo se comparte o se hace público, se anonimizan antes.

## 2026-10-04 · Django 5.2 LTS
Versión con soporte largo (hasta abril de 2028) y compatible con Python 3.14. Descartado: Django 6.1 (más nueva,
pero con soporte más corto). Pasar a 6.2 LTS cuando salga.

## 2026-10-04 · Cola de tareas: Huey
Las conversiones van a una cola con Huey. En el servidor usa Redis; en la PC puede correr en el mismo proceso
(`HUEY_INMEDIATO=1`) o guardar la cola en un SQLite, sin Redis ni Docker. Descartado: RQ, porque necesita `fork` y
no corre en Windows, que es donde se desarrolla. Celery es demasiado para el tamaño del proyecto.

## 2026-10-04 · Archivos: django-storages con Cloudflare R2
`ALMACENAMIENTO=r2` usa `storages.backends.s3.S3Storage` contra el endpoint de R2, con archivos privados y URL
firmadas. En la PC, `ALMACENAMIENTO=local` guarda en `datos/archivos/`. El resto del código usa el almacenamiento
de Django y no sabe cuál es.

## 2026-10-04 · Conversor: un solo módulo, cambios mínimos
`conversor/polyboard_a_app.py` sigue siendo un solo archivo, con `convertir()` y `ErrorConversion` agregados, para
que los arreglos se puedan llevar fácil al visor actual de Nord Good. El código del link del cliente lo decide
quien llama (la app lo guardará en la base; la línea de comandos sigue usando `.clientes.json`).

## 2026-10-04 · Zicar como módulo privado de Nord Good
El conversor Polyboard → Zicar no se vende. Se integra como módulo que se prende por taller y solo está prendido
para Nord Good. Su código queda en su propio repo privado.

## 2026-10-04 · Marca propia del servicio
El servicio no usa la marca Nord Good. Cada taller pone su logo y colores en el link del cliente.

## 2026-10-04 · Conversión en el servidor
El taller sube DXF + .ocp desde el navegador y el servidor convierte. Descartado por ahora: programa de escritorio
para cada taller (instalación y versiones distintas). Puede sumarse después como "subidor".

## 2026-10-04 · Stack inicial
Django + PostgreSQL + cola de tareas + Cloudflare R2, en un VPS detrás de Cloudflare. Descartado: el NAS de la casa
para clientes pagos (cortes de luz e internet, sin respaldo de uptime).
