# Ficha 20 — Avance por proceso, orden libre de los procesos y reparación del Armado

Pedidos de Martín (2026-10-24) al probar la v0.7.15 y la v0.7.16 en el NAS.

## Avance por proceso (v0.7.16)

Desde Mi puesto, **Lista** y **3D** muestran el avance del proceso que se está trabajando (no el visor de armado):
`/<taller>/proyectos/<id>/entrega/?proceso=<id>` y `/<taller>/visor/?p=<id>&avance=<id>`. En el 3D solo se mira (tocar
no elige nada; sin panel ni menús): hecho en verde, a medias en ámbar, con observaciones en rojo, falta en gris; en un
proceso por pieza se pintan las piezas. Se actualiza cada 15 s. `avance/pasos.py::avance_de_proceso`,
`visor/api/avance-proceso`. Salió "Colorear por entrega".

## Orden libre

Todos los procesos se ordenan arrastrándolos en Procesos, también los fijos (que siguen sin borrarse). Mi puesto los
muestra en ese orden. Armado ya no es "el último prendido": es el proceso fijo Armado por su tipo
(`models.etapa_de_armado`; si está apagado, el último de los del taller). Un proceso nuevo queda a continuación de los
del taller.

## Reparación del Armado (migración `avance 0006`)

La 0004 tomaba como Armado la última etapa prendida. En el taller de Martín era "Instalacion" (39 usos) y quedó como
el fijo Armado. La 0006 devuelve a proceso del taller por pieza (con sus marcas) todo Armado que no se llame como el
armado ("Armado", "Armada", "Ensamble"…) y crea un Armado nuevo. La 0004 ahora elige por el nombre.
