# Decisiones

Una entrada por decisión, la más nueva arriba. Qué se decidió, por qué y qué se descartó.

## 2026-10-07 · El programa llega al servidor como imagen que arma GitHub
Decisión de Martín (ficha 07a). Con cada etiqueta `v*`, GitHub Actions corre las pruebas (SQLite y PostgreSQL) y,
si pasan, arma la imagen y la guarda privada en `ghcr.io/caciquemar/visor-saas`. En el NAS (sin SSH) se actualiza
cambiando el número de versión en el YAML de la app de TrueNAS; volver atrás es poner el número anterior. El token
para instalar Zicar es un secreto de GitHub que se usa solo al armar: no queda en la imagen ni en el NAS. Descartado:
carpeta sincronizada por Nextcloud como el visor actual (instala todo en cada arranque, deja el token en el NAS y una
sincronización a medias rompe la app) y armar la imagen en la PC (hace falta Docker y hacerlo a mano).

## 2026-10-07 · Dirección de prueba de los pilotos: subdominio de nordgood.com.ar
Decisión de Martín (ficha 07a). Mientras no haya dominio de la marca, los pilotos entran por un subdominio de
nordgood.com.ar (`taller.nordgood.com.ar`, elegido por Martín) en el túnel de Cloudflare que ya existe, y los mails salen de `@nordgood.com.ar`.
Es inmediato; la contra es que los pilotos ven "nordgood". Al tener el dominio de la marca se agrega como otro
hostname y se cambia `DOMINIO_APP`. Descartado por ahora: comprar un dominio neutro, o esperar la marca para empezar.

## 2026-10-07 · Row-level security de PostgreSQL como segunda barrera entre talleres
Toda tabla de un `DatoDeTaller` tiene la política `por_taller` forzada (vale también para el dueño de la tabla) y,
antes de cada consulta, la app pone `visor.taller` con el taller del contexto (`talleres/rls.py`). La app entra con
un usuario que no es superusuario (lo crea el servicio `preparar`). Sin taller en el contexto (administración, entrar,
migraciones, copias) la base no filtra y manda la primera barrera: así no hace falta otro camino para la
administración. Las políticas se rehacen después de cada `migrate`, así un modelo nuevo no queda afuera.

## 2026-10-07 · Copias de la base: pg_dump diario a un bucket de R2 aparte
Todos los días a las 4, la cola sube un `pg_dump` a `visor-saas-copias` (30 diarias y 12 mensuales), con una clave de
R2 que solo ve ese bucket. Las filas van como INSERT porque PostgreSQL no deja cargar con COPY tablas con RLS forzada.
`restaurar_copia --base` la carga en una base aparte para probarla sin tocar la de la app. Descartado: copiar la
carpeta de PostgreSQL del NAS (queda en la misma casa y no sirve para mudarse a otra versión de PostgreSQL).

## 2026-10-07 · Pilotos en el NAS, cobro en un VPS
Decisión de Martín. Mientras los pilotos usan el servicio gratis, corre en el NAS de Terrero (TrueNAS, 8 GB de RAM,
compartido con Nextcloud, n8n y el visor de Nord Good) detrás del túnel de Cloudflare: no hay costo de servidor
mientras se valida. Condiciones: el mismo Docker Compose que va a usar el VPS, archivos en R2 (no gastan la subida de
la casa), copia diaria de la base fuera del NAS, límites de memoria y una conversión a la vez. Antes de cobrar
(ficha 08) se muda a un VPS (ficha 07b). Descartado: cobrarles a los talleres con el servicio en la casa (cortes de
luz e internet) y contratar el VPS ya.

## 2026-10-07 · Las luces entre piezas se ven también en el link del cliente
Decisión de Martín (ficha 15). Las cotas internas de luces entre piezas (alto, ancho y profundidad libres de cada
hueco) se muestran en el visor del taller y en el link del cliente. Las distancias de taladros y herrajes quedan solo
para el taller: son datos de fabricación.

## 2026-10-07 · Código de Zicar: paquete instalable desde su repo privado
Decisión de Martín (ficha 06). `Polyboard_to_zicar` sigue en su propio repo privado y ahora tiene `pyproject.toml`
(paquete `pb2zicar`, sin dependencias; el `.bat` y `run.py` siguen igual). Este repo no lo trae: el servidor lo
instala con `pip install -r requirements-zicar.txt`, que fija una etiqueta (`v1.0.0`), usando un token de GitHub de
solo lectura para ese repo que se usa solo al instalar (ficha 07). En la PC, `iniciar.ps1` lo instala desde la carpeta
de al lado (`pip install -e`). La app usa solo `pb2zicar.cli.process_folder`, en un proceso aparte. Si el paquete no
está, el módulo no se activa aunque esté prendido y sus pruebas se saltean.
Descartado: carpeta clonada a mano con la ruta en `.env` (sin versión fija; hay que acordarse de actualizarla) y
submódulo de git (cualquiera que clone este repo necesitaría acceso al otro).

