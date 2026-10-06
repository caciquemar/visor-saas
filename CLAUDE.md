# Visor SaaS — instrucciones para Claude

Servicio por suscripción para talleres de muebles que diseñan en Polyboard: suben el proyecto,
el taller lo arma escaneando las piezas, el cliente final lo ve en 3D y en realidad aumentada,
y los trabajos pendientes quedan registrados con fotos.

- Plan de negocio y arquitectura: https://claude.ai/artifact/FjcEFqkNyJpgcm2f5R5VRw (resumen en `docs/plan.md`)
- Nombre comercial: **todavía sin definir**. En el código usar `visor` como nombre interno; no usar "Nord Good" en el producto.
- Dueño: Martín (Nord Good, fábrica de muebles en melamina). Nord Good es el primer taller cliente y el único con el módulo Zicar.

## Cómo trabajamos

- Cada sesión de Claude Code toma **una** ficha de `docs/sesiones/` (ver el índice en `docs/sesiones/README.md`).
  Leé la ficha completa antes de empezar. En tareas grandes, empezá en modo plan y esperá aprobación.
- No hagas trabajo de otra ficha "de paso". Si aparece algo, anotalo en la sección *Pendientes* de esta página.
- Al terminar una sesión:
  1. Pruebas pasando (`docs/sesiones/README.md` dice cómo correrlas, una vez que exista la app).
  2. Actualizar *Estado* abajo y, si se tomó una decisión, agregarla a `docs/decisiones.md`.
  3. Commit con mensaje en español que diga qué cambia para el usuario.
- Idioma: todo en español rioplatense (textos de pantalla, comentarios, commits, documentación). Los nombres de
  código siguen el estilo del visor actual: en español (`proyecto`, `pieza`, `taller`, `trabajo`).

## Stack

- Python (Martín tiene 3.14 en la PC). App web en **Django** con **PostgreSQL** (SQLite solo para pruebas locales rápidas).
- Django 5.2 LTS. Cola de tareas para las conversiones: **Huey** (Redis en el servidor, SQLite o modo inmediato en la PC).
- Archivos (proyectos convertidos, texturas, GLB, fotos, ZIP) en **Cloudflare R2** vía API S3; en local, carpeta del disco.
- Visor: `visor/index.html`, JavaScript sin framework. Se adapta lo mínimo: hoy pide `data/…` y `api/…` con rutas relativas.
- Cobro: Mercado Pago Suscripciones (preapproval) + webhooks. Factura electrónica ARCA.
- Producción: VPS en la nube detrás de Cloudflare. **No** el NAS de la casa.

## Estructura

```
conversor/        paquete: from conversor import convertir, ErrorConversion (polyboard_a_app.py, base armado/armado @59fc33b)
visor/            index.html (copia del visor actual) -> se adapta a multi-taller
referencia/       api.py y nginx.conf actuales, solo como referencia (no se ejecutan)
muestras/         proyectos reales de Polyboard para pruebas, uno por carpeta (ver muestras/README.md)
docs/             plan, decisiones y fichas de cada sesión
negocio/claude-ai instrucciones y archivos para el Proyecto de claude.ai (negocio, marca, entrevistas)
app/              proyecto Django: config/ (settings y urls), usuarios/ (Usuario), talleres/ (Taller, Membresia,
                  Invitacion, separación entre talleres, PIN, Equipo), proyectos/ (Proyecto, Version, Original,
                  Material; subida, cola de conversión en proceso aparte, biblioteca de texturas), templates/
tests/            pytest: tests/conversor y tests/app (tests/app/taller_prueba: modelo Nota solo para pruebas)
datos/            (no va a git) base SQLite, cola y archivos en desarrollo
```

## Cómo correrlo

