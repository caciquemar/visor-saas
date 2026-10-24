# Ficha 21 — Cargas con ABM, carga nueva al escanear y escáner en el 3D de los procesos

Pedidos de Martín (2026-10-24).

## Qué pidió y eligió

- **Desde el proyecto, ABM de cargas.** Alta con todo, algunos o filtrando por proceso completado. Baja: anula y los
  bultos cargados vuelven a embalados (dueño u oficina). Modificar: agregar o sacar muebles (no uno con bultos ya
  cargados en esa carga).
- **Mi puesto:** elegir una carga o "Nueva carga": el primer bulto escaneado la crea (libre: lleva solo lo que se
  escanee). "Cerrar la carga": sale aunque falte algo; **lo que falta queda para otro envío**.
- **El 3D de cada proceso lleva escáner.** Se registra desde ahí como en Mi puesto; Control de calidad abre la lista de
  puntos Ok/Mal sobre el 3D; Carga usa la carga de Mi puesto (o crea una).

## Qué se hizo

- `Carga.libre`, `Carga.Estado.ANULADA`, `anulada_por`/`anulada_en` (migración `avance 0007`).
- `acciones`: `contenido` ya no cuenta como faltante lo que salió en otra carga; `pendientes_de_envio`;
  `modificar_carga`, `anular_carga`; `bulto_leido` sin carga crea una libre (y la borra si la primera lectura falla).
- Proyecto: tabla de cargas con estado, bultos y Modificar / Anular; "Nueva carga" con `avance/elegir_muebles.html`
  (Todos, Ninguno, Los que faltan enviar, filtro "Solo los que completaron" y "Tildar los que se ven").
  `pantalla.muebles_para_cargar`, `cargas/<id>/modificar/`, `cargas/<id>/anular/`.
- Mi puesto: opción "Nueva carga (se crea al escanear)", botón "Cerrar la carga"; API `cargas/nueva/bulto` y
  `cargas/<id>/salir`.
- Visor, modo avance: barra Escanear + código abajo del 3D, aviso arriba, tarjeta de control; `VISOR.avance.api`;
  `avance-proceso` trae el `tipo` del proceso.

## Falta

- Probar con celular de verdad (cámara en el 3D).