## 2026-10-07 · Módulos por taller: no se ve nada y todo da 404
`modulos.Modulo` es el catálogo (lo crea una migración; uno por módulo con código) y `modulos.TallerModulo` (dato de
taller) dice si está prendido, con configuración en JSON. Se prende en la administración, en la ficha del taller.
`modulos/registro.py` es la única puerta: la app pide los ganchos de los módulos prendidos (campos y HTML de la
subida, guardar lo suyo, paso extra de la conversión, HTML en cada versión) y nunca pregunta por un módulo en
particular. Las direcciones de un módulo llevan `con_modulo`, que responde 404 antes de mirar el rol, igual que una
dirección que no existe; lo que el navegador mande de más con el módulo apagado se ignora.
Módulo Zicar: en la subida, la carpeta del postprocesador como ZIP o arrastrando la carpeta (decisión de Martín: la
página arma un ZIP sin comprimir con los DXF, así el servidor siempre recibe un ZIP); en su propia tarea de la cola
(si falla, el visor del proyecto sigue andando) genera `<carpeta>_zicar.zip` con la misma forma que la carpeta que
deja "Convertir proyecto" en la PC; "Descargar Zicar" y subir la carpeta son de dueño y oficina (decisión de Martín).

## 2026-10-06 · Tres funcionalidades nuevas antes de los pilotos
Elegidas por Martín: etiquetas con QR (ficha 12), avance por etapas con fin de fabricación y control de carga
(ficha 13) y probador de colores en el link del cliente (ficha 14). Martín sumó la **etiqueta por mueble**: sirve
para cerrar la fabricación de cada mueble y para controlar la carga bulto por bulto. Quedaron para después de las
entrevistas: piezas a rehacer, uso sin señal, resumen de materiales, aprobación del cliente, estado del pedido para
el cliente, tablero de producción, avisos e integraciones.

## 2026-10-07 · Pantalla con los trabajos de todos los proyectos
Pedido de Martín, sumado a la ficha 05 (es del mismo tema y ninguna otra ficha lo cubre). `/<taller>/trabajos/` lista
los trabajos de todo el taller, vencidos primero, con filtros por persona, proyecto y estado; armadores e instaladores
entran viendo "para mí", dueño y oficina todo. Desde la lista se pasa al estado siguiente con ✓ (cualquiera del taller,
como en el visor; si otro ya lo cambió, no avanza dos veces) y se abre el trabajo en el visor (`?t=`). Es una página
de Django sin JavaScript propio (salvo aplicar filtros al cambiarlos): anda en cualquier celular. En el detalle del
visor, "Agregar foto" para cualquiera del taller (antes las fotos solo se sumaban desde Editar).

## 2026-10-07 · Trabajos: gente del taller y quién puede qué
"Para quién" es solo un miembro activo del taller (decisión de Martín): queda vinculado al usuario y el nombre sale
de su perfil; el que ya tenía un trabajo lo conserva aunque deje el taller. Quién anota y quién cambia cada estado
sale de la sesión, no de lo que mande el navegador (en el NAS era un nombre guardado en el celular). Cualquier
miembro anota, cambia el estado y sube fotos; cambiar texto, piezas, fecha o para quién, borrar y quitar fotos ajenas
es de quien lo anotó, el dueño o la oficina (confirmado por Martín el 2026-10-07; se cambia en `puede_editar`).
Descartado: texto libre para alguien de afuera (por ahora).

## 2026-10-07 · Trabajos: mismas rutas que el NAS, proyecto por id
La API vive en `/<taller>/visor/api/` con las rutas y respuestas de `referencia/api_actual.py`, así `index.html`
cambió poco: `autor`, `asignado` y `*_por` siguen siendo nombres (más `asignado_id` y `puede_editar`). El trabajo va
con el proyecto (no con la versión) por su id, porque dos proyectos pueden llamarse igual. El visor manda el token
CSRF de `VISOR.csrf`. Además del último quién/cuándo de cada paso (como en el NAS), `CambioDeEstado` guarda todos los
cambios, también los que se deshacen al volver atrás. Las fotos se comprueban con Pillow (el tipo que dice el pedido
tiene que ser el real) y se leen sin `request.body`, cuyo tope de Django es 2,5 MB. Límites por plan en
`talleres/limites.py`: `trabajos` y `fotos_de_trabajos` por separado; la ficha 08 los activa.

## 2026-10-06 · Cómo se pintan los lados de las piezas
Definición de Martín. Lado sin canto: un color de MDF que elige cada taller (Materiales; `#B58F63` por defecto).
Canto que se llama como el tablero de la pieza: se ve igual que el tablero, con su textura. Los nombres se comparan sin
mayúsculas ni acentos porque Polyboard suele tener `Blanco` (tablero) y `blanco` (canto), `f-Tribal` y `f-tribal`. Otro
canto: su color, de `cantos`. Igual en el visor y en los GLB de AR. Antes los lados sin canto y los cantos con nombre
de tablero tomaban el color del tablero o el color de señalización de Polyboard.