- Arrancar: `.\iniciar.ps1` (crea `.venv`, instala, copia `.env`, migra y levanta en http://127.0.0.1:8000/admin/).
  En la PC los mails (invitaciones) quedan como archivos en `datos/mails/`.
- Pruebas: `.venv\Scripts\python -m pytest` (todas, unos 8 minutos) o `-m "not muestras"` (rápidas).
- Si un cambio del conversor cambia el resultado a propósito: `pytest -m muestras --actualizar-esperados` y revisar
  el `git diff` de `muestras/*/esperado/resumen.json`.
- Configuración solo por `.env` (ver `.env.example`). Las pruebas usan `config.settings_pruebas`, que no lee
  valores del `.env` de la PC.
- Conversiones: con `HUEY_INMEDIATO=1` (la PC) se convierten dentro del mismo pedido (la subida tarda lo que la
  conversión). Para ver la cola como en el servidor: `HUEY_INMEDIATO=0` y en otra consola
  `.venv\Scripts\python app\manage.py run_huey`.
- Sin Docker: SQLite y Huey inmediato. Con Docker: `docker compose up -d` + `DATABASE_URL`/`REDIS_URL` en `.env`.

## Reglas que no se negocian

1. **Separación entre talleres.** Toda consulta y todo archivo se filtra por el taller de la sesión, desde una sola
   capa (manager/queryset o middleware), nunca a mano en cada vista. Cada modelo con datos de un taller tiene `taller`.
   Hay pruebas que intentan leer y escribir datos de otro taller y deben fallar.
   En la práctica: **todo modelo nuevo con datos de un taller hereda de `DatoDeTaller`**
   (`app/talleres/separacion.py`), los archivos usan `ruta_de_taller` / `abrir_de_taller`
   (`app/talleres/archivos.py`), las tareas de la cola usan `@tarea_de_taller`, y nunca se usa `sin_filtro` fuera de
   los archivos permitidos. `tests/app/test_guardianes.py` falla si algo de esto se saltea. Cada ficha que agregue
   modelos suma sus pruebas de cruce en `tests/app/test_separacion.py` (o al lado).
2. **Todo pide login** salvo el link del cliente (`/c/<código>`), que muestra solo la versión sin datos de taller,
   y la página de venta.
3. **Módulos por taller.** Las funciones extra se prenden por taller (`taller_modulo`). El módulo **Zicar** está
   habilitado solo para Nord Good: para los demás no se muestra nada y el servidor rechaza el pedido.
   El código de Zicar vive fuera de este repo (`C:\Users\Asus\GitHub\polyboard\Polyboard_to_zicar`).
4. **Secretos** (claves de Mercado Pago, R2, base de datos) solo en `.env`, nunca en el repo.
5. **Muestras:** por decisión de Martín (2026-10-04) van al repo con sus nombres reales porque el repo es
   **privado**. Si el repo se comparte con alguien de afuera o se hace público, antes hay que anonimizarlas
   (re-exportar desde Polyboard con otro nombre de proyecto y regenerar `esperado/`).
6. **No tocar el visor en producción de Nord Good** (`C:\Users\Asus\GitHub\polyboard\armado\armado`, NAS,
   visor.nordgood.com.ar) salvo que la ficha lo diga (solo la ficha 00).
7. Los datos de un taller nunca se borran sin aviso: suscripción vencida -> solo lectura -> 90 días -> borrado avisado.

## Relación con el visor actual

El visor de Nord Good sigue funcionando en el NAS hasta que este servicio esté probado. Si se corrige algo del
conversor acá que también afecta al visor actual, avisar a Martín para llevarlo allá (no hacerlo automáticamente).

## Estado

- 2026-10-04: estructura inicial creada. La 00 (seguridad del visor actual) quedó postergada por decisión de Martín.
- 2026-10-04: **ficha 01 hecha.** Django 5.2 en `app/` (solo administración), Huey y almacenamiento local/R2
  configurados por `.env`, conversor importable (`convertir()` + `ErrorConversion`, sin `sys.exit` ni URL de
  Nord Good; la línea de comandos sigue igual), 7 muestras (3 OptiCut viejo, 4 nuevo) con resultado guardado y
  pruebas. El resultado del conversor es idéntico al del visor actual. Próxima: 02.
- 2026-10-05: **ficha 02 hecha.** Usuario propio (entra con mail), talleres en `/<taller>/`, roles (dueño, oficina,
  armador, instalador), invitaciones por mail, alta de armadores con PIN y entrada con PIN desde cualquier celular,
  pantalla Equipo, crear taller en la administración. Separación entre talleres en una sola capa
  (`talleres/separacion.py` + `TallerMiddleware`) con pruebas de cruce (lectura, escritura, archivos, tareas, PIN) y
  pruebas de guardia. Se rehízo la base de la PC (`datos/dev.sqlite3`): hay que volver a crear el superusuario.
  Próxima: 03.
- 2026-10-06: **ficha 03 hecha.** Pantalla para subir proyecto o versión nueva (arrastrar DXF + uno o varios .ocp,
  barra de progreso, control de tipo, tamaño y contenido), versiones con "Usar esta versión" y "Volver a convertir",
  conversión en la cola en un proceso aparte (`proyectos/proceso.py`) con límite de tiempo (y de memoria en Linux),
  estados en cola / convirtiendo / listo / error con el mensaje del conversor, biblioteca de materiales del taller
  (las texturas que faltan aparecen solas y se suben una vez). El conversor no se tocó. Las 7 muestras subidas como
  desde el navegador quedan en "listo" (`pytest -m muestras tests/app/test_proyectos.py`). Próxima: 04.
- 2026-10-06: **ajustes a la 03 pedidos por Martín.** (1) El error de DXF ilegible ya no muestra el texto técnico de
  ezdxf. (2) Tableros y cantos no se mezclan: el conversor lee de qué tipo es cada material del .ocp
  (`materiales_del_ocp`), `materiales.json` acepta `{"tableros": …, "cantos": …}`, el proyecto convertido trae
  `cantos` aparte de `materiales`, y la biblioteca del taller tiene tablero y canto por separado aunque se llamen igual.
  El visor actual de Nord Good queda sin estos cambios por decisión de Martín.

## Pendientes

- Definir nombre comercial y dominio (Proyecto de claude.ai, ver `negocio/claude-ai`).
- Ficha 07: row-level security de PostgreSQL como segunda barrera entre talleres; caché compartida (Redis) para el
  límite de intentos de PIN por IP (hoy es por proceso); tomar la IP de `CF-Connecting-IP` detrás de Cloudflare
  (`talleres/vistas.py`, `ip_de`); configurar `EMAIL_URL` (SMTP) y `DOMINIO_APP`.
- Visor actual de Nord Good: **queda sin modificar por ahora** (decisión de Martín, 2026-10-06). No se le llevan los
  cambios del conversor del 2026-10-06 (mensaje de DXF dañado y tableros/cantos separados) hasta que él lo pida.
  Sigue andando igual: `materiales` conserva los cantos que no se llaman como un tablero.
- Ficha 04: sumar `/c/<código>` a las direcciones públicas de `tests/app/test_guardianes.py`. El visor lee
  `Version.archivo_proyecto` (siempre `.../resultado/proyecto.json`) de `proyecto.version_actual`; el link del cliente
  usa `Proyecto.codigo_cliente` (`.../resultado/clientes/<código>.json` y sus `.glb`). Las texturas quedan en
  `.../resultado/texturas/`. **Los cantos se buscan en `cantos`** (tablero y canto pueden llamarse igual);
  `materiales` es solo para tableros.
- Ficha 07: en el servidor el consumidor de Huey (`run_huey`) tiene que correr como servicio; el límite de memoria
  de la conversión (`CONVERSION_MEMORIA_MB`) solo funciona en Linux. Si Cloudflare queda en plan pago, se puede
  subir `MAX_DXF_MB`. Las versiones que quedan "en cola" con el consumidor caído no se marcan solas (sí las que
  quedan "convirtiendo").
- Tipo de material en el .ocp: la regla (primera clase = tableros, segunda = cantos, y después una marca por clase)
  se dedujo de las 7 muestras. Si un .ocp nuevo no la cumple, sus materiales van a los dos tipos como antes y
  `tests/conversor/test_texturas.py::test_todas_las_muestras_se_separan` lo detecta al sumarlo a `muestras/`.
- Muestras que faltan: mueble suelto (proyecto vacío en el .ocp) y proyecto dividido en varios .ocp.
- Instalar Docker Desktop para probar con PostgreSQL + Redis antes de la ficha 07.
- Pasar a Django 6.2 LTS cuando salga (abril de 2027); 5.2 tiene soporte hasta abril de 2028.
- Conversor, para revisar con Martín (no se tocó en la 01; si se arregla, avisar para llevarlo al visor actual):
  en *Rack florencia* el mueble "escritorio flotante\`1cajon con ajuste izq" queda sin vincular (10 avisos "Sin
  panel 3D"): en el .ocp el nombre tiene un acento grave (\`) y en el DXF aparece como `_`. *cocina grondona*
  tiene 8 avisos. Ver `muestras/*/esperado/resumen.json`.
