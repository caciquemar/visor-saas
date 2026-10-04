# 05 · Trabajos a realizar y fotos

## Objetivo
Pasar la lógica de `referencia/api_actual.py` a la app, con usuarios reales.

## Alcance
- Modelos `trabajo` y `foto` con taller, proyecto, piezas, muebles, estados (pendiente → en proceso → hecho → instalado),
  responsable, fecha límite, y quién y cuándo en cada cambio de estado.
- Las mismas rutas que usa el visor hoy (`/api/trabajos…`), ahora con sesión y dentro del taller, para tocar poco index.html.
- Fotos al almacenamiento; mismos tipos y tamaños que hoy (12 MB, jpg/png/webp).
- Límites por plan preparados (la ficha 08 los activa).

## Listo cuando
El botón "Trabajos" del visor funciona igual que hoy, con nombres de usuario reales; las pruebas de separación cubren
trabajos y fotos.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/05-trabajos.md`. Compará con `referencia/api_actual.py` y proponé el plan.
