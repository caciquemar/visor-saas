# 12 · Etiquetas con QR: por pieza y por mueble

## Objetivo
Que el visor sirva también a talleres que reciben las piezas sin etiqueta de mecanizado, y que cada mueble terminado
tenga su propia etiqueta para cerrar la fabricación y controlar la carga (ficha 13).

## Alcance
- **Etiqueta de pieza:** QR + número, nombre de la pieza, mueble, proyecto, largo × ancho, cantos (qué lados y cuál)
  y flecha de veta. El QR abre esa pieza puntual en el visor. Hoy, al escanear un número de mecanizado, se marcan
  todas las piezas con ese número (ver `index.html`, "no se sabe cuál es"); el QR resuelve eso porque identifica
  una pieza sola.
- **Etiqueta de mueble (bulto):** QR + proyecto, cliente, mueble, "bulto 1 de 3", cantidad de piezas y dirección de
  la obra si está cargada. Un mueble puede tener varios bultos: la cantidad la define quien embala (ficha 13) y
  se puede reimprimir.
- **Impresión en PDF**, que el taller elige y queda guardado:
  - Hoja A4 de etiquetas autoadhesivas (formatos comunes, con márgenes ajustables).
  - Rollo de impresora térmica (por ejemplo 100 × 50 mm y 62 mm de ancho).
- Imprimir por proyecto, por mueble o una selección (para reponer una etiqueta perdida).
- El QR lleva solo una dirección con un identificador corto; no lleva datos del proyecto. Abierto con la cámara
  del celular fuera de la app, pide entrar (mail o PIN) y después abre la pieza o el mueble.
- El escáner del visor ya lee QR (`FORMATOS` en `index.html`): que distinga el QR propio del número de mecanizado y
  siga aceptando los dos.
- Identificadores de pieza y mueble que no cambien al subir una versión nueva del proyecto mientras la pieza siga
  existiendo (mismo número, nombre y mueble). Si la pieza desaparece en la versión nueva, la etiqueta vieja avisa
  "Esta pieza ya no está en la versión actual". Decidir la regla y anotarla en `docs/decisiones.md`.

## Fuera de alcance
Marcar etapas, terminar muebles y controlar la carga (ficha 13). Etiquetas para el cliente final.

## Listo cuando
Una etiqueta de pieza y una de mueble impresas en papel de verdad (A4 y, si hay, térmica) se leen con la cámara del
celular y con el escáner del visor, y abren lo correcto. Las etiquetas de mecanizado siguen funcionando. Pruebas de
separación: un QR de otro taller da 404.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/12-etiquetas-qr.md`. Empezá en modo plan. Quiero ver primero cómo identificás
> piezas y muebles entre versiones, y una etiqueta de muestra en PDF antes de seguir.
