# Decisiones

Una entrada por decisión, la más nueva arriba. Qué se decidió, por qué y qué se descartó.

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
