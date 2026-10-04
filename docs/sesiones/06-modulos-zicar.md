# 06 · Módulos por taller y módulo Zicar

## Objetivo
Un mecanismo para prender funciones por taller, con Zicar como primer módulo, solo para Nord Good.

## Alcance
- Modelos `modulo` y `taller_modulo` (prendido, configuración en JSON), administrados desde la administración.
- Puntos de enganche: paso extra en la conversión, campo extra en la subida, botón extra en el proyecto.
  Si el módulo no está prendido, no se muestra nada y el servidor responde 404 aunque se arme el pedido a mano (con prueba).
- Módulo Zicar: en la subida, ZIP con la carpeta del postprocesador; la cola corre `Polyboard_to_zicar`
  (`C:\Users\Asus\GitHub\polyboard\Polyboard_to_zicar`, que queda en su propio repo privado) y guarda
  `<proyecto>_zicar.zip`; botón "Descargar Zicar".
- Cómo llega el código de Zicar al servidor sin meterlo en este repo (por ejemplo, instalable desde su repo privado).
  Decidir y anotar en `docs/decisiones.md`.

## Listo cuando
Con un proyecto real de Nord Good, el ZIP descargado es igual al que genera hoy "Convertir proyecto" en la PC;
un taller de prueba no ve nada de Zicar y recibe 404.

## Para abrir la sesión
> Leé `CLAUDE.md`, `docs/sesiones/06-modulos-zicar.md` y el `CLAUDE.md` de `Polyboard_to_zicar`. Empezá en modo plan.
