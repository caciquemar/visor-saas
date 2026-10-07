# Decisiones

Una entrada por decisión, la más nueva arriba. Qué se decidió, por qué y qué se descartó.

## 2026-10-06 · Tres funcionalidades nuevas antes de los pilotos
Elegidas por Martín: etiquetas con QR (ficha 12), avance por etapas con fin de fabricación y control de carga
(ficha 13) y probador de colores en el link del cliente (ficha 14). Martín sumó la **etiqueta por mueble**: sirve
para cerrar la fabricación de cada mueble y para controlar la carga bulto por bulto. Quedaron para después de las
entrevistas: piezas a rehacer, uso sin señal, resumen de materiales, aprobación del cliente, estado del pedido para
el cliente, tablero de producción, avisos e integraciones.

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
