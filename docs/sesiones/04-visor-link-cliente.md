# 04 · Visor dentro de la app y link del cliente

## Objetivo
El visor actual funcionando con los datos de cada taller, y el link para el cliente final con la marca del taller.

## Alcance
- Servir `visor/index.html` desde la app y cambiar lo mínimo para que `data/…` y `api/…` apunten al taller y al
  proyecto de la sesión (hoy son rutas relativas: ver los `fetch` de index.html). La lista de proyectos sale de la app,
  no de `index.json`.
- Escaneo de pieza funcionando por HTTPS en el celular (probar con el navegador integrado en formato celular).
- `link_cliente`: código no adivinable, vencimiento, anulación, contador de visitas. Dirección `/c/<código>`.
  Muestra solo la versión cliente (sin números de mecanizado ni datos de taller), con realidad aumentada.
- Marca del taller en el link: logo y color elegidos en su panel. Pie chico "hecho con [marca]".
- Texturas y GLB servidos sin romper la separación entre talleres.
- Ícono y nombre de la app instalable genéricos hasta tener marca (no usar el árbol de Nord Good).

## Fuera de alcance
Trabajos (ficha 05). Dominio propio del taller (más adelante, plan Fábrica).

## Listo cuando
Un proyecto de muestra se ve igual que en visor.nordgood.com.ar; el link del cliente abre sin login en otro navegador,
deja de andar al anularlo y no expone datos de taller.

## Para abrir la sesión
> Leé `CLAUDE.md` y `docs/sesiones/04-visor-link-cliente.md`. Empezá en modo plan; quiero ver la lista de cambios a
> index.html antes de hacerlos.
