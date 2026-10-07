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
- Producción: VPS en la nube detrás de Cloudflare (ficha 07b, antes de cobrar). Mientras los pilotos son gratis,
  el NAS de la casa (ficha 07a). Imagen de Docker armada por GitHub Actions, mismo compose en los dos: ver
  `docs/operacion.md`.

## Estructura

```
conversor/        paquete: from conversor import convertir, ErrorConversion (polyboard_a_app.py, base armado/armado @59fc33b)
visor/            index.html (copia del visor actual) -> se adapta a multi-taller
referencia/       api.py y nginx.conf actuales, solo como referencia (no se ejecutan)
muestras/         proyectos reales de Polyboard para pruebas, uno por carpeta (ver muestras/README.md)
docs/             plan, decisiones y fichas de cada sesión
negocio/claude-ai instrucciones y archivos para el Proyecto de claude.ai (negocio, marca, entrevistas)
app/              proyecto Django: config/ (settings y urls), usuarios/ (Usuario), talleres/ (Taller, Membresia,
                  Invitacion, separación entre talleres, PIN, Equipo, Marca), proyectos/ (Proyecto, Version, Original,
                  Material, LinkCliente; subida, cola de conversión en proceso aparte, biblioteca de texturas,
                  visor.py: el visor y el link del cliente), trabajos/ (Trabajo, CambioDeEstado, Foto; api.py: la
                  API de trabajos del visor; vistas.py: la pantalla Trabajos), modulos/ (Modulo, TallerModulo;
                  registro.py: ganchos y con_modulo; zicar/: ResultadoZicar, subida, tarea y descarga), servicio/
                  (sin modelos: /salud/, latido de la cola, copias de la base y sus comandos), templates/
                  talleres/rls.py: segunda barrera entre talleres en PostgreSQL (row-level security)
Dockerfile        imagen del servidor; docker/: arranque (web, cola, preparar) y preparar_base.py
despliegue/       compose.yml del servidor (NAS y VPS) y los .env de ejemplo
.github/          workflows/imagen.yml: pruebas (SQLite y PostgreSQL) y, con etiqueta v*, la imagen en ghcr.io
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
- Pruebas con PostgreSQL (marca `postgres`: row-level security y copias de verdad; se saltean con SQLite): poner
  `PRUEBAS_DATABASE_URL=postgres://visor:visor@host:puerto/visor` con un usuario **que no sea superusuario** (con
  CREATEDB) y `pg_dump`/`psql` en el PATH. En GitHub corren solas. En la PC sin Docker se puede usar el PostgreSQL
  portátil del paquete `pgserver` (Python 3.12 con `uv`; le faltan los husos horarios: copiar `tzdata/zoneinfo` a
  `pginstall/share/postgresql/timezone`).
- Servidor: `docs/operacion.md` (instalar, actualizar versión, copias, cortes de luz, mudanza al VPS).
- Módulo Zicar: necesita el paquete `pb2zicar` (repo `Polyboard_to_zicar`, aparte). `iniciar.ps1` lo instala si la
  carpeta está al lado (`..\polyboard\Polyboard_to_zicar`); en el servidor, `pip install -r requirements-zicar.txt`.
  Se prende por taller en la administración (ficha del taller → Módulos). En la PC está prendido en
  `nord-good-prueba` (dueño: el usuario de `datos/usuario_de_prueba.txt`).

## Reglas que no se negocian

1. **Separación entre talleres.** Toda consulta y todo archivo se filtra por el taller de la sesión, desde una sola
   capa (manager/queryset o middleware), nunca a mano en cada vista. Cada modelo con datos de un taller tiene `taller`.
   Hay pruebas que intentan leer y escribir datos de otro taller y deben fallar.
   En la práctica: **todo modelo nuevo con datos de un taller hereda de `DatoDeTaller`**
   (`app/talleres/separacion.py`), los archivos usan `ruta_de_taller` / `abrir_de_taller`
   (`app/talleres/archivos.py`), las tareas de la cola usan `@tarea_de_taller`, y nunca se usa `sin_filtro` fuera de
   los archivos permitidos. `tests/app/test_guardianes.py` falla si algo de esto se saltea. En PostgreSQL además la
   base misma filtra por taller (`talleres/rls.py`, se aplica sola al migrar). Cada ficha que agregue
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
- 2026-10-06: **ficha 04 hecha.** El visor se abre en `/<taller>/visor/` (con login) y lee los proyectos de la base:
  la app atiende las mismas rutas relativas `data/…` debajo de la página (`proyectos/visor.py`), así `index.html`
  cambió poco (configuración en `window.VISOR`, texturas relativas a la carpeta del proyecto, lista por posición y
  `?p=<id>`, sin "Nord Good", trabajos ocultos hasta la 05, íconos genéricos en `proyectos/static/visor/`).
  Link del cliente `/c/<código>/` (`LinkCliente`: código de 128 bits, vence a 30/90/365 días o nunca, se anula,
  cuenta visitas sin contar al taller) creado desde la pantalla del proyecto por dueño u oficina; el middleware toma el
  taller del link vigente y solo sirve `cliente.json`, sus GLB, texturas y el logo (nunca `proyecto.json`). Marca del
  taller (logo PNG/JPG/WEBP y color oscuro) en `/<taller>/marca/`, solo el dueño; pie "hecho con Visor"
  (`MARCA_SERVICIO`, `MARCA_URL`). Probado en el navegador integrado: Rack florencia igual que en
  visor.nordgood.com.ar (70 paneles, misma ficha; cambia solo la foto del guatambú de la biblioteca de prueba), en
  formato celular el escáner pide la cámara y el número a mano anda, el link abre sin sesión con la marca y deja de
  andar al anularlo. Próxima: 05.
