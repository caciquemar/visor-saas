# Ficha 17 — Producción: Mi puesto, Tablero de control y Procesos

Pedido de Martín (2026-10-24) con un dibujo, después de ordenar el Inicio por secciones. Hecha en la misma sesión.

## Qué pidió

- **Producción** con tres opciones: **Mi puesto** (pantalla de escaneo), **Tablero de control** (indicadores de
  avance y estado por proyecto, por etapa y general) y **Procesos** (donde se definen los procesos).
- **Mi puesto**: solo **Etapa ▾**, **Ubicación ▾** y **Escanear**.

## Respuestas de Martín

- Ubicación = **dónde queda la pieza** (estante, depósito, playa de carga), para encontrarla después.
- Mi puesto no pide el proyecto: lo dice la etiqueta.
- Procesos = lo que estaba en Configuración → Etapas (se muda y se suman las ubicaciones).
- Tareas: "capaz meterlo como un proceso más" → es una opción de Etapa ▾ en Mi puesto. La pantalla Tareas queda en
  Armado.

## Qué se hizo

- Menú: Producción = Mi puesto, Tablero de control (todos) y Procesos (dueño y oficina). Configuración = Materiales,
  Equipo, Marca. `/etapas/` lleva a `/procesos/`.
- Modelos `Ubicacion` y `Ubicado` (`avance/models.py`, migración `0002_ubicaciones`), con RLS y pruebas de cruce.
- Mi puesto (`avance/puesto.html`): Etapa ▾ (etapas, Fin de fabricación, Cargar, Entregar, Tareas), Ubicación ▾ y
  Escanear. Proyecto: el de la última etiqueta; para un número de mecanizado sin ninguna antes, se pide ahí mismo
  (`falta_proyecto`). Con ubicación: cada pieza (y los bultos al terminar el mueble) queda ahí; Deshacer la deshace;
  al cargar el bulto sale del taller. Modo Tareas: `POST puesto/api/tareas` y ✓ con `PATCH visor/api/trabajos/<id>`.
- Visor: "Está en …" en la ficha de la pieza y "Piezas en …" en el bloque del mueble (`visor/api/avance`, `lugares`).
- Tablero de control (`avance/tablero.py`, `/tablero/`).

## Falta

- Probar en el NAS con celular de verdad (cámara, sonido) junto con lo pendiente de la ficha 13.
