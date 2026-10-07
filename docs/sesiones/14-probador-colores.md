# 14 · Probador de colores en el link del cliente

## Objetivo
Que el cliente final pruebe colores de tablero sobre su propio mueble, en 3D y en realidad aumentada, y le mande
al taller la combinación que eligió.

## Alcance
- **Opciones por proyecto:** el taller elige, para cada tablero del proyecto, qué alternativas ofrecer, tomadas de su
  biblioteca de materiales (solo tableros, nunca cantos). Puede agruparlas con un nombre ("Frentes", "Cajonería").
- **Cantos que acompañan:** los cantos que se llaman como el tablero cambian con él (misma regla de los lados de
  las piezas, ver `docs/decisiones.md`); los otros cantos quedan como están.
- **En el link del cliente:** selector de colores con la muestra de cada textura; el 3D cambia al instante.
- **Realidad aumentada:** los GLB llevan las texturas adentro, así que cada combinación necesita su propio GLB.
  Propuesta: generarlo en la cola la primera vez que se pide esa combinación y guardarlo; mientras tanto, "Preparando…".
  Límite de combinaciones por proyecto. Decidir y anotar en `docs/decisiones.md`.
- **Elección del cliente:** botón "Me gusta esta" con nombre y comentario opcional. El taller la ve en la pantalla del
  proyecto con fecha y hora. No cambia el proyecto: el taller lo corrige en Polyboard y sube una versión nueva.
- En el visor del taller no aparece el probador (solo en el link del cliente).

## Fuera de alcance
Aprobación formal del diseño. Precio según el color. Cambiar materiales del proyecto desde la app.

## Listo cuando
Con una muestra real, el cliente cambia dos tableros, ve el cambio en 3D, abre la realidad aumentada con esa
combinación (en un celular de verdad cuando haya servidor) y manda su elección, que el taller ve.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/14-probador-colores.md`. Empezá en modo plan. Revisá cómo arma los GLB el
> conversor (`glb_ar`) antes de proponer cómo generar las combinaciones.