- 2026-10-06: **lados de las piezas (pedido de Martín).** Lado sin canto: color MDF que el taller elige en Materiales
  (`Taller.color_sin_canto`, `#B58F63` por defecto). Canto que se llama como su tablero (sin mayúsculas ni acentos):
  igual que el tablero, con su textura. Otro canto: su color, buscado en `cantos`. Vale en el visor 3D, la ficha de la
  pieza y los GLB de realidad aumentada del conversor (`glb_ar(..., sin_canto=)`, `convertir(sin_canto=)`,
  `--sin-canto`); por eso cambiaron las huellas de los GLB en `muestras/*/esperado/resumen.json` (el resto es igual).
  Si el taller cambia el color, la AR lo toma al "Volver a convertir".
- 2026-10-07: **ficha 05 hecha.** Trabajos a realizar dentro de la app (`trabajos/`): `Trabajo` (proyecto, texto,
  piezas, muebles, estado pendiente → en proceso → hecho → instalado, autor, para quién, fecha límite, quién y cuándo
  de cada paso con la misma regla que `referencia/api_actual.py`), `CambioDeEstado` (historial que solo suma) y `Foto`
  (almacenamiento del taller, 12 MB, JPG/PNG/WEBP comprobado con Pillow). API con las mismas rutas en
  `/<taller>/visor/api/` (`trabajos/api.py`) y las mismas respuestas, salvo: el proyecto va por id, "Para quién" es un
  miembro activo del taller y autor/quién salen de la sesión. Cualquier miembro anota, cambia el estado y sube fotos;
  editar, borrar y quitar fotos ajenas es del autor, el dueño o la oficina. Límites por plan preparados
  (`talleres/limites.py`, hoy todo permitido). `index.html`: token CSRF, proyecto por id, "Para quién" como lista,
  sin "Tu nombre", Editar/Borrar solo si `puede_editar`. Probado en el navegador integrado con `taller-prueba`
  (dueño con mail y armador con PIN: anotar, foto, estados, permisos). Próxima: 06.
