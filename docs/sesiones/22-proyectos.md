# Ficha 22 — Proyectos: ABM, en desarrollo / en producción, datos, lista y proyecto por secciones

Pedidos de Martín (2026-10-24).

## Qué pidió y eligió

- **ABM de proyectos.** Alta: la subida de siempre, con los datos. Modificación: los datos. Baja: **archivar**, y
  **desde Archivados se puede borrar** del todo.
- **Habilitar o deshabilitar para producción.** Un proyecto **en desarrollo** no aparece en Mi puesto, el Tablero de
  control, el visor (Armado) ni Tareas, pero **el cliente lo ve en su link**: es para los proyectos que todavía se
  están mostrando al cliente.
- **Datos:** dirección de entrega, teléfono y mail del cliente, fecha de entrega comprometida, número de pedido y notas.
- **El proyecto en secciones**, como pestañas pero **con íconos**: Resumen · Producción · Cliente · Versiones.
- **La lista de proyectos** con búsqueda, filtros y avance.

## Qué se hizo

- `Proyecto`: `telefono`, `mail`, `pedido`, `entrega`, `notas`, `en_produccion`, `archivado_en`/`archivado_por`;
  `direccion` se muestra como "dirección de entrega" (migración `proyectos 0008`: los que ya existían quedan en
  producción, los nuevos empiezan en desarrollo salvo que se tilde "Ya va a producción" al subir).
  `estado` (`desarrollo`, `produccion`, `archivado`) y `para_produccion(qs)`.
- Filtro de producción: Mi puesto (proyectos y cargas), Tablero (`proyectos_listos`), lista del visor
  (`visor/data/index.json`; con `?p=<id>` suma ese proyecto aunque esté en desarrollo, para "Abrir en el visor" desde
  su pantalla, con "(en desarrollo)" en el nombre) y Tareas. Escanear la etiqueta de un proyecto en desarrollo o
  archivado avisa y no registra (`acciones.fuera_de_produccion`; `proyecto_o_rechazo(..., solo_leer=True)` para lo
  que solo lee el visor).
- Vistas: `datos` (reemplaza a `obra`), `produccion`, `archivar`, `desarchivar` y `borrar` (solo el dueño, solo
  archivado, escribiendo el nombre; `proyectos/borrar.py` borra la base en cascada y después las carpetas de las
  versiones y las fotos de tareas, instalaciones y anotaciones).
- `proyectos/ver.html` con la barra de íconos (`?ver=`) y una plantilla por sección (`ver_resumen.html`,
  `ver_produccion.html`, `ver_cliente.html`, `ver_versiones.html`). Resumen: accesos, interruptor En producción,
  avance general, datos (formulario para dueño y oficina, solo lectura para los demás) y Archivar. Las redirecciones
  vuelven a la sección de donde vino la acción. La página se actualiza sola mientras convierte solo en Versiones.
- `proyectos/lista.html`: buscar (nombre, cliente o pedido), chips En curso · En producción · En desarrollo ·
  Archivados · Todos, tarjetas con estado, barra de avance, cuántos muebles llegaron al último paso y la entrega
  (en rojo si venció y no está todo en el último paso).
- Pruebas en `tests/app/test_proyectos_abm.py`.

## Falta

- Probar en el NAS que al migrar todos los proyectos queden en producción.
