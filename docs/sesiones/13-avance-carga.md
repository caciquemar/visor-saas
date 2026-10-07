# 13 · Avance por etapas, fin de fabricación y control de carga

**Requiere:** ficha 12 (etiquetas de pieza y de mueble).

## Objetivo
Saber en todo momento cuánto falta de cada mueble, cerrar la fabricación mueble por mueble y no salir nunca a obra
con un bulto de menos.

## Alcance
- **Etapas de las piezas**, configurables por taller. Por defecto: cortada, canteada, mecanizada, armada.
- **Modo puesto:** el que está en un puesto elige la etapa una vez y escanea pieza tras pieza (sonido y vibración en
  cada lectura, aviso si la pieza ya estaba marcada o es de otro proyecto). Queda quién y cuándo. Se puede deshacer.
- **Fin de fabricación por mueble:** se escanea la etiqueta del mueble y se toca "Fabricación terminada". Si faltan
  piezas por armar, muestra cuáles; se puede terminar igual con un motivo. Ahí se indica la cantidad de bultos y se
  imprimen sus etiquetas (ficha 12).
- **Control de carga:** se arma una carga (proyecto completo o algunos muebles) y se escanea cada bulto al subirlo.
  La pantalla muestra lo cargado y lo que falta, y no deja marcar "Salió a obra" con faltantes sin confirmarlo con un
  motivo. Opcional: escanear de nuevo en obra para "Entregado".
- **Avance a la vista:** porcentaje por mueble y por proyecto en la lista de proyectos, en la pantalla del proyecto
  y en el visor (las piezas ya armadas con otro tono en el 3D).
- Estados de bulto: embalado, cargado, entregado. Todo con usuario y hora.
- Si se sube una versión nueva del proyecto, el avance se conserva en las piezas que siguen iguales (misma regla que
  la ficha 12) y se avisa qué piezas son nuevas.
- Dejar listos los datos para mostrar el estado del pedido al cliente final más adelante (no mostrarlo todavía).

## Fuera de alcance
Estado del pedido en el link del cliente. Tablero de producción del dueño. Avisos por mail o WhatsApp.

## Listo cuando
Con una muestra real: se marcan piezas en dos etapas desde el celular, se termina un mueble con sus bultos, se arma
una carga, falta un bulto y la app lo avisa; todo queda con nombre y hora. Pruebas de separación cubren etapas,
bultos y cargas.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/13-avance-carga.md`. Empezá en modo plan. Mostrame primero cómo se ve el modo
> puesto en el celular, porque se usa con las manos ocupadas.