- 2026-10-07: **agregado a la 05, pedido por Martín.** Pantalla "Trabajos" del taller (`/<taller>/trabajos/`,
  `trabajos/vistas.py`): todos los trabajos de todos los proyectos, vencidos primero, con filtros (para quién, "para
  mí", proyecto, estado, ver instalados; armadores e instaladores entran con "para mí"), ✓ para pasar al estado
  siguiente y salto al visor con el trabajo abierto (`?p=<proyecto>&t=<trabajo>`). En el detalle del trabajo del
  visor, "Agregar foto" para cualquiera del taller. Arreglo del visor: con un panel que tapa toda el área del 3D
  (pantalla baja) la cámara quedaba en NaN y el dibujo no volvía; `tamano()` ahora espera a que el área tenga tamaño.
- 2026-10-06: **fichas 12 a 14 nuevas** (decisión de Martín): etiquetas con QR por pieza y por mueble, avance por
  etapas con fin de fabricación y control de carga, probador de colores en el link del cliente. Orden sugerido en
  `docs/sesiones/README.md`.

- 2026-10-07: **ficha 06 hecha.** Módulos por taller (`modulos/`): catálogo `Modulo` + `TallerModulo` (prendido,
  configuración JSON), prendidos desde la ficha del taller en la administración; `registro.py` con los ganchos (campo
  en la subida, paso extra en la conversión, HTML en cada versión) y `con_modulo` (404 si no está prendido, antes que
  el rol). Módulo Zicar (`modulos/zicar/`): la carpeta del postprocesador se sube como ZIP o arrastrando la carpeta
  (la página arma el ZIP), se revisa (rutas, cantidad, tamaño, que tenga DXF), se convierte con `pb2zicar` en su
  propia tarea y proceso aparte, y queda "Descargar Zicar" (`<carpeta>_zicar.zip`) con la lista de piezas para
  revisar a mano; solo dueño y oficina. `Polyboard_to_zicar` ahora es instalable (`pyproject.toml`, etiqueta v1.0.0).
  Probado con dos proyectos reales de Nord Good (*Rack florencia v2*, subido como ZIP del Explorador, y *Kogan2*, con
  el ZIP armado por el JavaScript de la página): el ZIP descargado es igual byte a byte a lo que genera hoy "Convertir
  proyecto" (`run.py`); `taller-prueba` no ve nada de Zicar y la descarga armada a mano da 404. Próxima: 12.
- 2026-10-07: **arreglo del conversor (pedido de Martín).** Muros, suelos y techos renombrados en Polyboard
  ("M lav", "Suelo 1", "ventana"…) se tomaban como muebles o herrajes y en el visor tapaban los muebles con un bloque
  macizo. Ahora un bloque de primer nivel sin sub-bloques (sin piezas adentro) es muro, se llame como se llame.
  Cambiaron `esperado/` de Aguilar, argerich, grondona y Kogan (solo pasan objetos de la obra a `muros`). Ya está
  también en el visor del NAS (polyboard f62ff14, grondona reconvertida).
- 2026-10-07: **ficha 07a, parte de código hecha; falta instalar en el NAS** (pasos de Martín en
  `docs/operacion.md`). El programa llega al NAS como imagen de Docker privada que arma GitHub Actions con cada
  etiqueta `v*`, después de pasar las pruebas con SQLite y con PostgreSQL (`.github/workflows/imagen.yml`; Zicar se
  instala con el secreto `ZICAR_TOKEN`, que no queda en la imagen ni en el NAS). `despliegue/compose.yml`, el mismo
  para NAS y VPS: web (gunicorn), cola (Huey, una conversión a la vez), PostgreSQL 17, Redis, y `preparar`, que crea
  el usuario de la base sin superusuario. Puerto 8090, nombres `visor-saas-*`: no toca `visor-armado`. Dirección de
  prueba: subdominio de nordgood.com.ar en el túnel que ya existe. En la app: whitenoise para los estáticos, caché en
  Redis (intentos de PIN entre procesos), `ip_de` con `CF-Connecting-IP` (`DETRAS_DE_CLOUDFLARE=1`), Sentry,
  `/salud/` para UptimeRobot (base, Redis y latido de la cola), memoria pico de cada conversión en el log, copias
  diarias de la base a otro bucket de R2 (`servicio/copias.py`, comandos `copia_base` y `restaurar_copia`, como
  INSERT porque COPY no anda con RLS) y **row-level security** en PostgreSQL (`talleres/rls.py`): política
  `por_taller` forzada en toda tabla de `DatoDeTaller`, la variable `visor.taller` sale de `taller_actual`. Con RLS,
  desde A las filas de B ni se ven: se ajustaron 4 pruebas de `test_separacion.py` que buscaban el objeto de B con
  `sin_filtro` dentro del contexto de A. Probado en la PC con PostgreSQL 16 portátil: todas las pruebas rápidas
  (también copia y restauración de verdad) y las 7 muestras. La imagen y el compose todavía no se probaron (no hay
  Docker en la PC): se prueban en GitHub y al instalar.

## Pendientes

- **Ficha 07a, instalación** (Martín, con `docs/operacion.md`): medir la subida de internet; tokens de GitHub;
  `git push` de visor-saas y de las etiquetas de `Polyboard_to_zicar` (`v1.0.0`) y primera etiqueta `v0.7.0`;
  R2 (dos buckets, CORS); dataset y carpeta compartida en TrueNAS; los dos `.env`; instalar el YAML; hostname en el
  túnel; superusuario y taller; prender Zicar a Nord Good; Sentry, UptimeRobot y Brevo (registros DNS). Después
  verificar lo de "Listo cuando" de la ficha, medir la memoria con *cocina grondona* y anotarla en
  `docs/operacion.md` (ajustar `CONVERSION_MEMORIA_MB` y el `mem_limit` de `cola`), y probar una restauración.
- Ficha 07a, a confirmar al instalar: cómo guarda TrueNAS 25.04 la clave del registro privado (pantalla *Docker
  Registries* o `docker login` desde System → Shell), y que cloudflared mande `X-Forwarded-Proto: https` (si la página
  entra en un bucle de redirecciones, poner `SECURE_SSL_REDIRECT=0`: Cloudflare ya fuerza HTTPS).
- RLS: sin taller en el contexto (administración, entrar, migraciones) la base no filtra; ahí manda solo la primera
  barrera. Es a propósito (la administración ve todo); si algún día hace falta, se puede sumar una variable aparte
  para "sin filtro" y que sin nada no se vea nada.

- Definir nombre comercial y dominio (Proyecto de claude.ai, ver `negocio/claude-ai`).
- Ficha 11: al migrar Nord Good, "Convertir proyecto" de la PC sigue haciendo la Zicar; cuando Martín use la app,
  se puede dejar de usar (no se tocó la PC).
- Visor actual de Nord Good: **queda sin modificar por ahora** (decisión de Martín, 2026-10-06). No se le llevan los
  cambios del conversor del 2026-10-06 (mensaje de DXF dañado y tableros/cantos separados) hasta que él lo pida.
  Sigue andando igual: `materiales` conserva los cantos que no se llaman como un tablero.
- Conversor y visor actual de Nord Good: la regla de los lados (sin canto MDF, canto igual al tablero) cambió
  `glb_ar` en este repo; el visor del NAS no la tiene. Va con el resto de los cambios al NAS, que quedan para el final (decisión de Martín, 2026-10-06).
- Lados con un canto de otro nombre: usan el color que trae Polyboard para ese canto, que a veces es de señalización
  (`negro` = `#408080`, `blanco` = `#FFFF31`). Revisar con Martín si molesta.
- Visor actual de Nord Good: tiene el mismo problema de la cámara en NaN con el panel de trabajos en una pantalla
  baja (arreglado acá en `tamano()`/`encuadrar()` de `index.html`); va con el resto de los cambios al NAS.
- Ficha 08: completar `talleres/limites.py` (`trabajos`, `fotos_de_trabajos`); el plan Taller de `docs/plan.md` no
  dice si tiene trabajos sin fotos o ningún trabajo. Con `trabajos` apagado se ven pero no se cambian.
- Ficha 11: al pasar `trabajos.db` de Nord Good, `autor`/`asignado`/`*_por` son texto libre: hay que emparejarlos con
  los usuarios del taller (o dejarlos vacíos) y el proyecto va por nombre (puede haber dos iguales).
- Formulario de materiales (ficha 03): con una textura ya cargada, guardar solo el ancho o el color falla con "Subí la
  imagen en JPG, PNG o WEBP" (`FormMaterial.clean_textura` revisa el archivo que ya estaba). Mismo arreglo que
  `FormMarca.clean_logo`: revisar solo si es un `UploadedFile`.
- Probar en un celular de verdad, por HTTPS (en el NAS, al instalar la 07a): escanear una etiqueta y abrir la
  realidad aumentada desde el link del cliente, y que texturas y GLB lleguen de R2 sin error de CORS. En el navegador
  integrado la cámara está bloqueada y el modelo de AR no termina de cargar (tampoco el de visor.nordgood.com.ar).
- Si Cloudflare queda en plan pago, se puede subir `MAX_DXF_MB`. Las versiones que quedan "en cola" con el
  consumidor caído siguen al volver (Redis guarda la cola en disco); las "convirtiendo" se marcan como error.
- Tipo de material en el .ocp: la regla (primera clase = tableros, segunda = cantos, y después una marca por clase)
  se dedujo de las 7 muestras. Si un .ocp nuevo no la cumple, sus materiales van a los dos tipos como antes y
  `tests/conversor/test_texturas.py::test_todas_las_muestras_se_separan` lo detecta al sumarlo a `muestras/`.
- Muestras que faltan: mueble suelto (proyecto vacío en el .ocp) y proyecto dividido en varios .ocp.
- Docker en la PC (opcional): permitiría probar la imagen y el compose antes de subir una versión. Hoy se prueban en
  GitHub Actions y en el NAS.
- Pasar a Django 6.2 LTS cuando salga (abril de 2027); 5.2 tiene soporte hasta abril de 2028.
- Conversor, para revisar con Martín (no se tocó en la 01; si se arregla, avisar para llevarlo al visor actual):
  en *Rack florencia* el mueble "escritorio flotante\`1cajon con ajuste izq" queda sin vincular (10 avisos "Sin
  panel 3D"): en el .ocp el nombre tiene un acento grave (\`) y en el DXF aparece como `_`. *cocina grondona*
  tiene 8 avisos. Ver `muestras/*/esperado/resumen.json`.