## 2026-10-06 · El visor se sirve con sus rutas relativas
La app sirve `visor/index.html` en `/<taller>/visor/` y `/c/<código>/`, y atiende debajo las mismas rutas `data/…` que
pedía en el NAS (`data/index.json` sale de la base). Lo que la app tiene que decir (modo cliente, marca, trabajos) va
en `window.VISOR`, que la vista reemplaza en el HTML. Así el archivo cambia poco y sigue andando sin la app (sin
configuración se comporta como antes). Descartado: plantilla de Django con todo el visor adentro (se separaría del
original) y rutas absolutas armadas en el JavaScript.

## 2026-10-06 · Link del cliente separado del código del conversor
`LinkCliente` tiene su propio código (128 bits), vencimiento (30, 90 o 365 días, o nunca; 90 por defecto), anulación
y visitas, y apunta al proyecto: muestra siempre la versión actual. El conversor sigue nombrando los archivos con
`Proyecto.codigo_cliente`, que no se publica como link; anular un link y crear otro no obliga a reconvertir. Por
`/c/` solo salen `cliente.json`, los GLB de ese proyecto, texturas y el logo; nunca `proyecto.json`. El taller que
abre su propio link no suma visitas. Lo crean y anulan el dueño y la oficina.

## 2026-10-06 · Marca del taller: logo y un color
Logo en PNG, JPG o WEBP (SVG no: puede traer código) de hasta 2 MB, y un color que tiene que ser oscuro (luminancia
≤ 0,4) porque los botones del visor llevan letras blancas. Lo cambia solo el dueño. El pie dice "hecho con Visor"
hasta que haya nombre comercial (`MARCA_SERVICIO` y `MARCA_URL` en el `.env`).

## 2026-10-06 · El visor actual de Nord Good no se toca por ahora
Los cambios del conversor del 2026-10-06 (tableros y cantos separados, error de DXF claro) quedan solo en este repo.
El visor actual (`armado/armado`, NAS) sigue como está hasta que Martín pida llevarlos. No hace falta para que siga
andando: la salida nueva es compatible con él.

## 2026-10-06 · Tableros y cantos nunca se mezclan
Pedido de Martín: muchos tableros y cantos se llaman igual (en 6 de las 7 muestras: `c-guatambu`, `f-paraiso`,
`f-Grey Extreme Matt`…) y tienen otra imagen o color. Antes el conversor guardaba un solo dato por nombre. Ahora:
el tipo de cada material del .ocp sale de su clase en el archivo (`materiales_del_ocp`: los dos primeros materiales
nuevos son de la clase tablero y de la clase canto; después cada uno lleva la marca de su clase, menor la de tableros;
comprobado en las 7 muestras). `materiales.json` puede venir separado (`tableros`/`cantos`); el formato plano sigue
valiendo para los dos. Cada tipo busca solo en sus fuentes (un canto ya no toma la imagen de la biblioteca de
tableros). La salida trae `materiales` (tableros, y los cantos que no se llaman como un tablero, para no romper el
visor actual) y `cantos`. La biblioteca del taller tiene `tipo`. Descartado: separar por mayúsculas/minúsculas
(Kogan tiene tablero y canto con el nombre idéntico).

## 2026-10-06 · Errores del conversor sin texto técnico
El taller ve solo qué pasó y qué hacer ("No se pudo abrir x.dxf: el archivo está dañado o no es un DXF. Exportá de
nuevo…"); el detalle de ezdxf va al log. Pedido de Martín.

## 2026-10-06 · Texturas: biblioteca del taller, una imagen por material
En el servidor no está la carpeta Textures de Polyboard. Al convertir, los materiales del proyecto que en Polyboard
tienen imagen se suman solos a la biblioteca del taller (`proyectos.Material`, con la ruta de Polyboard y el ancho en
mm). Los que no tienen imagen subida se ven con su color y el proyecto avisa "Faltan texturas"; el taller sube cada
imagen una vez y sirve para todos los proyectos. Después, el proyecto ofrece "Volver a convertir" (versión nueva con
los mismos originales); no se reconvierte solo. La biblioteca se le pasa al conversor como su `materiales.json` y una
carpeta Textures temporal, sin cambiar el conversor. Decidido por Martín. Descartado: subir un ZIP con la carpeta
Textures (cientos de MB, casi todo sin usar), subir las bibliotecas .mat-boole, reconvertir automáticamente (puede
llenar la cola sin que nadie lo pida).

## 2026-10-06 · Conversión en un proceso aparte
La tarea de la cola baja originales y texturas a una carpeta temporal y corre `python -m proyectos.proceso`, que no usa
Django ni la base: un proyecto que se cuelga o se come la memoria no tumba la cola. Límite de tiempo
`CONVERSION_SEGUNDOS` (600) y de memoria `CONVERSION_MEMORIA_MB` (2048, solo Linux). `ErrorConversion` llega al taller
tal cual; tiempo, memoria y errores inesperados dan un mensaje fijo y el detalle va al log. Cada subida es una versión
(`talleres/<t>/proyectos/<p>/versiones/<n>/originales|resultado/`); "Volver a convertir" crea otra versión que apunta
a los mismos originales sin copiarlos. El JSON principal queda siempre como `resultado/proyecto.json` y el código del
link del cliente es fijo por proyecto. Tamaño máximo del DXF: 95 MB, porque Cloudflare gratis corta en 100 MB.

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
